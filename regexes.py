import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class DelimiterType(Enum):
    """Types of delimiters."""
    NORMAL = auto()      # Regular delimited blocks (e.g., ----)
    VERBATIM = auto()    # Verbatim blocks (e.g., ===, ****, ++++, ____)
    TABLE = auto()       # Table blocks (e.g., |===, ,===, !===, :===)


@dataclass
class DelimiterInfo:
    """Information about a detected delimiter."""
    delimiter: str
    type: DelimiterType


CONDITIONAL = re.compile(r'''
      ^                           # start of line
      (ifdef|ifndef|endif|ifeval) # group 1: directive type
      ::                          # literal double colon
      ([^\[\]]*)                  # group 2: expression before brackets (possibly empty)
      \[                          # opening bracket
      ([^\]]*)                    # group 3: content inside brackets (possibly empty)
      \]                          # closing bracket
      (.*)                        # group 4: trailing content (comments, whitespace, etc.)
      $                           # end of line
  ''', re.VERBOSE)

#  Usage:

#   m = _CONDITIONAL.match(line.content)
#   if m:
#       directive = m.group(1)      # 'ifdef', 'ifndef', 'endif', 'ifeval'
#       expr_before = m.group(2)    # Expression before brackets
#       expr_inside = m.group(3)    # Expression inside brackets
#       trailing = m.group(4)       # Any trailing content

#       # Determine the actual expression based on directive type
#       if directive == 'ifeval':
#           expression = expr_inside  # ifeval uses inside brackets
#       else:
#           # ifdef/ifndef/endif typically use before brackets
#           # but endif can use either
#           expression = expr_before if expr_before else expr_inside


# Typical block delimiter: four-or-more *identical* supported chars:  = * _ - . / +
#    Line must contain ONLY that delimiter + optional trailing spaces.
FOUR_MORE_DELIM = re.compile(r'''
    ^                    # start of line
    (                    # group 1: the delimiter character
        [=*_\-\./+]         #   exactly one of the supported chars
    )
    \1{3,}               # that same char at least three more times → 4+
    [ \t]*               # optional trailing whitespace
    $                    # nothing else
''', re.VERBOSE)

# Table delimiter pattern - matches all table formats
# PSV (|), CSV (,), DSV (!), TSV (:)
TABLE_DELIM = re.compile(r'''
    ^              # start of line
    ([|,!:])       # group 1: table delimiter character
    ={3,}          # followed by at least three equals signs
    [ \t]*         # optional trailing whitespace
    $              # nothing else allowed
''', re.VERBOSE)

# IMPORTANT: the open block delimiter `--` also exists, to be detected by trivial comparison

# Delimiter detector helper
def is_delimiter(content: str) -> Optional[str]:
    """
    Check if content is a non-table delimiter.
    Returns the delimiter string if it is, None otherwise.
    Does NOT return table delimiters - use is_table_delimiter() for those.
    """
    stripped = content.rstrip()

    # Check for open block delimiter (exactly "--")
    if stripped == "--":
        return stripped

    # Check for four-or-more delimiter (but NOT table delimiters)
    if FOUR_MORE_DELIM.match(stripped):
        return stripped
    
    # Check for a table delimiter

    if (result := is_table_delimiter(content)):
        return result

    return None

def is_table_delimiter(content: str) -> Optional[str]:
    """
    Check if content is a table delimiter.
    Returns the delimiter string if it is, None otherwise.
    Matches: |=== (PSV), ,=== (CSV), !==== (DSV), :=== (TSV)
    Caller can check delimiter[0] to determine format.
    """
    stripped = content.rstrip()

    if TABLE_DELIM.match(stripped):
        return stripped

    return None

def get_delimiter_info(content: str) -> Optional[DelimiterInfo]:
    """
    Check if content is a delimiter and determine its type.
    Returns DelimiterInfo with delimiter string and type, or None.

    Delimiter types:
    - NORMAL: Regular delimited blocks (----, etc.)
    - VERBATIM: Verbatim blocks (====, ****, ++++, ____)
    - TABLE: Table blocks (|===, ,===, !===, :===)
    """
    stripped = content.rstrip()

    # Check for open block delimiter (exactly "--")
    if stripped == "--":
        return DelimiterInfo(stripped, DelimiterType.NORMAL)

    # Check for table delimiter
    if TABLE_DELIM.match(stripped):
        return DelimiterInfo(stripped, DelimiterType.TABLE)

    # Check for four-or-more delimiter
    if FOUR_MORE_DELIM.match(stripped):
        # Determine if verbatim
        if is_delimiter_verbatim(stripped):
            return DelimiterInfo(stripped, DelimiterType.VERBATIM)
        else:
            return DelimiterInfo(stripped, DelimiterType.NORMAL)

    return None

