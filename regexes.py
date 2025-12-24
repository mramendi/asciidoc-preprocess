import re
from typing import Optional

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

# Table opener  |===  !=== ,=== :===
TABLE_DELIM = re.compile(r'''
    ^              # start of line
    ([|!,:])      # group 1: exactly one of |  !  ,  :
    ={3,}          # followed by at least three equals signs
    [ \t]*         # optional trailing whitespace
    $              # nothing else allowed
''', re.VERBOSE)

# IMPORTANT: the open block delimiter `--` also exists, to be detected by trivial comparison

# Delimiter detector helper
def is_delimiter(content: str) -> Optional[str]:
    """
    Check if content is a delimiter.
    Returns the delimiter string if it is, None otherwise.
    """
    stripped = content.rstrip()

    # Check for open block delimiter (exactly "--")
    if stripped == "--":
        return stripped

    # Check for four-or-more delimiter
    if FOUR_MORE_DELIM.match(stripped):
        return stripped

    # Check for table delimiter
    if TABLE_DELIM.match(stripped):
        return stripped

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