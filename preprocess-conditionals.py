import re
from typing import List, Dict, Optional, NamedTuple, Any, Set
from dataclasses import dataclass
import yaml
import argparse
import jsonschema
from jsonschema import validate, ValidationError

Line = int  # 0-based

# --------------------------------------------------------------------------- #
#  Lightweight data holders                                                   #
# --------------------------------------------------------------------------- #
@dataclass
class Block:
    kind: str               # 'code', 'table', 'open', 'comment', … - UNUSED AT PRESENT
    open_line: Line
    close_line: Line
    delimiter: str          # exact delimiter string that opened the block
    nesting: int            # 0 = outermost
    verbatim: bool
    hashable: tuple = None  # (open_line, delimiter) - set during __post_init__

    def __post_init__(self):
        # Set hashable property based on open_line and delimiter
        # This won't change even if close_line is mutated later
        object.__setattr__(self, 'hashable', (self.open_line, self.delimiter))

@dataclass
class Conditional:
    kind: str               # 'ifdef', 'ifndef', 'ifeval', 'endif'
    open_line: Line
    close_line: Line
    expression: str         # text after the :: (and before the [] )
    nesting: int


# --------------------------------------------------------------------------- #
#  Main indexer                                                               #
# --------------------------------------------------------------------------- #
class AsciiDocIndexer:
    """
    One-shot parser that remembers every delimited block and every conditional
    in an AsciiDoc document.  All queries are O(1).
    Input: list of lines (str) – 0-based indexing everywhere.
    """

    # --------------------------------------------------------------------- #
    #  Pre-compiled VERBOSE regexes                                         #
    # --------------------------------------------------------------------- #
    # 1. Four-or-more *identical* supported chars:  = * _ - . / +
    #    Line must contain ONLY that delimiter + optional trailing spaces.
    _FOUR_MORE_DELIM = re.compile(r'''
        ^                    # start of line
        (                    # group 1: the delimiter character
          [=*_\-\./+]         #   exactly one of the supported chars
        )
        \1{3,}               # that same char at least three more times → 4+
        [ \t]*               # optional trailing whitespace
        $                    # nothing else
    ''', re.VERBOSE)

    # 2. Table opener  |===  !=== ,=== :===
    _TABLE_DELIM = re.compile(r'''
        ^              # start of line
        ([|!,:])      # group 1: exactly one of |  !  ,  :
        ={3,}          # followed by at least three equals signs
        [ \t]*         # optional trailing whitespace
        $              # nothing else allowed
    ''', re.VERBOSE)

    # 3. Two-character open-block delimiter  --
    _OPEN_BLOCK_DELIM = re.compile(r'''
        ^                    # start of line
        (--)[ \t]*           # two dashes, optional trailing spaces
        $                    # nothing else
    ''', re.VERBOSE)

    # 4. Conditional directives - three patterns:

    # 4a. ifdef/ifndef: expression BEFORE brackets, brackets are empty
    #     Examples: ifdef::azure[]  ifndef::windows[]
    _IFDEF_IFNDEF = re.compile(r'''
        ^                    # start of line
        (ifdef|ifndef)       # group 1: directive name
        ::                   # literal double colon
        ([^\[\]]+)           # group 2: expression (before brackets, non-empty)
        \[\]                 # empty bracket pair
        [ \t]*               # optional trailing whitespace
        $
    ''', re.VERBOSE)

    # 4b. ifeval: expression INSIDE brackets
    #     Example: ifeval::["{attr}"=="value"]
    _IFEVAL = re.compile(r'''
        ^                    # start of line
        (ifeval)             # group 1: directive name
        ::                   # literal double colon
        \[                   # opening bracket
        ([^\]]+)             # group 2: expression (inside brackets, non-empty)
        \]                   # closing bracket
        [ \t]*               # optional trailing whitespace
        $
    ''', re.VERBOSE)

    # 4c. endif: expression can be EITHER before or inside brackets
    #     Examples: endif::[]  endif::azure[]  endif::[azure]
    _ENDIF = re.compile(r'''
        ^                    # start of line
        (endif)              # group 1: directive name
        ::                   # literal double colon
        (?:                  # non-capturing group for two alternatives:
          ([^\[\]]*)\[\]     #   option 1: expression before empty brackets (group 2)
          |                  #   OR
          \[([^\]]*)\]       #   option 2: expression inside brackets (group 3)
        )
        [ \t]*               # optional trailing whitespace
        $
    ''', re.VERBOSE)

    # --------------------------------------------------------------------- #
    def __init__(self, lines: List[str]):
        self.lines: List[str] = lines
        self.blocks: List[Block] = []
        self.conditionals: List[Conditional] = []

        # four O(1) lookup tables  line -> object
        self._block_opener: Dict[Line, Block] = {}
        self._block_closer: Dict[Line, Block] = {}
        self._cond_opener: Dict[Line, Conditional] = {}
        self._cond_closer: Dict[Line, Conditional] = {}

        self._parse()

    # -------------------------------------------------------------------- #
    #  Public helpers                                                      #
    # -------------------------------------------------------------------- #
    def get_block_by_opening_line(self, line: Line) -> Optional[Block]:
        """ Return the block that is opening on this line, None if there's none """
        return self._block_opener.get(line)

    def get_block_by_closing_line(self, line: Line) -> Optional[Block]:
        """ Return the block that is closing on this line, None if there's none """
        return self._block_closer.get(line)

    def get_conditional_by_opening_line(self, line: Line) -> Optional[Conditional]:
        """ Return the conditional that is opening on this line, None if there's none """
        return self._cond_opener.get(line)

    def get_conditional_by_closing_line(self, line: Line) -> Optional[Conditional]:
        """ Return the conditional that is closing on this line, None if there's none """
        return self._cond_closer.get(line)

    def blocks_enclosing(self, line: Line) -> List[Block]:
        """
        Return every Block that *fully encloses* the given 0-based line.
        'Fully enclosed'  ⇔  block.open_line < line < block.close_line
        """
        return [b for b in self.blocks if b.open_line < line < b.close_line]

    def conditionals_enclosing(self, line: Line) -> Set[Conditional]:
        """
        Same idea for conditionals.
        """
        return {c for c in self.conditionals
                if c.open_line < line < c.close_line}

    def is_in_same_blocks(self, line1: Line, line2: Line) -> bool:
        """
        Check if two lines are enclosed by the same set of blocks.
        Uses block.hashable for comparison to avoid mutability issues.
        """
        blocks1 = {b.hashable for b in self.blocks_enclosing(line1)}
        blocks2 = {b.hashable for b in self.blocks_enclosing(line2)}
        return blocks1 == blocks2

    # ------------------------------------------------------------------ #
    # Sorted list of conditional start lines                             #
    # ------------------------------------------------------------------ #
    def conditional_start_lines(self) -> List[Line]:
        """
        All 0-based line numbers that open a conditional, in ascending order.
        """
        if not hasattr(self, '_cond_starts_cache'):
            self._cond_starts_cache = sorted(
                c.open_line for c in self.conditionals if c.open_line >= 0)
        return self._cond_starts_cache

    # -------------------------------------------------------------------- #
    #  Internal parser                                                     #
    # -------------------------------------------------------------------- #
    def _parse(self):
        block_stack: List[Block] = []
        cond_stack: List[Conditional] = []

        # true while we are inside ----  ++++  or  ////  and must ignore nesting
        verbatim_mode: Optional[str] = None

        for lineno, raw in enumerate(self.lines):

            # ------------------------------------------------------------- #
            # 1.  Conditional directives
            # ------------------------------------------------------------- #
            # Try matching ifdef/ifndef
            m = self._IFDEF_IFNDEF.match(raw)
            if m:
                directive, expr = m.groups()
                lvl = len(cond_stack)
                c = Conditional(kind=directive, open_line=lineno,
                    close_line=len(self.lines), expression=expr, nesting=lvl)
                self.conditionals.append(c)
                self._cond_opener[lineno] = c
                cond_stack.append(c)
                continue

            # Try matching ifeval
            m = self._IFEVAL.match(raw)
            if m:
                directive, expr = m.groups()
                lvl = len(cond_stack)
                c = Conditional(kind=directive, open_line=lineno,
                    close_line=len(self.lines), expression=expr, nesting=lvl)
                self.conditionals.append(c)
                self._cond_opener[lineno] = c
                cond_stack.append(c)
                continue

            # Try matching endif
            m = self._ENDIF.match(raw)
            if m:
                directive = m.group(1)  # 'endif'
                # Expression can be in group 2 (before brackets) or group 3 (inside brackets)
                expr = m.group(2) if m.group(2) is not None else m.group(3)
                if expr is None:
                    expr = ""  # Handle case where both groups are None

                lvl = len(cond_stack) - 1
                if cond_stack:
                    # modify the conditional now being closed to save its closing line
                    open_c = cond_stack.pop()
                    open_c.close_line = lineno
                    # set the closing line index
                    self._cond_closer[lineno] = open_c
                else:
                    # save endif conditional, output a warning
                    c = Conditional(kind='endif', open_line=-1, close_line=lineno,
                                    expression=expr, nesting=lvl)
                    self._cond_closer[lineno] = c
                    self.conditionals.append(c)
                    print(f"WARNING: unmatched endif at line {lineno+1}")
                continue

            # ------------------------------------------------------------- #
            # 2.  Inside a verbatim block we only look for the closing twin
            # ------------------------------------------------------------- #
            if verbatim_mode:
                if raw.rstrip() == verbatim_mode:
                    # close verbatim block
                    open_b = block_stack.pop()
                    open_b.close_line = lineno
                    self._block_closer[lineno] = open_b
                    verbatim_mode = None
                # ignore everything else while verbatim
                continue

            # ------------------------------------------------------------- #
            # 3.  Delimited blocks
            # ------------------------------------------------------------- #
            if (self._FOUR_MORE_DELIM.match(raw) or self._TABLE_DELIM.match(raw) or
             self._OPEN_BLOCK_DELIM.match(raw)):
                delim = raw.rstrip()

                if block_stack and block_stack[-1].delimiter == delim:
                    # close a block
                    open_b = block_stack.pop()
                    open_b.close_line = lineno
                    self._block_closer[lineno] = open_b
                else:
                    # open new block

                    # enter verbatim mode for ----  ++++  //// ....
                    verbatim_flag = ((len(delim)>=4) and
                       (delim[:4] in ["----","++++","////","...."]))

                    if verbatim_flag:
                        verbatim_mode = delim


                    # kind = self._classify_block(open_delim)
                    kind = ""
                    lvl = len(block_stack)
                    b = Block(
                        kind=kind,
                        open_line=lineno,
                        close_line=len(self.lines),
                        delimiter=delim,
                        nesting=lvl,
                        verbatim=verbatim_flag
                    )
                    self.blocks.append(b)
                    self._block_opener[lineno] = b
                    block_stack.append(b)
        # the looping over the lines is now done
        # non-closed conditionals and blocks are already saved with close_line=len(self.lines)
        # TODO: output warnings about them