def is_delimiter_verbatim(delimiter: str) -> bool:
    """Checks if a delimiter denotes a verbatim block.
    TODO: temporarily tables are considered verbatim blocks
    IMPORTANT: Does NOT check what is passed is actually a valid delimiter"""
    if delimiter == "--":
        return False
    if delimiter[0] in ["-", "+", "/", "."]: 
        return True
    # TODO temporarily marking table as verbatim
    if delimiter[0] in ["!", ":", ",", "|"]: 
        return True
    return False

SECTION_HEADER = re.compile(r'''                                                                                                                                                                                                                                                       
      ^                # start of line                                                                                                                                                                                                                                                   
      (={1,6})         # group 1: section level (1-6 equals signs)                                                                                                                                                                                                                       
      [ \t]+           # required whitespace after level marker                                                                                                                                                                                                                          
      (.+?)            # group 2: section title text (non-greedy)                                                                                                                                                                                                                        
      (?:              # optional non-capturing group for trailing equals                                                                                                                                                                                                                
        [ \t]+         #   whitespace before trailing marker                                                                                                                                                                                                                             
        =+             #   one or more trailing equals signs                                                                                                                                                                                                                             
      )?               # end optional group                                                                                                                                                                                                                                              
      [ \t]*           # optional trailing whitespace                                                                                                                                                                                                                                    
      $                # end of line                                                                                                                                                                                                                                                     
  ''', re.VERBOSE)                                                                                                                                                                                                                                                                       
                                                                                                                                                                                                                                                                                         
"""   Usage:                                                                                                                                                                                                                                                                                 
  m = SECTION_HEADER.match(line)                                                                                                                                                                                                                                                         
  if m:                                                                                                                                                                                                                                                                                  
      level_marker = m.group(1)  # '=', '==', '===', etc.                                                                                                                                                                                                                                
      level = len(level_marker)   # 1-6                                                                                                                                                                                                                                                  
      title = m.group(2)          # 'Section Title'                                                                                                                                                                                                                                      
                                                                                                                                                                                                                                                                                         
  Examples that match:                                                                                                                                                                                                                                                                   
  - = Document Title → level 1 (document title)                                                                                                                                                                                                                                          
  - == Section → level 2                                                                                                                                                                                                                                                                 
  - === Subsection === → level 3 (with trailing equals)                                                                                                                                                                                                                                  
  - ==== Chapter     → level 4 (with trailing whitespace)                                                                                                                                                                                                                                
                                                                                                                                                                                                                                                                                         
  Does NOT match:                                                                                                                                                                                                                                                                        
  - ======= (7 equals - too many)                                                                                                                                                                                                                                                        
  - =NoSpace (missing required space after =)                                                                                                                                                                                                                                            
  - Lines without equals at the start   """

LIST_ITEM = re.compile(r'''                                                                                                                                                                                                                                                            
      ^                # start of line                                                                                                                                                                                                                                                   
      (                # group 1: list marker                                                                                                                                                                                                                                            
        \*+            #   one or more asterisks (unordered)                                                                                                                                                                                                                             
        |              #   OR                                                                                                                                                                                                                                                            
        \.+            #   one or more dots (ordered)                                                                                                                                                                                                                                    
      )                                                                                                                                                                                                                                                                                  
      [ \t]+           # required whitespace after marker                                                                                                                                                                                                                                
      (.*)             # group 2: list item content (can be empty)                                                                                                                                                                                                                       
      $                # end of line                                                                                                                                                                                                                                                     
  ''', re.VERBOSE)                                                                                                                                                                                                                                                                       
                                                                                                                                                                                                                                                                                         
