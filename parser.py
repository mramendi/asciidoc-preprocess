from line_types import Line, State, StateType, StateSubtype, StateStack
from typing import Optional, List, Dict, Any
import logging
import re
import regexes

logger = logging.getLogger(__name__)


class Parsed:
    """The full parsed text of an Asciidoc module"""

    # Generation of unique IDs for lines. When processing original text, the line id should
    # be the line number. Then there is a large base for ids of additional lines.
    # IMPORTANT: there is NO guarantee of continuous or sequential line IDs in total
    # however the original lines can be acesed by original IDs - but handle skips gracefully (intercept KeyError)
    _next_line_id = 1 # for reference - this is also repeated in __init__
    ADDED_LINE_START = 10000
    last_original_id = -1
    _updating_last_original_id = True

    def _new_line_id(self) -> int:
        """Get next line ID and increment counter"""
        line_id = self._next_line_id
        self._next_line_id += 1
        return line_id

    def _original_text_processed(self):
        self._updating_last_original_id = False
        if self._next_line_id > self.ADDED_LINE_START:
            logger.warning(f"maximum line id is {self._next_line_id-1}, did not jump line ID")
        else:
            self._next_line_id = self.ADDED_LINE_START

    # direct list-like access to lines

    def __getitem__(self, index):
          """Allow parsed[1] to access parsed.lines[1]"""
          return self.lines[index]

    def __len__(self):
          """Allow len(parsed) to work"""
          return len(self.lines)
    
    def __setitem__(self, index, value):
        """Allow parsed[5] = new_line"""
        self.lines[index] = value

    def __delitem__(self, index):
        """Allow del parsed[5]"""
        del self.lines[index]

    def __iter__(self):
        """Make iteration explicit"""
        return iter(self.lines)
    
    # work with lines in the list

    def create_line(self, content: str) -> Line:
        return Line(id=self._new_line_id(), content=content)
 

    def index(self, line: Line) -> int:
        """Find the index of a Line object. Raises ValueError if not found."""
        return self.lines.index(line)

    def insert_before(self, target_line: Line, new_line: Line):
        """Insert a new line before the target line"""
        index = self.lines.index(target_line)
        self.lines.insert(index, new_line)

    def insert_after(self, target_line: Line, new_line: Line):
        """Insert a new line after the target line"""
        index = self.lines.index(target_line)
        self.lines.insert(index + 1, new_line)

    def create_line_before(self, target_line: Line, content: str) -> Line:
        """Create a new line and insert it before the target line. Returns the created line."""
        new_line = self.create_line(content)
        self.insert_before(target_line, new_line)
        return new_line

    def create_line_after(self, target_line: Line, content: str) -> Line:
        """Create a new line and insert it after the target line. Returns the created line."""
        new_line = self.create_line(content)
        self.insert_after(target_line, new_line)
        return new_line

    def remove(self, line: Line):
        """Remove a line from the document"""
        self.lines.remove(line)


    def line_by_id(self, line_id: int) -> Line:
        """Find a Line object by its id. Raises KeyError if not found."""
        for line in self.lines:
            if line.id == line_id:
                return line
        raise KeyError(f"No line with id {line_id} found in document")

    def remove_by_id(self, line_id: int):
        """Remove a line from the document by line ID"""
        self.lines.remove(self.line_by_id(line_id))


    def previous_line(self, line: Line) -> Optional[Line]:
        """Get the previous line in the document. Returns None if this is the first line.
           Raises KeyError if the line is not in the document."""
        try:
            index = self.lines.index(line)
        except ValueError:
            raise KeyError(f"Line {line.id} not found in document")

        if index == 0:
            return None
        return self.lines[index - 1]

    def next_line(self, line: Line) -> Optional[Line]:
        """Get the next line in the document. Returns None if this is the last line.
           Raises KeyError if the line is not in the document."""
        try:
            index = self.lines.index(line)
        except ValueError:
            raise KeyError(f"Line {line.id} not found in document")

        if index == len(self.lines) - 1:
            return None
        return self.lines[index + 1]

    def pretty(self) -> str:
        """Return a readable representation of the parsed document for debugging"""
        result = []
        result.append("=" * 80)
        result.append("PARSED DOCUMENT")
        result.append("=" * 80)
        for line in self.lines:
            result.append(line.pretty())
        result.append("=" * 80)
        return "\n".join(result)


    # PARSING - the core logic

    def _parse_line(self, content: str, starting_state_stack: StateStack) -> StateStack:
        """parse a single line, creating the state stack for it.
           Uses the state stack created by parsing the previous line
           At the first line of the Asciidoc text, the state starts with a blank stack
           NOTE: conditional lines are mostly-ignored at this stage"""
        # Check for mistaken passing of states that are not intended to be passed to the next line
        if (top_starting_state := starting_state_stack.top()):
            if (top_starting_state.type in [StateType.CONDITIONAL, StateType.BLOCK_PREFIX, 
                                           StateType.SECTION_HEADER] or
               top_starting_state.subtype == StateSubtype.JOINER):
                 raise ValueError(f"Invalid top state passed to parse_line: {top_starting_state}")
                  
        # create the Line object and add it to the lines list
        clean_text = content.replace("\n","")
        line = self.create_line(clean_text)
        self.lines.append(line)
        if self._updating_last_original_id:
            self.last_original_id = line.id

        # first check if this is a conditional
        if (conditional_match := regexes.CONDITIONAL.match(content)):
            operator = conditional_match.group(1)  # ifdef, ifndef, endif, ifeval
            expression_before = conditional_match.group(2)  # before []
            expression_inside = conditional_match.group(3)  # inside []

            # Determine subtype and params
            params = {}
            if operator == "endif":
                subtype = StateSubtype.END
                # Walk backwards to find matching START
                logger.debug("Walking back...")
                for i in range(len(self.lines) - 2, -1, -1):
                    prev_line = self.lines[i]
                    logger.debug(f"Checking line: {prev_line.content}")
                    if (prev_line.state_stack.top().type == StateType.CONDITIONAL and
                        prev_line.state_stack.top().subtype == StateSubtype.START and
                        prev_line.state_stack.top().get("end_line") == -1):
                        # Found the matching start
                        prev_line.state_stack.top()["end_line"] = line.id
                        params["start_line"] = prev_line.id
                        break
                else:
                    # No matching start found
                    logger.warning(f"endif without matching ifdef/ifndef/ifeval on line {line.id}")
            elif operator in ["ifdef", "ifndef"] and expression_before.strip() and expression_inside.strip():
                # Single-line conditional: has content both before and inside []
                subtype = StateSubtype.SINGLE_LINE
                params = {
                    "operator": operator,
                    "expression": expression_before,
                    "content": expression_inside
                }
            else:
                # START
                subtype = StateSubtype.START
                # Extract the meaningful expression
                if operator in ["ifdef", "ifndef"]:
                    expression = expression_before
                else:  # ifeval
                    expression = expression_inside
                params = {
                    "expression": expression,
                    "operator": operator,
                    "end_line": -1
                }

            line.state_stack.copy(starting_state_stack)
            line.state_stack.push(State(StateType.CONDITIONAL, subtype, params))
            return starting_state_stack


        # check for closing of the top delimited block, if available
        if (delimiter := starting_state_stack.top_delimiter()):
            if clean_text == delimiter:
                # The state of the line is the end delimiter in that delimited block
                line.state_stack.copy(starting_state_stack)
                line.state_stack.pop_until_delimited_block(inclusive = False)
                delim_state = line.state_stack.pop()
                # set the block_end_line paraneter on the start line state
                block_start_line = self.line_by_id(delim_state.get("block_start_line"))
                block_start_line.state_stack.top().parameters["block_end_line"] = line.id

                result_state_stack = line.state_stack.duplicate()
                delim_state.subtype = StateSubtype.END
                line.state_stack.push(delim_state)
                return result_state_stack

        # Table content parsing - simplified boundary detection
        if (starting_state_stack.top().type == StateType.DELIMITED_BLOCK and
            starting_state_stack.top().subtype == StateSubtype.TABLE):

            table_state = starting_state_stack.top()
            table_format = table_state.get("format")
            expected_col_count = table_state.get("expected_col_count", -1)
            current_col = table_state.get("current_col", 0)

            # Determine delimiter character and regex
            if table_format == 'psv':
                delim_char = '|'
                delim_regex = re.compile(r'(?<!\\)\|')
            elif table_format == 'csv':
                delim_char = ','
                delim_regex = re.compile(r',')
            else:
                raise RuntimeError(f"Unsupported table format: {table_format}")

            # Find all delimiters on this line
            delimiters = list(delim_regex.finditer(clean_text))

            if not delimiters:
                # No delimiters - line is fully inside a cell
                line.state_stack.copy(starting_state_stack)
                line.state_stack.push(State(StateType.IN_TABLE, StateSubtype.IN_CELL, {}))
                return starting_state_stack

            # Count columns added by this line (including colspan)
            # Also track ALL row boundaries (could be multiple per line)
            cols_on_line = 0
            boundary_delim_indices = []  # List of delimiter indices that trigger row boundaries
            rowspans_to_save = {}  # {col_idx: remaining_rows} for cells with rowspan

            for idx, delim_match in enumerate(delimiters):
                # Parse cell spec BEFORE this delimiter
                # Cell spec format: [multiplier*][colspan][.rowspan][+|*][align][style]|content
                # The spec is the text immediately before the |

                if idx == 0:
                    # First delimiter - spec is from start of line
                    spec_text = clean_text[:delim_match.start()]
                else:
                    # Subsequent delimiter - spec is from previous delimiter's end
                    prev_delim_end = delimiters[idx-1].end()
                    spec_text = clean_text[prev_delim_end:delim_match.start()]

                # Match cell spec at END of spec_text (just before the |)
                spec_text = spec_text.rstrip()

                colspan = 1
                rowspan = 1
                # Cell spec pattern: [colspan][.rowspan]+
                # Examples: "2+" (colspan=2), "3.2+" (colspan=3, rowspan=2), ".2+" (rowspan=2)
                spec_pattern = re.search(r'(\d+(?:\.\d+)?|\.\d+)\+\s*$', spec_text)
                if spec_pattern:
                    span_spec = spec_pattern.group(1)
                    if '.' in span_spec:
                        parts = span_spec.split('.')
                        if parts[0]:  # colspan.rowspan (e.g., "3.2+")
                            colspan = int(parts[0])
                        if parts[1]:  # Handle both "3.2+" and ".2+" cases
                            rowspan = int(parts[1])
                    else:  # Just colspan (e.g., "2+")
                        colspan = int(span_spec)

                    # Save rowspan for next row's column offset
                    if rowspan > 1:
                        col_idx = current_col + cols_on_line
                        rowspans_to_save[col_idx] = rowspan - 1

                # Check if adding this cell crosses the expected column count
                if expected_col_count > 0 and current_col + cols_on_line + colspan >= expected_col_count:
                    # ROW BOUNDARY - this delimiter completes a row
                    boundary_delim_indices.append(idx)
                    # Reset for next row (columns after this boundary)
                    cols_on_line = 0
                    current_col = 0

                cols_on_line += colspan

            # Handle implicit column inference (line starting with delimiter after first row accumulation)
            if expected_col_count == -1 and current_col > 0 and clean_text.lstrip().startswith(delim_char):
                # Infer column count from accumulated cells
                expected_col_count = current_col
                table_state.parameters["expected_col_count"] = expected_col_count
                logger.info(f"Inferred {expected_col_count} columns from first table row at line {line.id}")
                boundary_delim_indices = [0]  # First delimiter is the boundary

            if boundary_delim_indices:
                # ROW_BOUNDARY - determine content before/after
                # Note: If multiple boundaries exist, both flags are automatically True
                if len(boundary_delim_indices) > 1:
                    # Multiple row boundaries on this line - content exists between them
                    has_content_before = True
                    has_content_after = True
                    # Use LAST boundary for next row calculation
                    last_boundary_idx = boundary_delim_indices[-1]
                else:
                    # Single row boundary - check content before/after
                    boundary_delim_idx = boundary_delim_indices[0]
                    boundary_delim = delimiters[boundary_delim_idx]
                    boundary_pos = boundary_delim.start()

                    # Check content BEFORE boundary
                    # Content before includes all text/delimiters before this boundary delimiter
                    # Exclude whitespace and cell spec modifiers (the colspan/rowspan before the delimiter)
                    if boundary_delim_idx == 0:
                        # Boundary is first delimiter - check if anything before it
                        text_before = clean_text[:boundary_pos].strip()
                        # Remove cell spec pattern from end
                        text_before = re.sub(r'(\d+(?:\.\d+)?|\.\d+)\+\s*$', '', text_before).strip()
                        has_content_before = bool(text_before)
                    else:
                        # Boundary is not first delimiter - previous delimiters count as content
                        has_content_before = True

                    # Check content AFTER boundary
                    # Content after includes all text/delimiters after this boundary delimiter
                    has_content_after = bool(clean_text[boundary_delim.end():].strip()) or len(delimiters[boundary_delim_idx+1:]) > 0

                    last_boundary_idx = boundary_delim_idx

                # Emit ROW_BOUNDARY state
                line.state_stack.copy(starting_state_stack)
                line.state_stack.push(State(StateType.IN_TABLE, StateSubtype.ROW_BOUNDARY, {
                    "content_before": has_content_before,
                    "content_after": has_content_after
                }))

                # Update state for next line - reset to start of new row
                result_state_stack = starting_state_stack.duplicate()
                table_state = result_state_stack.top()

                # Count columns after LAST boundary (for next row's starting position)
                # Note: boundary delimiter itself starts a cell in the new row
                cols_after_boundary = 0
                for idx in range(last_boundary_idx, len(delimiters)):
                    delim_match = delimiters[idx]

                    # Parse cell spec BEFORE this delimiter
                    if idx == 0:
                        spec_text = clean_text[:delim_match.start()]
                    else:
                        prev_delim_end = delimiters[idx-1].end()
                        spec_text = clean_text[prev_delim_end:delim_match.start()].rstrip()

                    # Extract colspan (ignore rowspan for column counting after boundary)
                    colspan = 1
                    spec_pattern = re.search(r'(\d+(?:\.\d+)?|\.\d+)\+\s*$', spec_text)
                    if spec_pattern:
                        span_spec = spec_pattern.group(1)
                        if '.' in span_spec:
                            parts = span_spec.split('.')
                            if parts[0]:  # colspan.rowspan (e.g., "3.2+")
                                colspan = int(parts[0])
                            # else: .rowspan (e.g., ".2+") → colspan stays 1
                        else:  # Just colspan (e.g., "2+")
                            colspan = int(span_spec)

                    cols_after_boundary += colspan

                # Save rowspans for next row's column counting
                if rowspans_to_save:
                    table_state.parameters["rowspans"] = rowspans_to_save

                table_state.parameters["current_col"] = cols_after_boundary
                return result_state_stack

            else:
                # CELL_BOUNDARY - has delimiters but no row boundary
                line.state_stack.copy(starting_state_stack)
                line.state_stack.push(State(StateType.IN_TABLE, StateSubtype.CELL_BOUNDARY, {}))

                # Update column counter for next line
                result_state_stack = starting_state_stack.duplicate()
                table_state = result_state_stack.top()
                table_state.parameters["current_col"] = current_col + cols_on_line
                return result_state_stack

        # If we were verbatim: as we already checked for a closing delimiter, we continue the state and return
        if starting_state_stack.top().subtype == StateSubtype.VERBATIM:
            line.state_stack.copy(starting_state_stack)
            return starting_state_stack
        
        # process a line comment
        if clean_text.startswith("//") and (len(clean_text)<=4 or
                                            clean_text[2:4]!="//"):
            line.state_stack.copy(starting_state_stack)
            line.state_stack.push(State(StateType.LINE_COMMENT, StateSubtype.NORMAL))
            return starting_state_stack
        
        # process an attribute definition
        if regexes.ATTRIBUTE_DEFINITION.match(clean_text):
            line.state_stack.copy(starting_state_stack)
            line.state_stack.push(State(StateType.ATTRIBUTE_DEFINITION, StateSubtype.NORMAL))
            return starting_state_stack


        # Process a delimiter starting a new block
        if (delimiter := regexes.is_delimiter(clean_text)):

            # determine the first line of the new block - this line or pull in any immediately preceding block prefixes
            first_line = line.id

            # NOT SURE if I need to include block prefixes in first_line calculation - for now, commented out
