#!/usr/bin/env python3
"""
Test script for line state tracking in AsciiDocIndexer.
"""

import sys
import importlib.util

# Import module with dash in name
spec = importlib.util.spec_from_file_location("preprocess_conditionals", "preprocess-conditionals.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

AsciiDocIndexer = module.AsciiDocIndexer
LineState = module.LineState

def test_basic_states():
    """Test basic line state detection."""

    lines = [
        "This is a paragraph.",
        "It continues here.",
        "",
        "* List item 1",
        "* List item 2",
        "",
        ". Ordered item 1",
        ". Ordered item 2",
        "",
        "term:: description",
        "",
        "ifdef::foo[]",
        "Content",
        "endif::foo[]",
        "",
        "// This is a comment",
        "",
        "----",
        "Verbatim content",
        "----",
    ]

    indexer = AsciiDocIndexer(lines)

    # Test paragraph detection
    print("=== Testing Paragraph Detection ===")
    assert indexer.is_in_paragraph(0), "Line 0 should be in paragraph"
    assert indexer.is_in_paragraph(1), "Line 1 should be in paragraph"
    print("✓ Paragraph detection works")

    # Test blank line detection
    print("\n=== Testing Blank Line Detection ===")
    assert indexer.is_blank_line(2), "Line 2 should be blank"
    assert indexer.is_blank_line(5), "Line 5 should be blank"
    print("✓ Blank line detection works")

    # Test list detection
    print("\n=== Testing List Detection ===")
    assert indexer.is_list_item_start(3), "Line 3 should be a list item"
    assert indexer.get_list_type(3) == 'unordered', "Line 3 should be unordered list"
    assert indexer.is_list_item_start(4), "Line 4 should be a list item"
    print("✓ Unordered list detection works")

    assert indexer.is_list_item_start(6), "Line 6 should be a list item"
    assert indexer.get_list_type(6) == 'ordered', "Line 6 should be ordered list"
    print("✓ Ordered list detection works")

    assert indexer.is_list_item_start(9), "Line 9 should be a list item"
    assert indexer.get_list_type(9) == 'description', "Line 9 should be description list"
    print("✓ Description list detection works")

    # Test conditional detection
    print("\n=== Testing Conditional Detection ===")
    assert indexer.has_state(11, LineState.CONDITIONAL_DIRECTIVE), "Line 11 should be conditional"
    assert indexer.has_state(13, LineState.CONDITIONAL_DIRECTIVE), "Line 13 should be conditional"
    print("✓ Conditional detection works")

    # Test comment detection
    print("\n=== Testing Comment Detection ===")
    assert indexer.has_state(15, LineState.COMMENT_LINE), "Line 15 should be comment"
    print("✓ Comment detection works")

    # Test verbatim block detection
    print("\n=== Testing Verbatim Block Detection ===")
    assert indexer.is_block_delimiter(17), "Line 17 should be block delimiter"
    assert indexer.is_in_verbatim_block(18), "Line 18 should be in verbatim block"
    assert indexer.is_block_delimiter(19), "Line 19 should be block delimiter"
    print("✓ Verbatim block detection works")

    print("\n=== All Basic Tests Passed! ===")


def test_continuation_marker():
    """Test that + is only a continuation marker in list context."""

    lines = [
        "This is a paragraph.",
        "+",
        "More paragraph text.",
        "",
        "* List item 1",
        "+",
        "Continued list item",
        "",
        ". Ordered item",
        "+",
        "----",
        "code block attached to list",
        "----",
    ]

    indexer = AsciiDocIndexer(lines)

    print("=== Testing Continuation Marker Context ===")

    # In paragraph context, + is just text
    assert not indexer.is_continuation_marker(1), "Line 1 (+) should NOT be continuation in paragraph"
    assert indexer.is_in_paragraph(1), "Line 1 should be part of paragraph"
    print("✓ Plus in paragraph is not a continuation marker")

    # In list context, + is a continuation marker
    assert indexer.is_continuation_marker(5), "Line 5 (+) SHOULD be continuation in list"
    assert indexer.has_state(5, LineState.ATTACHED_TO_LIST), "Line 5 should be attached to list"
    print("✓ Plus after list item is a continuation marker")

    assert indexer.is_continuation_marker(9), "Line 9 (+) SHOULD be continuation in list"
    print("✓ Plus after ordered list item is a continuation marker")

    print("\n=== Continuation Marker Tests Passed! ===")


def test_complex_lists():
    """Test list item continuation and paragraph breaks."""

    lines = [
        "* Item 1",
        "continuation of item 1",
        "",
        "* Item 2",
        "+",
        "attached paragraph",
        "",
        "* Item 3",
    ]

    indexer = AsciiDocIndexer(lines)

    print("=== Testing Complex List Structure ===")

    assert indexer.is_list_item_start(0), "Line 0 should be list item start"
    assert indexer.is_in_list_item(1), "Line 1 should be in list item"
    assert indexer.is_blank_line(2), "Line 2 should be blank (breaks list item)"
    assert indexer.is_list_item_start(3), "Line 3 should be new list item"
    assert indexer.is_continuation_marker(4), "Line 4 should be continuation marker"
    assert indexer.has_state(5, LineState.ATTACHED_TO_LIST), "Line 5 should be attached to list"

    print("✓ Complex list structure works correctly")
    print("\n=== Complex List Tests Passed! ===")


def print_line_states(lines, indexer):
    """Helper function to print all line states for debugging."""
    print("\n=== Line State Report ===")
    for i, line in enumerate(lines):
        state = indexer.get_line_state(i)
        line_preview = line[:50] if len(line) <= 50 else line[:47] + "..."
        print(f"{i:3d}: {line_preview:50s} | {state}")


if __name__ == "__main__":
    try:
        test_basic_states()
        print()
        test_continuation_marker()
        print()
        test_complex_lists()

        print("\n" + "="*60)
        print("ALL TESTS PASSED!")
        print("="*60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