"""   Usage:                                                                                                                                                                                                                                                                                 
  m = LIST_ITEM.match(line)                                                                                                                                                                                                                                                              
  if m:                                                                                                                                                                                                                                                                                  
      marker = m.group(1)        # '*', '**', '.', '..', etc.                                                                                                                                                                                                                            
      content = m.group(2)       # 'Item text'                                                                                                                                                                                                                                           
                                                                                                                                                                                                                                                                                         
      # Determine type and level                                                                                                                                                                                                                                                         
      if marker[0] == '*':                                                                                                                                                                                                                                                               
          list_type = 'unordered'                                                                                                                                                                                                                                                        
          level = len(marker)    # *, **, *** = levels 1, 2, 3                                                                                                                                                                                                                           
      else:  # marker[0] == '.'                                                                                                                                                                                                                                                          
          list_type = 'ordered'                                                                                                                                                                                                                                                          
          level = len(marker)    # ., .., ... = levels 1, 2, 3                                                                                                                                                                                                                           
                                                                                                                                                                                                                                                                                         
  Examples that match:                                                                                                                                                                                                                                                                   
  - * Item → unordered level 1                                                                                                                                                                                                                                                           
  - ** Nested → unordered level 2                                                                                                                                                                                                                                                        
  - *** Deep → unordered level 3                                                                                                                                                                                                                                                         
  - . First → ordered level 1                                                                                                                                                                                                                                                            
  - .. Nested → ordered level 2                                                                                                                                                                                                                                                          
  - *  → unordered with empty content                                                                                                                                                                                                                                                    
                                                                                                                                                                                                                                                                                         
  Does NOT match:
  - *NoSpace (missing required space)
  -  * Item (leading whitespace - not plain)
  - - Item (dash marker - not supported)     """

ATTRIBUTE_DEFINITION = re.compile(r'''
    ^                # start of line
    :                # opening colon
    (!)?             # group 1: optional ! for unsetting
    ([a-zA-Z0-9_-]+) # group 2: attribute name (alphanumeric, hyphens, underscores)
    :                # closing colon
    (.*)             # group 3: attribute value (possibly empty)
    $                # end of line
''', re.VERBOSE)

"""   Usage:
  m = ATTRIBUTE_DEFINITION.match(line)
  if m:
      unset_flag = m.group(1)    # '!' or None
      attr_name = m.group(2)     # 'attr-name'
      attr_value = m.group(3)    # ' value' or ''

      # Strip leading whitespace from value
      value = attr_value.lstrip() if attr_value else ''

  Examples that match:
  - :attr-name: → unset/empty attribute
  - :attr-name: value → set attribute with value
  - :!attr-name: → unset attribute (alternative syntax)
  - :version: 1.0 → attribute 'version' = '1.0'
  - :toc: left → attribute 'toc' = 'left'

  Does NOT match:
  - attr-name: value (missing leading colon)
  - :attr name: value (space in attribute name)
  - Lines that don't start with :     """

def parse_block_attributes(line: str) -> dict[str, str]:
    """
    Parse AsciiDoc block attributes from a line like [attr1="value1", attr2=value2].

    Returns a dictionary of attribute names to values.
    Ignores non-attribute items like .role, [[id]], etc.
    Handles commas inside quoted values correctly.

    Examples:
        parse_block_attributes('[format="csv", options="header"]')
        → {'format': 'csv', 'options': 'header'}

        parse_block_attributes('[.role,cols="2,1"]')
        → {'cols': '2,1'}

        parse_block_attributes('[cols="1,1,2"]')
        → {'cols': '1,1,2'}
    """
    # Strip whitespace and outer brackets
    line = line.strip()
    if line.startswith('[') and line.endswith(']'):
        line = line[1:-1]

    result = {}

    # Split on commas, but not commas inside quotes
    # Parse character by character to handle quoted values
    parts = []
    current_part = []
    in_quotes = False
    quote_char = None

    for char in line:
        if char in ('"', "'") and not in_quotes:
            in_quotes = True
            quote_char = char
            current_part.append(char)
        elif char == quote_char and in_quotes:
            in_quotes = False
            quote_char = None
            current_part.append(char)
        elif char == ',' and not in_quotes:
            parts.append(''.join(current_part))
            current_part = []
        else:
            current_part.append(char)

    # Don't forget the last part
    if current_part:
        parts.append(''.join(current_part))

    # Now parse each part for key=value
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Check if it's a key=value pair
        if '=' in part:
            key, _, value = part.partition('=')
            key = key.strip()
            value = value.strip()

            # Remove quotes from value if present
            if value and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]

            result[key] = value

    return result

