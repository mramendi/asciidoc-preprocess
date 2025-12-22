from line_types import Line, State, StateType, StateSubtype, StateStack
from typing import Optional, List
import regexes


class Parsed:
    """The full parsed text of an Asciidoc module"""

    # Generation of unique IDs for lines. When processing original text, the line id should
    # be the line number. Then there is a large base for ids of additional lines.
    # IMPORTANT: there is NO guarantee of continuous or sequential line IDs
    _next_line_id = 1 # for reference - this is also repeated in __init__
    ADDED_LINE_START = 10000

    def _new_line_id(self) -> int:
        """Get next line ID and increment counter"""
        line_id = self._next_line_id
        self._next_line_id += 1
        return line_id

    def _original_text_processed(self):
        if self._next_line_id > self.ADDED_LINE_START:
            print(f"WARNING: maximum line id is {self._next_line_id-1}, did not jump line ID")
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

    def remove(self, line: Line):
        """Remove a line from the document"""
        self.lines.remove(line)

    def line_by_id(self, line_id: int) -> Line:
        """Find a Line object by its id. Raises KeyError if not found."""
        for line in self.lines:
            if line.id == line_id:
                return line
        raise KeyError(f"No line with id {line_id} found in document")

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
        clean_text = content.rstrip()
        line = self.create_line(clean_text)
        self.lines.append(line)

        # first check if this is a conditional - we mostly ignore those for now
        if (conditional_match := regexes.CONDITIONAL.match(content)):
            subtype = StateSubtype.END if conditional_match.group(1) == "endif" else StateSubtype.START
            line.state_stack.push(State(StateType.CONDITIONAL, subtype))
            return starting_state_stack


        # check for closing of the top delimited block, if available
        if (delimiter := starting_state_stack.top_delimiter()):
            if clean_text == delimiter:
                # The sate of the line is the end deimiter in that delimited block
                line.state_stack.copy(starting_state_stack)
                line.state_stack.pop_until_delimited_block(inclusive = False)
                delim_state = line.state_stack.pop()
                result_state_stack = line.state_stack.duplicate()
                delim_state.subtype = StateSubtype.END
                line.state_stack.push(delim_state)
                return result_state_stack

        # If we were verbatim: as we already checked for a closing delimiter, we continue the state and return
        if starting_state_stack.top().subtype == StateSubtype.VERBATIM:
            line.state_stack.copy(starting_state_stack)
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

            block_param = {"delimiter": delimiter, "first_line": first_line}

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
                    print(f"WARNING: + continuation marker immediately after another + on line {line.id}")

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
                print(f"Warning: single + is not a valid joiner, line {line.id}")

        # Block attribute line
        if clean_text.startswith("[") and clean_text.endswith("]"):
            new_state_stack = starting_state_stack.duplicate()

            if new_state_stack.top().type == StateType.PARAGRAPH:
                # A paragraph is ended, reinstating the state immediately underlying it
                new_state_stack.pop()
            elif new_state_stack.top().type == StateType.LIST_ITEM:
                # A list item is continued, but if inside a joined paragraph, a new joined paragraph begins
                # note that an existing JOINED_FIRST_LINE state is continued - handled by the default case below
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
                                   {"list_start_line": line.id, "marker": list_marker})
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
        # Is only processed in root, delimited block, and after a terminated list item (terminates list) 
        # can't condition header lines but this comes later
        # We use new_state_stack as the flag - if it's assigned the header line is actually a header line
        if regexes.SECTION_HEADER.match(clean_text):
            new_state_stack = None
            if (starting_state_stack.top().type == StateType.LIST_ITEM and
                starting_state_stack.top().subtype == StateSubtype.TERMINATED):
                new_state_stack = starting_state_stack.duplicate()
                # Terminate the list and all list under it
                while new_state_stack.top().type == StateType.LIST_ITEM:
                    new_state_stack.pop()
            elif starting_state_stack.top().type in [StateType.ROOT, StateType.DELIMITED_BLOCK]:
                new_state_stack = starting_state_stack.duplicate()
            if new_state_stack:
                if new_state_stack.top().type == StateType.DELIMITED_BLOCK:
                    print(f"WARNING: Section title inside delimited block on line {line.id}")
                line.state_stack.copy(new_state_stack)
                line.state_stack.push(State(StateType.SECTION_HEADER,StateSubtype.NORMAL))
                return new_state_stack

        # if we are here, this is just a normal line, not a list item start, not an empty line, etc
        # If we are in a paragraph the line continues the state
        if starting_state_stack.top().type == StateType.PARAGRAPH:
            line.state_stack.copy(starting_state_stack)
            return starting_state_stack

        # If in a list item:
        #    - in most subtypes continue the same state
        #    - if JOINED_FIRST_LINE was the starting state, use it but continue with JOINED_NORMAL
        #    - if terminated or after a joined delimited block, terminate all lists then new paragraph
        result_state_stack = starting_state_stack.duplicate()
        if starting_state_stack.top().type == StateType.LIST_ITEM:
            if starting_state_stack.top().subtype in [StateSubtype.JOINED_DELIMITED_BLOCK,
                                                      StateSubtype.TERMINATED]:
                # Pop all lists from new_state_stack
                while result_state_stack.top().type == StateType.LIST_ITEM:
                    result_state_stack.pop()
                # note we do NOT return so the process continues to creating a new paragraph
            else: 
                line.state_stack.copy(starting_state_stack)
                # Special case: transition from JOINED_FIRST_LINE to JOINED_NORMAL
                if (starting_state_stack.top().type == StateType.LIST_ITEM and
                    starting_state_stack.top().subtype == StateSubtype.JOINED_FIRST_LINE):
                    list_item_state = result_state_stack.pop()
                    list_item_state.subtype = StateSubtype.JOINED_NORMAL
                    result_state_stack.push(list_item_state)
                    return result_state_stack

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
    
    def __init__(self, lines: List[str]):
        self._next_line_id = 1
        self.lines = []
        running_state_stack = StateStack()
        running_state_stack.push(State(StateType.ROOT, StateSubtype.NORMAL))
        for line in lines:
            running_state_stack = self._parse_line(line, running_state_stack)
        self._original_text_processed()

        # Validation: ensure no line has an empty state stack (logic error if so)
        for line in self.lines:
            if len(line.state_stack) == 0:
                raise RuntimeError(
                    f"Logic error: Line {line.id} has empty state stack. "
                    f"Content: '{line.content}'"
                )








                
                




        







