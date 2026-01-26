#!/usr/bin/env python3
"""
Preprocess AsciiDoc files to handle conditional directives.
"""

import sys
import logging
import argparse
from parser import Parsed
from line_types import Line, State, StateType, StateSubtype, StateStack
from condmap import ConditionalsMap, ConditionalType
from typing import Set

logger = logging.getLogger(__name__)

ATTRIBUTE = "otherprops"

def dotroles(values: Set[str]) -> str:
    return ' '.join(["."+ATTRIBUTE+":"+x for x in values])

def attroles(values: Set[str]) -> str:
    return 'role="'+' '.join([ATTRIBUTE+":"+x for x in values])+'"'



def process_conditionals(parsed: Parsed, cond_map: ConditionalsMap):
    idx = 0
    while idx < len(cond_map.conditionals):
        cond = cond_map.conditionals[idx]
        logger.debug(f"Processing conditional {idx}: {cond.type.name}, lines {cond.start_id}-{cond.end_id}, values: {', '.join(sorted(cond.values))}")

        first_line = parsed.next_line(parsed.line_by_id(cond.start_id))
        last_line = parsed.previous_line(parsed.line_by_id(cond.end_id))

        if cond.type == ConditionalType.PARTIAL:
            logger.debug(f"  Branch: PARTIAL - adding inline roles")
            first_line.prepend("["+dotroles(cond.values)+"]#")
            last_line.append("#")
        elif cond.type == ConditionalType.PART_START_LIST_ITEM:
            logger.debug(f"  Branch: PART_START_LIST_ITEM - adding inline roles to partial list item")
            marker = first_line.state_stack.top().get("marker")
            if not marker:
                raise RuntimeError(f"Classified as PART_START_LIST_ITEM but no marker found in state, line {first_line.id}")
            content_after_marker = first_line.content[len(marker)+1:] # remove marker and space after it
            first_line.content = marker+" ["+dotroles(cond.values)+"]#"+content_after_marker
            last_line.append("#")
        elif cond.type == ConditionalType.GROUP_START_LIST_ITEM:
            logger.debug(f"  Branch: GROUP_START_LIST_ITEM - processing joint list item group")
            try:
                marker = first_line.state_stack.top().get("marker")
                if not marker:
                    raise RuntimeError(f"Classified as GROUP_START_LIST_ITEM but no marker found in state, line {first_line.id}")
                # this is the first one in the group so it does get the marker
                content_after_marker = first_line.content[len(marker)+1:] # remove marker and space after it
                first_line.content = marker+" ["+dotroles(cond.values)+"]#"+content_after_marker
                last_line.append("#")

                # find the next id after the end line
                next_line = parsed.next_line(parsed.line_by_id(cond.end_id))
                next_line_id = next_line.id

                # walk on to find the rest of the group
                idx += 1
                while (idx < len(cond_map.conditionals) and
                       cond_map.conditionals[idx].type == ConditionalType.GROUP_START_LIST_ITEM and
                       cond_map.conditionals[idx].start_id == next_line_id):

                    cond = cond_map.conditionals[idx]
                    first_line = parsed.next_line(parsed.line_by_id(cond.start_id))
                    last_line = parsed.previous_line(parsed.line_by_id(cond.end_id))

                    # error out if this does not have the same marker
                    if first_line.state_stack.top().get("marker") != marker:
                        raise RuntimeError(f"Classified as GROUP_START_LIST_ITEM but marker in state not the same as previous group member, line {first_line.id}")

                    # this is a subsequent group member so it gets its marker removed
                    content_after_marker = first_line.content[len(marker)+1:] # remove marker and space after it
                    first_line.content = "["+dotroles(cond.values)+"]#"+content_after_marker
                    last_line.append("#")

                    # Update next_line_id for next iteration
                    next_line = parsed.next_line(parsed.line_by_id(cond.end_id))
                    next_line_id = next_line.id
                    idx += 1

            except AttributeError as e:
                logger.error(f"GROUP_START_LIST_ITEM processing failed at line {cond.start_id}: likely hit EOF unexpectedly")
                logger.error(f"This suggests a logic error in conditional classification")
                raise

            continue # continue the loop immediately to avoid incrementing idx again
        else:
            # at this time the type is BLOCKS or SINGLE_LIST_ITEM and the processing is block-based
            # the meaning of SINGLE_LIST_ITEM as a separate category is all about
            # detecting groups, which is already done by now
            logger.debug(f"  Branch: {cond.type.name} - block-based processing")
            current_line = first_line
            block_attributes_set = False # flag that we used an existing block attributes line
            while current_line and (current_line.id != cond.end_id): # we process until we hit the endif
                current_line_top_state = current_line.state_stack.top()
                if ((current_line_top_state.type, current_line_top_state.subtype) ==
                    (StateType.BLOCK_PREFIX, StateSubtype.BLOCK_ATTRIBUTES)):
                    logger.debug(f"    Line {current_line.id}: Adding role to existing BLOCK_ATTRIBUTES")
                    # add role to an existing block attributes line
                    clean_text = current_line.content.rstrip()
                    if not clean_text.endswith("]"):
                        raise RuntimeError(f"Line marked BLOCK_ATTRIBUTES but not ending with ], line {current_line.id}")
                    current_line.content = clean_text[:-1]+","+attroles(cond.values)+"]" 
                    block_attributes_set = True
                elif ((current_line_top_state.type, current_line_top_state.subtype) ==
                    (StateType.BLOCK_PREFIX, StateSubtype.BLOCK_TITLE)):
                    logger.debug(f"    Line {current_line.id}: BLOCK_TITLE - creating attributes if needed")
                    # for a block title: set block attributes if not present,
                    # also assume attributes carry over to block below
                    if not block_attributes_set:
                        parsed.create_line_before(current_line, "["+attroles(cond.values)+"]")
                    block_attributes_set = True
                elif ((current_line_top_state.type, current_line_top_state.subtype) ==
                    (StateType.PARAGRAPH, StateSubtype.FIRST_LINE)):
                    logger.debug(f"    Line {current_line.id}: PARAGRAPH start - creating attributes if needed")
                    # start of paragraph - set block attributes if not present, consume block attributes
                    if not block_attributes_set:
                        parsed.create_line_before(current_line, "["+attroles(cond.values)+"]")
                    block_attributes_set = False
                elif ((current_line_top_state.type, current_line_top_state.subtype) ==
                    (StateType.DELIMITED_BLOCK, StateSubtype.START)):
                    logger.debug(f"    Line {current_line.id}: DELIMITED_BLOCK start - setting attributes if not comment, then jumping over block")
                    # start of delimited block - if not a comment, set block attributes if not present,
                    # consume block attributes,
                    # then (in all cases) jump after the end of the block
                    if current_line_top_state.get("delimiter")[0] != "/":
                        if not block_attributes_set:
                            parsed.create_line_before(current_line, "["+attroles(cond.values)+"]")
                        block_attributes_set = False
                    block_end_line_id = current_line_top_state.get("block_end_line")
                    if not block_end_line_id:
                        logger.warning(f"Block end not found from line {current_line.id}, results can be unpredictable")
                    else:
                        block_end_line = parsed.line_by_id(block_end_line_id)
                        current_line = parsed.next_line(block_end_line)
                        continue # immediately continue the loop as we jumped over the block
                elif ((current_line_top_state.type, current_line_top_state.subtype) ==
                    (StateType.LIST_ITEM, StateSubtype.FIRST_LINE)):
                    logger.debug(f"    Line {current_line.id}: LIST_ITEM start - checking if whole list or just item")
                    # start of list item
                    # here, we must check if the whole list is actually in the conditional
                    #  - but only if this is also the list start line
                    # In this case we jump over the list. So if we reach a list item where this is not the
                    #  list start line, we just conditionalize the item
                    # The logic is we check for whole-list first, and if we conditionalize it we jump oveer it and continue
                    # If we don't continue the loop we fall through to conditonalizing the item
                    if current_line_top_state.get("list_start_line") == current_line.id:
                        logger.debug(f"      This is the list start line - checking if entire list is conditioned")
                        # walk the lines of the list until they are either no longer in the list or we hit the endif
                        # if we encounter a delimited block in the list we jump over it - the endif should be after it,
                        #  because we checked delimited block state
                        complete_list = False
                        line_after_list = None
                        walking_line = parsed.next_line(current_line)
                        if not walking_line:
                            raise RuntimeError(f"While processing conditional from line {cond.start_id} we hit EOF - this should not happen")
                        while walking_line.id != cond.end_id:
                            if not walking_line:
                                raise RuntimeError(f"While processing conditional from line {cond.start_id} we hit EOF - this should not happen")
                            logger.debug(f"Walking line {walking_line.id}")
                            if ((walking_line.state_stack.top().type == StateType.LIST_ITEM) and
                                (walking_line.state_stack.top().get("list_start_line") == current_line.id)):
                                # we are still in the list, next line, continue
                                walking_line = parsed.next_line(walking_line)
                                continue
                            if walking_line.state_stack.top().type == StateType.DELIMITED_BLOCK:
                                analysis_state_stack = walking_line.state_stack.duplicate()
                                analysis_state_stack.pop() # see what is under the delimited block
                                if ((analysis_state_stack.top().type == StateType.LIST_ITEM) and
                                (analysis_state_stack.top().get("list_start_line") == current_line.id)):
                                    # the block is inside the list, jump over the block, continue
                                    block_end_line_id = walking_line.state_stack.top().get("block_end_line")
                                    if not block_end_line_id:
                                        logger.warning(f"Block end not found from line {walking_line.id}, results can be unpredictable")
                                        # loop to next line, though at this stage things are very likely to break
                                        walking_line = parsed.next_line(walking_line)
                                        continue
                                    else:
                                        block_end_line = parsed.line_by_id(block_end_line_id)
                                        walking_line = parsed.next_line(block_end_line)
                                        continue # continue the loop as we jumped over the block and were still in the list
                            if walking_line.state_stack.top().type in [StateType.CONDITIONAL,
                                                                       StateType.ATTRIBUTE_DEFINITION,
                                                                       StateType.LINE_COMMENT]:
                                # skip nontext lines
                                walking_line = parsed.next_line(walking_line)
                                continue
                            # if we fall through here, we reached a line not in the list before reaching endif
                            complete_list = True
                            line_after_list = walking_line
                            break 

                        if complete_list:
                            logger.debug(f"      Entire list is conditioned - creating block attributes and jumping over list")
                            # set block attributes if not present, consume block attributes
                            if not block_attributes_set:
                                parsed.create_line_before(current_line, "["+attroles(cond.values)+"]")
                            block_attributes_set = False
                            current_line = line_after_list
                            continue
                        else:
                            logger.debug(f"      List extends beyond conditional - will conditionalize just this item")
                    # if we reached this point we need to add the slug to conditionalize the list item
                    logger.debug(f"      Adding inline role to individual list item")
                    marker = current_line.state_stack.top().get("marker")
                    if not marker:
                        raise RuntimeError(f"Line classified as LIST_ITEM but no marker found in state, line {current_line.id}")
                    content_after_marker = current_line.content[len(marker)+1:] # remove marker and space after it
                    current_line.content = marker+" ["+dotroles(cond.values)+"]#{empty}# "+content_after_marker
                elif current_line_top_state.type == StateType.SECTION_HEADER:
                    logger.debug(f"    Line {current_line.id}: SECTION_HEADER - creating block attributes (uncertain result)")
                    # we already warned the user this might get unpredictable
                    # now we just create the block attributes
                    parsed.create_line_before(current_line, "["+attroles(cond.values)+"]")
                else:
                    logger.debug(f"    Line {current_line.id}: Other type ({current_line_top_state.type.name}) - consuming block attributes if content line")
                    # consume block attributes unless the line is blank or non-text
                    if not ( current_line.content.strip()== "" or
                            current_line_top_state.type in [StateType.CONDITIONAL,
                                                            StateType.LINE_COMMENT,
                                                            StateType.ATTRIBUTE_DEFINITION]):
                        block_attributes_set = False
                
                # end of the loop - move current_line to the next line
                # if we needed to jump we already continued
                current_line = parsed.next_line(current_line)
            if not current_line:
                raise RuntimeError(f"While processing block conditional from line {cond.id} hit EOF instead of endif")
        idx += 1