def parse_table_cols_count(self, cols_attr: str) -> int:
    """Extract column count from the value of a cols attribute for an Asciidoc table.
       IMPORTANT: assumes the value is not blank, as a blank value is ignored by Asciidoctor
    """

    if cols_attr.isdigit():
        return int(cols_attr)

    specs = re.split(r'[,;]', cols_attr)
    count = 0
    for spec in specs:
        sp = spec.strip()
        if (len(sp) > 1) and (sp[-1] == "*") and (sp[:-1].isdigit()):
            count += int(sp[:-1])
        else:
            count+=1
    return count

# Regular expressions for parsing table specs
# Extracted from Asciidoctor using Claude Code
"""
  Capture Groups (same for both START and END)                                                                                                                                                                                                               
                  
  Group 1: Number (optional)                                                                                                                                                                                                                                 
  - Pattern: (\d+(?:\.\d*)?|(?:\d*\.)?\d+)
  - Examples: 2, 3.2, .5, 2.                                                                                                                                                                                                                                 
  - Used for: colspan/rowspan (when with +) or repeat count (when with *)
  - Can contain a dot for separate col/row values: 2.3 means col=2, row=3                                                                                                                                                                                    
                                                                                                                                                                                                                                                             
  Group 2: Operator (optional)                                                                                                                                                                                                                               
  - Pattern: ([*+])                                                                                                                                                                                                                                          
  - Values: * or +                                                                                                                                                                                                                                           
  - Meaning:                                                                                                                                                                                                                                                 
    - + = span operator (colspan/rowspan)
    - * = repeat operator (repeat this cell N times)
                                                                                                                                                                                                                                                             
  Group 3: Alignment (optional)
  - Pattern: ([<^>](?:\.[<^>]?)?|(?:[<^>]?\.)?[<^>])?                                                                                                                                                                                                        
  - Values: <, ^, > (optionally with dot notation like <.^ or .>)                                                                                                                                                                                            
  - Used for: horizontal/vertical alignment                                                                                                                                                                                                                  
  - Can be split on . for horizontal.vertical: <.^ means halign=left, valign=middle                                                                                                                                                                          
                                                                                                                                                                                                                                                             
  Group 4: Style letter (optional)                                                                                                                                                                                                                           
  - Pattern: ([a-z])?                                                                                                                                                                                                                                        
  - Valid values: a, d, s, e, m, h, l (single letter only)                                                                                                                                                                                                   
  - Maps to cell styles (asciidoc, none, strong, emphasis, monospaced, header, literal)
                                                                                                                                                                                                                                                             
  Example Parsing                                                                                                                                                                                                                                            
                                                                                                                                                                                                                                                             
  # "2.3+<.^a" (colspan=2, rowspan=3, halign=left, valign=middle, style=asciidoc)                                                                                                                                                                            
  m = CELL_SPEC_END_RX.match(" 2.3+<.^a")                                                                                                                                                                                                                    
  # m.group(1) = "2.3"                                                                                                                                                                                                                                       
  # m.group(2) = "+"                                                                                                                                                                                                                                         
  # m.group(3) = "<.^"                                                                                                                                                                                                                                       
  # m.group(4) = "a"                                                                                                                                                                                                                                         
                                                                                                                                                                                                                                                             
  All four groups are optional, so " a" would give you groups: None, None, None, "a".  

"""

# For cellspecs at the END of cell content (so not the first delimiter on a line)                                                                                                                                                                                                      
CELL_SPEC_END_RX = re.compile(
    r'[ \t]+(?:(\d+(?:\.\d*)?|(?:\d*\.)?\d+)([*+]))?'
    r'([<^>](?:\.[<^>]?)?|(?:[<^>]?\.)?[<^>])?([a-z])?$'
)

# For cellspecs at the START of line (first delimiter on a line)
CELL_SPEC_START_RX = re.compile(
    r'^[ \t]*(?:(\d+(?:\.\d*)?|(?:\d*\.)?\d+)([*+]))?'
    r'([<^>](?:\.[<^>]?)?|(?:[<^>]?\.)?[<^>])?([a-z])?$'
)