class ConditionalLookup:
    """
    Build a lookup table from a YAML (or dict) config that looks like:

        attributes:
          platform: [azure,aws,onprem]
          product: [rhel,ocp,rosa]
        conditionals:
          - name: azure
            attribute: platform
            value: azure
          - name: rhel
            attribute: product
            value: rhel

    TODO: proper error handling
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self._attributes: Dict[str, List[str]] = dict(config["attributes"])
        self._cond_map: Dict[str, tuple[str, str]] = {}
        for cond in config["conditionals"]:
            self._cond_map[cond["name"]] = (cond["attribute"], cond["value"])

    def is_supported(self, conditional: str):
        return (conditional in self._cond_map)

    def find_attribute_value(self, conditional: str, ifdef: bool = True) -> tuple[str, str]:
        try:
            attr, val = self._cond_map[conditional]
        except KeyError as e:
            raise ValueError(f"Unknown conditional: {conditional!r}") from e

        if ifdef:
            return (attr, val)

        # Build comma-separated list of everything *except* the excluded value
        try:
            all_vals = self._attributes[attr]
        except KeyError:
            raise KeyError(f"Attribute {attr!r} not found in config") from None

        remaining = [v for v in all_vals if v != val]
        return (attr, ",".join(remaining))

# JSON Schema for validating the YAML configuration
CONDITIONALS_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["attributes", "conditionals"],
    "properties": {
        "attributes": {
            "type": "object",
            "description": "Mapping of attribute names to their possible values",
            "patternProperties": {
                "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "uniqueItems": True
                }
            },
            "additionalProperties": False,
            "minProperties": 1
        },
        "conditionals": {
            "type": "array",
            "description": "List of conditional definitions",
            "items": {
                "type": "object",
                "required": ["name", "attribute", "value"],
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Conditional name used in ifdef/ifndef directives"
                    },
                    "attribute": {
                        "type": "string",
                        "description": "Reference to an attribute defined in the attributes section"
                    },
                    "value": {
                        "type": "string",
                        "description": "Value from the attribute's possible values"
                    }
                },
                "additionalProperties": False
            },
            "minItems": 1
        }
    },
    "additionalProperties": False
}

def validate_config_schema(config: Dict[str, Any]) -> None:
    """
    Validate the configuration against the JSON schema and perform additional checks.
    Raises ValidationError with helpful messages if validation fails.
    """
    # First validate against the JSON schema
    try:
        validate(instance=config, schema=CONDITIONALS_SCHEMA)
    except ValidationError as e:
        # Create a more user-friendly error message
        path = " -> ".join(str(p) for p in e.path) if e.path else "root"
        raise ValidationError(f"Schema validation failed at '{path}': {e.message}") from e

    # Additional semantic validation: check that conditional attributes reference existing attributes
    attributes = config["attributes"]
    conditionals = config["conditionals"]

    conditional_names = set()
    for idx, cond in enumerate(conditionals):
        cond_name = cond["name"]
        cond_attr = cond["attribute"]
        cond_value = cond["value"]

        # Check for duplicate conditional names
        if cond_name in conditional_names:
            raise ValidationError(
                f"Duplicate conditional name '{cond_name}' found at conditionals[{idx}]"
            )
        conditional_names.add(cond_name)

        # Check that the referenced attribute exists
        if cond_attr not in attributes:
            raise ValidationError(
                f"Conditional '{cond_name}' at conditionals[{idx}] references "
                f"unknown attribute '{cond_attr}'. Available attributes: {list(attributes.keys())}"
            )

        # Check that the value is in the attribute's list of possible values
        if cond_value not in attributes[cond_attr]:
            raise ValidationError(
                f"Conditional '{cond_name}' at conditionals[{idx}] uses value '{cond_value}' "
                f"which is not in attribute '{cond_attr}' possible values: {attributes[cond_attr]}"
            )

def load_config(config_path: str) -> ConditionalLookup:
    """ Load and validate the configuration file """
    try:
        with open(config_path) as cy:
            config = yaml.safe_load(cy)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML in {config_path}: {str(e)}")
        exit(3)
    except Exception as e:
        print(f"Error reading {config_path}: {str(e)}")
        exit(3)

    # Validate the configuration
    try:
        validate_config_schema(config)
    except ValidationError as e:
        print(f"Configuration validation error in {config_path}:")
        print(f"  {str(e)}")
        exit(3)

    return ConditionalLookup(config)

def read_input_file(file_path: str) -> List[str]:
    """ Read the input file """
    # this particular method strips the \n characters
    try:
        with open(file_path) as f:
            return f.read().splitlines()
    except Exception as e:
        print (f"Error when reading {file_path}: {str(e)}")
        exit(4)

def is_conditional_processable(conditional: Conditional,
    indexer: AsciiDocIndexer, conditional_lookup: ConditionalLookup,
        previous_end_line_number: Line) -> bool:
    # ignore not ifdef/ifndef
    if not conditional.kind in ["ifdef","ifndef"]: return False

    lineno = conditional.open_line

    # ignore unsupported
    if not conditional_lookup.is_supported(conditional.expression): return False

    # reject nested
    if lineno<previous_end_line_number:
        print(f"WARNING: nested conditionals NOT supported, line {lineno+1}")
        return False

    # reject contained in different blocks
    if not indexer.is_in_same_blocks(lineno, conditional.close_line):
        print(f"WARNING: conditionals with a block boundary between them NOT supported, line {lineno+1}")
        return False

    enclosing_blocks = indexer.blocks_enclosing(lineno)

    # reject contained in verbatim blocks
    if any(b.verbatim for b in enclosing_blocks):
        print(f"WARNING: conditionals inside verbatim blocks NOT supported, line {lineno+1}")
        return False

    # reject conditionals inside table blocks
    if any(AsciiDocIndexer._TABLE_DELIM.match(b.delimiter) for b in enclosing_blocks):
        print(f"WARNING: conditionals inside table blocks NOT supported, line {lineno+1}")
        return False



    # reject empty
    if conditional.close_line<=lineno+1:
        print(f"WARNING: empty conditionals NOT supported, line {lineno+1}")
        return False

    # TODO: test if we need to reject blank-lines-only here

    return True

def is_conditional_processable_as_parablock_start(conditional: Conditional, lines: List[str], indexer: AsciiDocIndexer) -> bool:
    """ check if a conditional can be processed as one or several blocks/paragraphs/list items
    This is the check of the start line """

    lineno=conditional.open_line

    # Start is the first line
    if lineno==0: return True

    # Line before start is blank
    if lines[lineno-1].strip()=="": return True

    # Line before start closes a block
    if indexer.get_block_by_closing_line(lineno-1): return True

    # Line after start starts a block
    if (lineno < len(lines)-2) and indexer.get_block_by_opening_line(lineno+1):
        return True

    # Line after start is [...] and the one after that is the start of a block

    if ((lineno < len(lines)-3) and lines[lineno+1].startswith("[") and
        lines[lineno+1].rstrip().endswith("]") and
        indexer.get_block_by_opening_line(lineno+2)):
            return True

    return False

def is_conditional_processable_as_parablock_end(conditional: Conditional, lines: List[str], indexer: AsciiDocIndexer) -> bool:
    """ check if a conditional can be processed as one or several blocks/paragraphs/list items
    This is the check of the end line """

    # now check the closing line - if it is the last line
    # or else the line above it is a block close
    # or else the line after it is blank
    # or else the line after it starts a block
    # or else the line below the closing line is [...] and the one after that is the start of a block
    # if none of this is true, can't process as "parablocks" (whole paragraphs, blocks, list items)
    # TODO: consider the situation when the line below is the start of another conditional
    #  (in this situation this can still be a paragraph/block boundary ...
    #  IF conditionals are mutually exclusive)
    closeline=conditional.close_line

    # it is the last line or beyond
    if (closeline >= len(lines)-1): return True

    # block closes before closing line
    if indexer.get_block_by_closing_line(closeline-1): return True

    # blank line after closing line
    if (lines[closeline+1].strip()==""): return True

    # block opens after closing line
    if indexer.get_block_by_opening_line(closeline+1): return True

    # line below the closing line is [...] and the one after that is the start of a block
    if ((closeline<len(lines)-3) and lines[closeline+1].startswith("[") and
        lines[closeline+1].rstrip().endswith("]") and
        indexer.get_block_by_opening_line(closeline+2)):
            return True

    return False

def process_parablock_conditional(lines: List[str], conditional: Conditional, attribute: str, value: str, indexer: AsciiDocIndexer, to_insert_lines: Dict, to_delete_lines: List) -> None:
    """ process a conditional as applying to one or more paragraphs/blocks/list items
       save any lines to insert in to_insert_lines and lines to delete in to_delete_lines """

    lineno=conditional.open_line

    # Mark the ifdef/ifndef and endif lines for deletion
    to_delete_lines.append(lineno)
    to_delete_lines.append(conditional.close_line)

    # walk to the end line inserting roles
    # when they are new lines, tbat's most of them, put this in the buffer
    current_line=lineno+1
    while current_line<conditional.close_line:
        if lines[current_line].startswith(". "):
            # this is a list item, insert special role stub
            # TODO: here, we assume that every list item is separate all the time
            # HOWEVER when the conditional encompasses en entire list,
            # the list should get the role instead
            lines[current_line]= \
              f'. [.{attribute}:{value}]#{{empty}}#{lines[current_line][2:]}'
        elif (lines[current_line].startswith("[") and lines[current_line].rstrip().endswith("]")
          and not lines[current_line].startswith("[.")):
            # paraneters for the upcoming block/paragraph, add role
            until_closing_bracket=lines[current_line][:lines[current_line].rfind("]")]
            lines[current_line]=f'{until_closing_bracket},role="{attribute}:{value}"]'
            # in this specific case we treat the NEXT line as the one to which role was just added
            current_line+=1
        else:
            # need to insert a role string
            to_insert_lines[current_line]=f'[role="{attribute}:{value}"]'

        # the role was just added to the line so we need to find the next one
        if (block := indexer.get_block_by_opening_line(current_line)):
            # the role was added to a block, skip to after the end of the block
            current_line = block.close_line+1
            # if the next line is a blank line or a +, we just need the normal search from it
            if not (lines[current_line].strip() in ["","+"]):
                continue
        else:
            # start search from the line where we added a role
            current_line+=1

        # find one of: blank line, block start, list item, end of current conditional
        while not (current_line >= conditional.close_line or
            lines[current_line].strip()=="" or
            indexer.get_block_by_opening_line(current_line) or
            lines[current_line].startswith(". ")):
                current_line+=1

        if current_line >= conditional.close_line:
            break
            # while this just duplicates the while condition, it avoids
            #  out-of-bounds in following checks

        # if we found a blank line, the role needs to go on to the first
        #  non-blank line or to the end of the block

        while ((current_line < conditional.close_line) and (lines[current_line].strip()=="")):
            current_line+=1

        # if we found the block start and there is a parameter block above it,
        #   the role needs to be added to the parameter block
        #   if the previous loop was triggered, lines[candidate] will be blank
        #   so this one won't be triggered in that case - no need for elif
        if indexer.get_block_by_opening_line(current_line):
            candidate=current_line-1
            if (lines[candidate].startswith("[") and
              lines[candidate].rstrip().endswith("]") and
              not lines[candidate].startswith("[.")):
                 current_line=candidate

def process_inline_conditional(lines: List[str], conditional: Conditional, attribute: str, value: str, indexer: AsciiDocIndexer, to_delete_lines: List) -> None:
    """ process a conditional as applying inline to a part of one paragraph/block
       save any lines to delete in to_delete_lines """
    lineno=conditional.open_line
    # mark the opening and closing line of the conditional for removal
    to_delete_lines.append(lineno)
    to_delete_lines.append(conditional.close_line)

    # in the first line inside the conditional, add the start of the role
    # NOTE: spaces at the start are not supported in asciidoc
    lines[lineno+1]=f"[.{attribute}:{value}]#{lines[lineno+1].lstrip()}"

    # in the last line inside the conditional, add the end of the role
    # NOTE: spaces at the start are not supported in asciidoc
    # NOTE: this well may be the same as the previous line
    lines[conditional.close_line-1]=lines[conditional.close_line-1].rstrip()+"#"

def apply_line_modifications(lines: List[str], to_insert_lines: Dict, to_delete_lines: List) -> None:
    """ apply line insertions and deletions """

    # Sanity check: a line should never be in both lists
    overlap = set(to_insert_lines.keys()) & set(to_delete_lines)
    if overlap:
        raise ValueError(f"Internal error: lines {overlap} appear in both insert and delete lists")

    lines_original_len=len(lines)
    current_correction=0 # difference between old and current index right now

    for lineno in range(lines_original_len):
        if lineno in to_insert_lines:
            lines.insert(lineno+current_correction,to_insert_lines[lineno])
            current_correction+=1
        elif lineno in to_delete_lines:
            lines.pop(lineno+current_correction)
            current_correction-=1

def process_conditionals(lines: List[str], indexer: AsciiDocIndexer, conditional_lookup: ConditionalLookup) -> None:
    """ process the conditionals in the input file """

    # processing as paragraphs/blocks can break immutability if it inserts or deletes a line
    # to avoid ths problem we create a buffer specifically for inserting lines after the main run
    to_insert_lines = {}

    # and a list of lines to delete
    to_delete_lines = []

    # walk conditionals
    previous_end_line_number = -1

    for lineno in indexer.conditional_start_lines():
        conditional = indexer.get_conditional_by_opening_line(lineno)

        # check if the conditional is to be processed at all
        if not is_conditional_processable(conditional, indexer, conditional_lookup, previous_end_line_number):
                continue

        # work out the attribute and value for the current conditional
        try:
            attribute,value=conditional_lookup.find_attribute_value(
             conditional.expression, (conditional.kind=="ifdef"))
        except ValueError:
            print(f"WARNING: value not found (should not happen), line {lineno+1}")
            continue


        # if possible, process as one or several paragraphs/blocks/list items
        if (is_conditional_processable_as_parablock_start(conditional, lines, indexer)
          and is_conditional_processable_as_parablock_end(conditional, lines, indexer)):
            # this is getting processed, so mark the end line to exclude nested correctly
            previous_end_line_number=conditional.close_line
            process_parablock_conditional(lines, conditional, attribute, value, indexer, to_insert_lines, to_delete_lines)
        else:
            # processing as "parablock" was not possible
            # to check if we can process as inline we need to check every line in the conditional
            # if any is blank or a block start, nope
            process_inline=True
            for current_line in range(lineno+1,conditional.close_line):
                if lines[current_line].strip()=="" or indexer.get_block_by_opening_line(current_line):
                    process_inline=False
                    break

            if not process_inline:
                print(f"WARNING: conditionals encompassing parts of several blocks NOT supported, line {lineno+1}")
            else:
                # this is getting processed, so mark the end line to exclude nested correctly
                previous_end_line_number=conditional.close_line

                process_inline_conditional(lines, conditional, attribute, value, indexer, to_delete_lines)

    # loop is over - now insert and remove the lines as per buffers
    apply_line_modifications(lines, to_insert_lines, to_delete_lines)

def write_output_file(file_path: str, lines: List[str]) -> None:
    """write the output file"""
    try:
        with open(file_path,"w") as f:
            f.write("\n".join(lines))
    except Exception as e:
        print (f"Error when writing {file_path}: {str(e)}")
        exit(4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", help="The path to the source file to read from.")
    parser.add_argument("output_file", help="The path to the destination file to write to.")

    args = parser.parse_args()

    # Read configuration
    conditional_lookup=load_config("conditionals.yaml")

    # Read the input file
    lines=read_input_file(args.input_file)

    # Parse for blocks and conditionals
    indexer=AsciiDocIndexer(lines)

    # process the conditionals
    process_conditionals(lines, indexer, conditional_lookup)

    # write output file
    write_output_file(args.output_file, lines)

if __name__ == "__main__":
    main()