def remove_conditionals(parsed: Parsed, cond_map: ConditionalsMap):
    for cond in cond_map.conditionals:
        for id in [cond.start_id, cond.end_id]:
            parsed.remove_by_id(id)


def main():
    parser = argparse.ArgumentParser(description="Preprocess AsciiDoc files to handle conditional directives")
    parser.add_argument("input_file", help="Input AsciiDoc file")
    parser.add_argument("output_file", help="Output file")
    parser.add_argument("--list",
                       default="conditionals.lst",
                       help="List file containing conditional values (default: conditionals.lst)")
    parser.add_argument("--debug-output",
                       help="Debug output file for pretty-printed parse and conditional info")
    parser.add_argument("--log-level",
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       default='WARNING',
                       help="Set the logging level (default: WARNING)")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(levelname)s: %(message)s'
    )

    input_file = args.input_file
    output_file = args.output_file
    list_file = args.list

    # Read list file and create values set
    try:
        with open(list_file, 'r', encoding='utf-8') as f:
            values = set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        print(f"Error: List file '{list_file}' not found", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error reading list file: {e}", file=sys.stderr)
        sys.exit(1)

    # Read input file
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error reading input file: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse the document
    parsed = Parsed(lines)

    # Create conditionals map
    cond_map = ConditionalsMap(parsed, values)

    # Write debug output if requested
    if args.debug_output:
        try:
            with open(args.debug_output, 'w', encoding='utf-8') as f:
                f.write(parsed.pretty())
                f.write("\n\n")
                f.write(cond_map.pretty())
                f.write("\n")
        except IOError as e:
            print(f"Error writing debug output file: {e}", file=sys.stderr)
            sys.exit(1)

    # Process conditionals
    process_conditionals(parsed, cond_map)

    # Remove the conditional lines themselves
    remove_conditionals(parsed, cond_map)

    # Write the processed output file (just line contents)
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for line in parsed.lines:
                f.write(line.content)
                f.write("\n")
    except IOError as e:
        print(f"Error writing output file: {e}", file=sys.stderr)
        sys.exit(1)


    print(f"Successfully processed {input_file} -> {output_file}")


if __name__ == "__main__":
    main()