#            potential_prefix_line = self.previous_line(line)
#            while potential_prefix_line and potential_prefix_line.state_stack.top().type == StateType.BLOCK_PREFIX:
#                first_line = potential_prefix_line.id
#                potential_prefix_line = self.previous_line(potential_prefix_line)

            block_param = {"delimiter": delimiter, "block_start_line": first_line}

            result_state_stack = starting_state_stack.duplicate()
            # if we are in a paragraph, terminate the paragraph, reverting to the state under it
            if result_state_stack.top().type == StateType.PARAGRAPH:
                result_state_stack.pop()
            # if we are in a list item right after a joiner, this is a joined block
            # in a list in any other place: terminate the list item and any list items under it
            if result_state_stack.top().type == StateType.LIST_ITEM:
                if result_state_stack.top().subtype == StateSubtype.JOINED_FIRST_LINE:
                    list_state = result_state_stack.pop()
                    list_state.subtype = StateSubtype.JOINED_DELIMITED_BLOCK
                    result_state_stack.push(list_state)
                else:
                    while result_state_stack.top().type == StateType.LIST_ITEM:
                        result_state_stack.pop()
                        # Note - this is expected to reach a root or delimited block
                        # if this reaches an empty state it is an error and the exceptiom is correct

            line.state_stack.copy(result_state_stack)
            line.state_stack.push(State(StateType.DELIMITED_BLOCK, StateSubtype.START, block_param))

            # Check if this is a parseable table (PSV/CSV)
            tbl_format = regexes.table_format(delimiter)
            if tbl_format:
                # Parseable table - extract column count if available
                # Walk backwards through blank lines, comments, conditionals, block prefixes
                cols_attr = None
                walk_line = self.previous_line(line)
                while walk_line:
                    top_state = walk_line.state_stack.top()
                    # Skip blank lines and special lines
                    if (walk_line.content.strip() == "" or
                        top_state.type == StateType.CONDITIONAL or
                        top_state.type == StateType.LINE_COMMENT or
                        top_state.type == StateType.ATTRIBUTE_DEFINITION):
                        walk_line = self.previous_line(walk_line)
                        continue

                    # Check for block attributes
                    if (top_state.type == StateType.BLOCK_PREFIX and
                        top_state.subtype == StateSubtype.BLOCK_ATTRIBUTES):
                        # Extract cols attribute from block attributes line
                        # Format: [cols="...",other="..."]
                        match = re.search(r'cols="([^"]+)"', walk_line.content)
                        if match:
                            cols_attr = match.group(1)
                            break
                        # Found block attributes but no cols - continue searching
                        walk_line = self.previous_line(walk_line)
                        continue

                    # Check for block title - can be between attributes and delimiter
                    if (top_state.type == StateType.BLOCK_PREFIX and
                        top_state.subtype == StateSubtype.BLOCK_TITLE):
                        walk_line = self.previous_line(walk_line)
                        continue

                    # Hit content line - stop searching
                    break

                # Create table parameters
                table_param = {
                    "delimiter": delimiter,
                    "block_start_line": first_line,
                    "format": tbl_format,
                    "expected_col_count": self._parse_table_cols_count(cols_attr) if cols_attr else -1,
                    "current_col": 0,
                    "rowspans": {},  # Track active rowspans {col_idx: remaining_rows}
                }

                # Push DELIMITED_BLOCK/TABLE state
                result_state_stack.push(State(StateType.DELIMITED_BLOCK, StateSubtype.TABLE, table_param))
                return result_state_stack
            else:
                # Non-table delimiter - use existing logic
                subtype = StateSubtype.VERBATIM if regexes.is_delimiter_verbatim(delimiter) else StateSubtype.NORMAL
                result_state_stack.push(State(StateType.DELIMITED_BLOCK, subtype, block_param))
                return result_state_stack

        # Process a blank line
        if clean_text == "":
            if starting_state_stack.top().type == StateType.PARAGRAPH:
                # a blank line terminates a paragraph, reinstating the state immediately underlying it
                result_state_stack=starting_state_stack.duplicate()
                result_state_stack.pop()
                line.state_stack.copy(result_state_stack)
                return result_state_stack
            if starting_state_stack.top().type == StateType.LIST_ITEM:
                # blank line terminates a list item, but, in itself, not yet the list
                # except if the current state is "right after a joiner" it can be ancestor list continuation
                new_state_stack = starting_state_stack.duplicate()
                list_state = new_state_stack.pop()
                if list_state.subtype == StateSubtype.JOINED_FIRST_LINE:
                    if new_state_stack.top() and new_state_stack.top().type == StateType.LIST_ITEM:
                        # ancestor list continuation, see documentation:
                        # https://docs.asciidoctor.org/asciidoc/latest/lists/continuation/#ancestor-list-continuation
                        ancestor_list_state = new_state_stack.pop()
                        current_line_list_state = ancestor_list_state.duplicate()
                        current_line_list_state.subtype = StateSubtype.JOINER
                        line.state_stack.copy(new_state_stack)
                        line.state_stack.push(current_line_list_state)
                        ancestor_list_state.subtype = StateSubtype.JOINED_FIRST_LINE
                        new_state_stack.push(ancestor_list_state)
                        return new_state_stack
                        
                list_state.subtype = StateSubtype.TERMINATED
                new_state_stack.push(list_state)
                line.state_stack.copy(new_state_stack)
                return new_state_stack
            # At this point, we are processing a blank line and the state type is ROOT or DELIMITED_BLOCK
            # In this case the state does not change
            line.state_stack.copy(starting_state_stack)
            return starting_state_stack

        # Continuation marker (+) - only valid in list item context
        # NOT valid if the list item is terminated
        # However if there was a delimited block in the list item, a + is valid after it
        # That is what the JOINED_DELIMITED_BLOCK state is for
        if clean_text == "+":
            if (starting_state_stack.top().type == StateType.LIST_ITEM and 
                starting_state_stack.top().subtype != StateSubtype.TERMINATED):
                # Warn if we're already in a joined state
                if starting_state_stack.top().subtype == StateSubtype.JOINED_FIRST_LINE:
                    logger.warning(f"+ continuation marker immediately after another + on line {line.id}")

                # The + line gets marked with JOINER subtype
                result_state_stack = starting_state_stack.duplicate()
                list_item_state = result_state_stack.pop()

                # Mark this line as JOINER
                line_list_item_state = list_item_state.duplicate()
                line_list_item_state.subtype = StateSubtype.JOINER
                line.state_stack.copy(result_state_stack)
                line.state_stack.push(line_list_item_state)

                # For the next line, transition to JOINED_FIRST_LINE
                list_item_state.subtype = StateSubtype.JOINED_FIRST_LINE
                result_state_stack.push(list_item_state)
                return result_state_stack
            # If not in list item context, fall through to treat as regular content
            else:
                logger.warning(f"single + is not a valid joiner, line {line.id}")

        # Block attribute line
        if clean_text.startswith("[") and clean_text.endswith("]"):
            new_state_stack = starting_state_stack.duplicate()

            if new_state_stack.top().type == StateType.PARAGRAPH:
                # A paragraph is ended, reinstating the state immediately underlying it
                new_state_stack.pop()
            elif new_state_stack.top().type == StateType.LIST_ITEM:
                # A list item is continued, but if inside a joined paragraph, a new joined paragraph begins
                # note that an existing JOINED_FIRST_LINE state is continued - handled by the default case below
                # TODO: investigate what happens right after a joined delim block
                if new_state_stack.top().subtype == StateSubtype.JOINED_NORMAL:
                    list_item_state = new_state_stack.pop()
                    list_item_state.subtype = StateSubtype.JOINED_FIRST_LINE
                    new_state_stack.push(list_item_state) 
                    # this does mean both the block prefix line and the line after it get JOINED_FIRST_LINE
                    # at this moment I see no cleaner way to handle this 
                    # note the top state for the block prefix is BLOCK_PREFIX
            line.state_stack.copy(new_state_stack)
            line.state_stack.push(State(StateType.BLOCK_PREFIX,StateSubtype.BLOCK_ATTRIBUTES))
            return new_state_stack
        

        # List item start - note these do NOT work in-paragraph
        if ((list_match := regexes.LIST_ITEM.match(clean_text)) and 
            starting_state_stack.top().type != StateType.PARAGRAPH):
            list_marker = list_match.group(1)  # Extract the actual marker string ("*", "**", ".", etc.)
            existing_list_state_stack_base = None
            existing_list_state = None
            if starting_state_stack.top().type == StateType.LIST_ITEM:
                # check if we might already be inside this type of list
                # Importantly not just this one list but any encompassing lists - up to either root or delimiter block

                analysis_state_stack = starting_state_stack.duplicate()
                analysis_state = analysis_state_stack.pop()
                while not (analysis_state.type in [StateType.ROOT, StateType.DELIMITED_BLOCK]):
                    if analysis_state.type == StateType.LIST_ITEM and analysis_state.get("marker") == list_marker:
                        existing_list_state_stack_base = analysis_state_stack
                        existing_list_state = analysis_state
                        break
                    analysis_state = analysis_state_stack.pop()
            # at this point if an existing list is applicable the correct state for it is in
            # existing_list_state and the lower levels for it in existing_list_state_stack_base
            if existing_list_state_stack_base and existing_list_state:
                existing_list_state.subtype = StateSubtype.FIRST_LINE
                existing_list_state.parameters["item_start_line"] = line.id
                next_line_list_state = existing_list_state.duplicate()
                next_line_list_state.subtype = StateSubtype.NORMAL
                line.state_stack.copy(existing_list_state_stack_base)
                line.state_stack.push(existing_list_state)
                result_state_stack = existing_list_state_stack_base # just for clarity - still same object
                result_state_stack.push(next_line_list_state)
                return result_state_stack
            # if we reached this point, we are starting a new list on top of existing state stack
            # Note: if the existing state is a list item, its subtype is not checked
            # This doesn't really matter as the list items are ended together
            # ...except for ancestor list continuation where the subtype is reset anyway 
            new_list_state = State(StateType.LIST_ITEM, StateSubtype.FIRST_LINE,
                                   {"list_start_line": line.id, "item_start_line": line.id, "marker": list_marker})
            next_line_list_state = new_list_state.duplicate()
            next_line_list_state.subtype = StateSubtype.NORMAL
            result_state_stack = starting_state_stack.duplicate()
            line.state_stack.copy(result_state_stack)
            line.state_stack.push(new_list_state)
            result_state_stack.push(next_line_list_state)
            return result_state_stack

        # Block title line
        if len(clean_text)>1 and clean_text.startswith(".") and not clean_text[1].isspace() and clean_text[1]!=".":
            if starting_state_stack.top().type in [StateType.ROOT, StateType.DELIMITED_BLOCK]:
                # A block title is always a block title in root or in base delimiter block
                line.state_stack.copy(starting_state_stack)
                line.state_stack.push(State(StateType.BLOCK_PREFIX,StateSubtype.BLOCK_TITLE))
                return starting_state_stack
            # In a paragraph a like that looks like a block title line is NOT a block title, so no need to process here
            # Inside a list item it works the same way, BUT in a joint list paragraph it marks a new joint paragraph
            # (if subtype is JOINED_FIRST_LINE it can also be the block title for a delimited block,
            #   which is processed by keeping JOINED_FIRST_LINE for both this and next line)
            # ...and if the list item is terminated, a block title terminates the list!
            # TODO: investigate what happens right after a joined delim block
            if starting_state_stack.top().type == StateType.LIST_ITEM:
                if starting_state_stack.top().subtype in [StateSubtype.JOINED_FIRST_LINE, StateSubtype.JOINED_NORMAL]:
                    new_state_stack = starting_state_stack.duplicate()
                    line_item_state = new_state_stack.pop()
                    line_item_state.subtype = StateSubtype.JOINED_FIRST_LINE
                    new_state_stack.push(line_item_state)
                    # this does mean both the block prefix line and the line after it get JOINED_FIRST_LINE
                    # at this moment I see no cleaner way to handle this 
                    # note the top state for the block prefix is BLOCK_PREFIX
                    line.state_stack.copy(new_state_stack)
                    line.state_stack.push(State(StateType.BLOCK_PREFIX,StateSubtype.BLOCK_TITLE))
                    return new_state_stack
                if starting_state_stack.top().subtype == StateSubtype.TERMINATED:
                    # Terminate the list and all list under it
                    result_state_stack = starting_state_stack.duplicate()
                    while result_state_stack.top().type == StateType.LIST_ITEM:
                        result_state_stack.pop()
                    line.state_stack.copy(result_state_stack)
                    line.state_stack.push(State(StateType.BLOCK_PREFIX,StateSubtype.BLOCK_TITLE))
                    return result_state_stack

        # Section header line - warn if not in root; mark line, pass thru state
        # Is only processed in root, delimited block, and after a terminated list item/after delim block (terminates list)
        # can't condition header lines but this comes later
        # We use new_state_stack as the flag - if it's assigned the header line is actually a header line
        if (header_match := regexes.SECTION_HEADER.match(clean_text)):
            level = len(header_match.group(1))  # Count the = signs to get level

            new_state_stack = None
            if (starting_state_stack.top().type == StateType.LIST_ITEM and
                starting_state_stack.top().subtype in [StateSubtype.TERMINATED, StateSubtype.JOINED_DELIMITED_BLOCK] ):
                new_state_stack = starting_state_stack.duplicate()
                # Terminate the list and all list under it
                while new_state_stack.top().type == StateType.LIST_ITEM:
                    new_state_stack.pop()
            elif starting_state_stack.top().type in [StateType.ROOT, StateType.DELIMITED_BLOCK]:
                new_state_stack = starting_state_stack.duplicate()
            if new_state_stack:
                if new_state_stack.top().type == StateType.DELIMITED_BLOCK:
                    logger.warning(f"Section title inside delimited block on line {line.id}")

                # Walk backwards to find section end boundary and close previous sections
                # First, find the first non-blank, non-comment, non-attribute-block, non-conditional line
                section_end_line_id = None
                walk_line = self.previous_line(line)
                while walk_line:
                    top_state = walk_line.state_stack.top()
                    if not (walk_line.content.strip() == "" or
                            top_state.type == StateType.CONDITIONAL or
                            top_state.type == StateType.LINE_COMMENT or
                            top_state.type == StateType.ATTRIBUTE_DEFINITION or
                            (top_state.type == StateType.BLOCK_PREFIX and
                             top_state.subtype == StateSubtype.BLOCK_ATTRIBUTES)):
                        # This is the first content line before the section
                        section_end_line_id = walk_line.id
                        break
                    walk_line = self.previous_line(walk_line)

                # Now continue walking back to find previous section headers to close
                while walk_line:
                    top_state = walk_line.state_stack.top()
                    if top_state.type == StateType.SECTION_HEADER:
                        if top_state.get("end_line") == -1:
                            # This section is still open
                            walk_level = top_state.get("level")
                            if walk_level is not None and walk_level >= level:
                                # Same or lower level (numerically same or higher) - close it
                                top_state.parameters["end_line"] = section_end_line_id
                    walk_line = self.previous_line(walk_line)

                line.state_stack.copy(new_state_stack)
                line.state_stack.push(State(StateType.SECTION_HEADER, StateSubtype.NORMAL,
                                           {"level": level, "end_line": -1}))
                return new_state_stack

        # if we are here, this is just a normal line, not a list item start, not an empty line, etc
        # If we are in a paragraph the line continues the state
        if starting_state_stack.top().type == StateType.PARAGRAPH:
            line.state_stack.copy(starting_state_stack)
            return starting_state_stack

        # If in a list item:
        #    - in most subtypes continue the same state
        #    - if JOINED_FIRST_LINE was the starting state, use it, mark first line id, continue with JOINED_NORMAL
        #    - if terminated or after a joined delimited block, terminate all lists then new paragraph
        result_state_stack = starting_state_stack.duplicate()
        if starting_state_stack.top().type == StateType.LIST_ITEM:
            if starting_state_stack.top().subtype in [StateSubtype.JOINED_DELIMITED_BLOCK,
                                                      StateSubtype.TERMINATED]:
                # Pop all lists from new_state_stack
                while result_state_stack.top().type == StateType.LIST_ITEM:
                    result_state_stack.pop()
                # note we do NOT return so the process continues to creating a new paragraph
            elif (starting_state_stack.top().type == StateType.LIST_ITEM and
                    starting_state_stack.top().subtype == StateSubtype.JOINED_FIRST_LINE):
                    list_item_state = result_state_stack.pop()
                    list_item_state.parameters["joined_start_line"] = line.id
                    next_line_list_item_state = list_item_state.duplicate()
                    next_line_list_item_state.subtype = StateSubtype.JOINED_NORMAL
                    line.state_stack.copy(result_state_stack)
                    line.state_stack.push(list_item_state)
                    result_state_stack.push(next_line_list_item_state)
                    return result_state_stack
            
            else: 
                line.state_stack.copy(starting_state_stack)
                return starting_state_stack

        # at this point we are in root or a delimited block, or we have just terminated a list
        #  so this line starts a paragraph
        paragraph_state = State(StateType.PARAGRAPH, StateSubtype.FIRST_LINE, {"first_line": line.id})
        next_line_paragraph_state = paragraph_state.duplicate()
        next_line_paragraph_state.subtype = StateSubtype.NORMAL
        line.state_stack.copy(result_state_stack)
        line.state_stack.push(paragraph_state)
        result_state_stack.push(next_line_paragraph_state)
        return result_state_stack

    def _parse_table_cols_count(self, cols_attr: str) -> int:
        """Extract column count from cols attribute.

        Format: "3" or "3*" or "1,2,3" - returns number of columns
        Ignores alignment/style modifiers - we only need the count.
        """
        if not cols_attr:
            return -1  # Implicit columns

        # Handle bare number: "3" means 3 columns
        if cols_attr.isdigit():
            return int(cols_attr)

        # Handle repeat syntax: "3*" means 3 columns
        match = re.match(r'(\d+)\*', cols_attr)
        if match:
            return int(match.group(1))

        # Count comma/semicolon-separated specs
        specs = [s.strip() for s in re.split(r'[,;]', cols_attr) if s.strip()]
        return len(specs)

    def __init__(self, lines: List[str]):
        self.last_original_id = -1
        self._updating_last_original_id = True

        self._next_line_id = 1
        self.lines = []
        running_state_stack = StateStack()
        running_state_stack.push(State(StateType.ROOT, StateSubtype.NORMAL))
        for line in lines:
            logger.debug(f"Starting state stack: {running_state_stack.pretty()}")
            logger.debug(f"Line: {line.rstrip()}")
            running_state_stack = self._parse_line(line, running_state_stack)
            logger.debug(f"Last line state stack: {self.lines[-1].state_stack.pretty()}")

        # Close any remaining open sections by walking backwards from EOF
        # Find the last non-blank, non-comment, non-attribute-block, non-conditional line
        last_content_line_id = None
        for walk_line in reversed(self.lines):
            top_state = walk_line.state_stack.top()
            if not (walk_line.content.strip() == "" or
                    top_state.type == StateType.CONDITIONAL or
                    top_state.type == StateType.LINE_COMMENT or
                    top_state.type == StateType.ATTRIBUTE_DEFINITION or
                    (top_state.type == StateType.BLOCK_PREFIX and
                     top_state.subtype == StateSubtype.BLOCK_ATTRIBUTES)):
                last_content_line_id = walk_line.id
                break

        # Now close all open sections
        if last_content_line_id is not None:
            for walk_line in self.lines:
                top_state = walk_line.state_stack.top()
                if (top_state.type == StateType.SECTION_HEADER and
                    top_state.get("end_line") == -1):
                    top_state.parameters["end_line"] = last_content_line_id

        self._original_text_processed()

        # Validation: ensure no line has an empty state stack (logic error if so)
        for line in self.lines:
            if len(line.state_stack) == 0:
                raise RuntimeError(
                    f"Logic error: Line {line.id} has empty state stack. "
                    f"Content: '{line.content}'"
                )








                
                




        







