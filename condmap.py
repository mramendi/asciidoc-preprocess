from parser import Parsed
from line_types import Line, State, StateType, StateSubtype, StateStack
from typing import Optional, List, Set
from enum import Enum, auto
from dataclasses import dataclass
import logging
import regexes

logger = logging.getLogger(__name__)

class ConditionalType(Enum):
    """ types of conditionals 
        note absence of INVALID - invalid conditionals are just not processed"""
    PARTIAL = auto() # any part of one paragraph or part of a list item that does NOT start with a first line
    PART_START_LIST_ITEM = auto() # a part of a list item that starts with a first line
    SINGLE_LIST_ITEM = auto() # exactly one list item, nothing joined
    GROUP_START_LIST_ITEM = auto() # one of several list item starts with common continuation
    BLOCKS = auto () # any number 

@dataclass
class Conditional:
    type: ConditionalType
    start_id: int
    end_id: int
    values: Set[str]


class ConditionalsMap:
    conditionals: List[Conditional] = [] # type hint for IDE
    def __init__(self, parsed: Parsed, values: Set[str]):
        self.parsed = parsed
        self.conditionals = []
        self.values = values
        self._make_map()

    def pretty(self) -> str:
        """Return a pretty-printed representation of the conditionals map"""
        if not self.conditionals:
            return "No conditionals found"

        result = []
        result.append("=" * 80)
        result.append("CONDITIONALS MAP")
        result.append("=" * 80)
        for cond in self.conditionals:
            values_str = ", ".join(sorted(cond.values))
            result.append(f"{cond.type.name}: lines {cond.start_id}-{cond.end_id}, values: {values_str}")
        result.append("=" * 80)
        return "\n".join(result)

    def _warn_about_nested(self, start_line: Line, end_line: Line):
        """go through lines from the start to the end index
           if any conditional starts on them warn it is nested and so unsupported"""
        start_idx = self.parsed.index(start_line)
        end_idx = self.parsed.index(end_line)
        if end_idx < start_idx:
            raise RuntimeError(f"_warn_about_nested called with start_idx {start_idx} > end_idx {end_idx}")
        idx = start_idx
        while idx <= end_idx:
            line = self.parsed.lines[idx]
            if (line.state_stack.top().type == StateType.CONDITIONAL and 
                line.state_stack.top().subtype != StateSubtype.END):
                logger.warning(f"Conditional at line {line.id} is nested - unsupported")
            if line.state_stack.top().type == StateType.SECTION_HEADER:
                logger.warning(f"Section header confitioned at line {line.id} - result is uncertain!")
            idx += 1


    def _make_map(self):
        idx = 1
        end_ids_unsupported = []
        while idx < len(self.parsed.lines):
            start_line: Line = self.parsed.lines[idx]

            logger.debug(f"Processing line index {idx}, id {start_line.id}")

            top_state = start_line.state_stack.top()
            if top_state.type != StateType.CONDITIONAL:
                # the line is not a conditional marker and we are outside any conditional markers
                idx+=1
                continue

            logger.debug(f"  Found conditional at line {start_line.id}")

            # at this point the line at idx is a conditional
            # if it is a single-line - ignore with a warning
            if top_state.subtype == StateSubtype.SINGLE_LINE:
                logger.debug(f"  Skipping SINGLE_LINE conditional")
                logger.warning(f"Single-line conditional ignored, line {start_line.id}")
                idx+=1
                continue

            # if it is an end, we somehow did not see the start, output a warning
            # ...except if this is the end of an unsupported conditional, just skip it
            if top_state.subtype == StateSubtype.END:
                if not start_line.id in end_ids_unsupported:
                    logger.debug(f"  Unmatched END conditional")
                    logger.warning(f"endif encountered with no pair, line {start_line.id}")
                else:
                    logger.debug(f"  Skipping END of unsupported conditional")
                idx+=1
                continue

            # subtype is START at this point, so an end line should be present
            end_line_id = top_state.get("end_line")
            if (end_line_id is None) or (end_line_id == -1):
                logger.warning(f"conditional with no endif line found - skipped, line {start_line.id}")
                idx += 1
                continue
            end_line = self.parsed.line_by_id(end_line_id)

            # if it is an ifeval, it is not supported
            operator = top_state.get("operator")
            if operator == "ifeval":
                logger.debug(f"  Skipping ifeval (unsupported)")
                logger.warning(f"ifeval is unsupported, line {start_line.id}")
                end_ids_unsupported.append(end_line_id)
                idx+=1
                continue

            # parse the expression now
            expression = top_state.get("expression")
            if not expression:
                logger.debug(f"  Skipping (no expression)")
                logger.warning(f"could not get the expression for ifdef/endif, line {start_line.id}")
                end_ids_unsupported.append(end_line_id)
                idx+=1
                continue

            logger.debug(f"  Processing {operator}::{expression}[], lines {start_line.id}-{end_line_id}")
            # if a + is used: we don't support this logic currently
            if "+" in expression:
                logger.warning(f"ifdef/ifndef expression using + unsupported, line {start_line.id}")
                end_ids_unsupported.append(end_line_id)
                idx+=1
                continue

            # now the expression should be just one attribute or a few split by "," 
            condition_values=set([attr.strip() for attr in expression.split(",") if attr.strip()])
            if not condition_values.issubset(self.values):
                logger.warning(f"ifdef/ifndef expression {expression} uses undefined value - unsupported, line {start_line.id}")
                end_ids_unsupported.append(end_line_id)
                idx+=1
                continue
            # revert the values if ifndef
            if operator == "ifndef":
                condition_values = self.values - condition_values

            # if the delimited block stack situation is different, unsupported
            if start_line.state_stack.until_delim_or_root() != end_line.state_stack.until_delim_or_root():
                logger.debug(f"  Skipping (crosses delimited block boundary)")
                logger.warning(f"lines {start_line.id} and {end_line_id} are in different delimited block positions - unsupported")
                end_ids_unsupported.append(end_line_id)
                idx+=1
                continue


            # check what is in the PREVIOUS line
            prev_line = self.parsed.previous_line(start_line)
            if prev_line: # note it might be None in case the conditional starts on line 1
                prev_line_top_state = prev_line.state_stack.top()
                # if it is a block attribute line - no support; 
                #  for a block title line it is only "no support" if the first line starts a block
                if prev_line_top_state.type == StateType.BLOCK_PREFIX:
                    if prev_line_top_state.subtype == StateSubtype.BLOCK_ATTRIBUTES:
                        logger.warning(f"[Block attributes] immediately before conditional at line {start_line.id} - unsupported")
                        end_ids_unsupported.append(end_line_id)
                        idx+=1
                        continue
                    if prev_line_top_state.subtype == StateSubtype.BLOCK_TITLE:
                        next_line = self.parsed.next_line(start_line)
                        if next_line.state_stack.top().type == StateType.DELIMITED_BLOCK:
                            logger.warning(f"Conditional cuts .BlockTitle off delimited block at line {start_line.id} - unsupported")
                            end_ids_unsupported.append(end_line_id)
                            idx+=1
                            continue
        
            # get the first and last lines within the conditioned block, first check for empty
            first_line = self.parsed.next_line(start_line)
            if first_line == end_line:
                logger.warning(f"Empty conditional at line {start_line.id} - unsupported")
                # just skip past the end
                idx = self.parsed.index(end_line)+1
                continue
            last_line = self.parsed.previous_line(end_line)
            # note that first_line and last_line CAN be the same, the subsequent logic should be robust to this
            first_line_top_state = first_line.state_stack.top()
            last_line_top_state = last_line.state_stack.top()

            # find the last NON-BLANK line - important for evaluating partials
            # TODO: this logic is NOT robust to comments in some places
            last_non_blank_line = last_line
            while last_non_blank_line.content.strip() == "":
                if last_non_blank_line == first_line:
                    logger.warning(f"Conditional of blanks at line {idx} - unsupported")
                    # just skip past the end
                    idx = self.parsed.index(end_line)+1
                    continue
                last_non_blank_line = self.parsed.previous_line(last_non_blank_line)

            # for several cases we want to know the next line 
            # (that is not a conditional or attribute line or comment or blank) 
            # note the line might not even exist (end of file)
            next_line = self.parsed.next_line(end_line)
            while (next_line and ((next_line.content.strip() =="") or
                next_line.state_stack.top().type in [StateType.CONDITIONAL,
                                                    StateType.LINE_COMMENT,
                                                    StateType.ATTRIBUTE_DEFINITION])):
                next_line = self.parsed.next_line(next_line)
            if next_line:
                next_line_state_stack = next_line.state_stack.duplicate()
            else:
                next_line_state_stack = None # Fail loudly if we didn't check next_line exists



            # Process a partial that is clearly a partial from the start side
            # So mid-paragraph or mid-list-item
            if (((first_line_top_state.type,first_line_top_state.subtype) ==
                 (StateType.PARAGRAPH, StateSubtype.NORMAL)) or (
                     first_line_top_state.type == StateType.LIST_ITEM and
                     not first_line_top_state.subtype in [StateSubtype.FIRST_LINE,
                                                          StateSubtype.TERMINATED,
                                                           StateSubtype.JOINED_DELIMITED_BLOCK ])):
                 # TODO this makes starting/ending on a joiner unsupported, maybe add some way for it

                 # this works as a partial if the last non-blank line has the exact same state
                 if first_line.state_stack == last_non_blank_line.state_stack :
                    logger.debug(f"  Classified as PARTIAL: lines {start_line.id}-{end_line_id}")
                    cond = Conditional(type = ConditionalType.PARTIAL,
                                        start_id = start_line.id,
                                        end_id = end_line_id,
                                        values = condition_values)
                    self.conditionals.append(cond)
                    self._warn_about_nested(first_line, last_line)
                    idx = self.parsed.index(end_line)+1
                    continue
                 else:
                    logger.warning(f"Conditional starts mid-paragraph/list item and includes several items, lines {start_line.id}  - unsupported")
                    end_ids_unsupported.append(end_line_id)
                    idx+=1
                    continue 

            # now the special versions that start exactly on a list item start
            # and the last line is still in the same item and is not blank
            # they are special because they can lead into the grouped special case
            # we also detect the group special case here
            if (((first_line_top_state.type,first_line_top_state.subtype) == 
                (StateType.LIST_ITEM, StateSubtype.FIRST_LINE)) and 
                (last_line_top_state == first_line_top_state)): 

                # we already know the last conditioned ine is in this same list item
                # now we want to know if the next line 
                # (that is not a conditional or attribute line or comment or blank) 
                # is parsed as a part of this same list item
                # note the line ight not even exist (end of file) in which cases this is
                # a complete list item
                next_line = self.parsed.next_line(end_line)
                while (next_line and ((next_line.content.strip() =="") or
                   next_line.state_stack.top().type in [StateType.CONDITIONAL,
                                                        StateType.LINE_COMMENT,
                                                        StateType.ATTRIBUTE_DEFINITION])):
                    next_line = self.parsed.next_line(next_line)

                part_start_list_item = False

                if next_line:
                    next_line_state_stack_copy = next_line_state_stack.duplicate()
                    test_state = next_line_state_stack_copy.pop()
                    if test_state.type == StateType.DELIMITED_BLOCK: # this one might be on top of the list item
                        test_state = next_line_state_stack_copy.pop()
                    if test_state.type == StateType.LIST_ITEM:
                        if test_state.get("item_start_line") == first_line_top_state.get("item_start_line"):
                            part_start_list_item = True

                if not part_start_list_item:
                    logger.debug(f"  Classified as SINGLE_LIST_ITEM: lines {start_line.id}-{end_line_id}")
                    cond = Conditional(type = ConditionalType.SINGLE_LIST_ITEM,
                                        start_id = start_line.id,
                                        end_id = end_line_id,
                                        values = condition_values)
                    self.conditionals.append(cond)
                    self._warn_about_nested(first_line, last_line)
                    idx = self.parsed.index(end_line)+1
                    continue
                # we do have a partial start of list item - work out if there are grouped versions
                # a group must have strictly no lines in between conditionals
                # this allows us a backward pass on self.conditionals with strict criteria
                group = False
                potential_last_line_id = self.parsed.previous_line(start_line).id
                for cond_idx in range(len(self.conditionals)-1,-1,-1):
                    if self.conditionals[cond_idx].end_id != potential_last_line_id:
                        break
                    if self.conditionals[cond_idx].type != ConditionalType.SINGLE_LIST_ITEM:
                        break
                    group = True
                    self.conditionals[cond_idx].type = ConditionalType.GROUP_START_LIST_ITEM
                if group:
                    type = ConditionalType.GROUP_START_LIST_ITEM
                else:
                    type = ConditionalType.PART_START_LIST_ITEM

                logger.debug(f"  Classified as {type.name}: lines {start_line.id}-{end_line_id}")
                cond = Conditional(type = type,
                    start_id = start_line.id,
                    end_id = end_line_id,
                    values = condition_values)
                self.conditionals.append(cond)
                self._warn_about_nested(first_line, last_line)
                idx = self.parsed.index(end_line)+1
                continue

            # At this point we should be at the start of a block/paragraph/list item
            # we need to work out if the end is a clean division (or EOF)
            # if it is we have a standard blockwise conditional
            breaking_boundary = False
            if last_line_top_state.type == StateType.PARAGRAPH and next_line:
                if (next_line_state_stack.top().type == StateType.PARAGRAPH and
                    next_line_state_stack.top().subtype != StateSubtype.FIRST_LINE):
                    breaking_boundary = True
            elif last_line_top_state.type == StateType.LIST_ITEM and next_line:
                # work out if the next line is in the same list item
                # note that the next line light start a delimited block inside this list item
                next_line_state_stack_copy = next_line_state_stack.duplicate()
                test_state = next_line_state_stack_copy.pop()
                if test_state.type == StateType.DELIMITED_BLOCK: # this one might be on top of the list item
                    test_state = next_line_state_stack_copy.pop()
                if test_state.type == StateType.LIST_ITEM:
                    if test_state.get("item_start_line") == first_line_top_state.get("item_start_line"):
                        breaking_boundary = True

            if not breaking_boundary:
                # normal block style conditional
                logger.debug(f"  Classified as BLOCKS: lines {start_line.id}-{end_line_id}")
                cond = Conditional(type = ConditionalType.BLOCKS,
                                    start_id = start_line.id,
                                    end_id = end_line_id,
                                    values = condition_values)
                self.conditionals.append(cond)
                self._warn_about_nested(first_line, last_line)
                idx = self.parsed.index(end_line)+1
                continue

            # the boundary is broken at the end, while we have a clean start at the start
            # this can still be a partial at the start of a pargraph
            # (valid partials at the start of a list item were handled above)
            if first_line_top_state.type == StateType.PARAGRAPH:
                if last_line_top_state.type == StateType.PARAGRAPH:
                    if last_line_top_state.get("start_line") == first_line_top_state.get("start_line"):
                        logger.debug(f"  Classified as PARTIAL (paragraph start): lines {start_line.id}-{end_line_id}")
                        cond = Conditional(type = ConditionalType.PARTIAL,
                            start_id = start_line.id,
                            end_id = end_line_id,
                            values = condition_values)
                        self.conditionals.append(cond)
                        self._warn_about_nested(first_line, last_line)
                        idx = self.parsed.index(end_line)+1
                        continue       

            # if we reach this place, the conditional is not supported
            logger.debug(f"  Skipping (breaks boundary, includes multiple items)")
            logger.warning(f"Conditional ends mid-paragraph/list item and includes several items, line {start_line.id}  - unsupported")
            end_ids_unsupported.append(end_line_id)
            idx+=1
            continue 




                
                

                
  
        



