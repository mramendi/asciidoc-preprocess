#!/usr/bin/env python3

import unittest
import sys
import os
from io import StringIO
from typing import List
import importlib.util

# Add the current directory to Python path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the module with hyphens in the name
spec = importlib.util.spec_from_file_location(
    "preprocess_conditionals",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "preprocess-conditionals.py")
)
preprocess_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preprocess_module)

# Import the functions and classes we're testing
AsciiDocIndexer = preprocess_module.AsciiDocIndexer
ConditionalLookup = preprocess_module.ConditionalLookup
is_conditional_processable = preprocess_module.is_conditional_processable
is_conditional_processable_as_parablock_start = preprocess_module.is_conditional_processable_as_parablock_start
is_conditional_processable_as_parablock_end = preprocess_module.is_conditional_processable_as_parablock_end
process_parablock_conditional = preprocess_module.process_parablock_conditional
process_inline_conditional = preprocess_module.process_inline_conditional
apply_line_modifications = preprocess_module.apply_line_modifications
process_conditionals = preprocess_module.process_conditionals


class TestAsciiDocIndexer(unittest.TestCase):
    """Test the AsciiDoc indexer for blocks and conditionals"""

    def test_simple_code_block(self):
        """Test detection of a simple code block"""
        content = """Some text
----
code here
----
more text"""
        indexer = AsciiDocIndexer(content.splitlines())

        self.assertEqual(len(indexer.blocks), 1)
        block = indexer.blocks[0]
        self.assertEqual(block.open_line, 1)  # Line 1 (0-based) = "----"
        self.assertEqual(block.close_line, 3)  # Line 3 (0-based) = "----"
        self.assertEqual(block.delimiter, '----')
        self.assertTrue(block.verbatim)

    def test_example_block_with_code_block(self):
        """Test example block (non-verbatim) containing code block (verbatim)"""
        content = """Text
====
outer example
----
code block
----
more example
====
end"""
        indexer = AsciiDocIndexer(content.splitlines())

        self.assertEqual(len(indexer.blocks), 2)
        # Check outer block
        outer = [b for b in indexer.blocks if b.delimiter == '===='][0]
        self.assertEqual(outer.open_line, 1)  # Line 1 (0-based) = "===="
        self.assertEqual(outer.close_line, 7)  # Line 7 (0-based) = "===="
        self.assertFalse(outer.verbatim)
        # Check inner block
        inner = [b for b in indexer.blocks if b.delimiter == '----'][0]
        self.assertEqual(inner.open_line, 3)  # Line 3 (0-based) = "----"
        self.assertEqual(inner.close_line, 5)  # Line 5 (0-based) = "----"
        self.assertTrue(inner.verbatim)

    def test_simple_conditional(self):
        """Test detection of a simple ifdef/endif"""
        content = """text
ifdef::azure[]
conditional content
endif::[]
more text"""
        indexer = AsciiDocIndexer(content.splitlines())

        self.assertEqual(len(indexer.conditionals), 1)
        cond = indexer.conditionals[0]
        self.assertEqual(cond.kind, 'ifdef')
        self.assertEqual(cond.expression, 'azure')
        self.assertEqual(cond.open_line, 1)  # Line 1 (0-based) = "ifdef::azure[]"
        self.assertEqual(cond.close_line, 3)  # Line 3 (0-based) = "endif::[]"

    def test_unmatched_endif(self):
        """Test handling of unmatched endif"""
        # Capture stdout to check warning
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        content = """text
endif::[]
more text"""
        indexer = AsciiDocIndexer(content.splitlines())

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn('WARNING: unmatched endif', output)
        # Should still create a conditional entry
        self.assertEqual(len(indexer.conditionals), 1)
        self.assertEqual(indexer.conditionals[0].kind, 'endif')
        self.assertEqual(indexer.conditionals[0].open_line, -1)  # Unmatched endif has open_line = -1

    def test_unclosed_conditional(self):
        """Test handling of unclosed conditional"""
        content = """text
ifdef::azure[]
conditional content
more content"""
        indexer = AsciiDocIndexer(content.splitlines())

        self.assertEqual(len(indexer.conditionals), 1)
        cond = indexer.conditionals[0]
        # Should have close_line set to end of file
        self.assertEqual(cond.close_line, len(content.splitlines()))

    def test_table_block_detection(self):
        """Test detection of table blocks"""
        content = """text
|===
| Col 1 | Col 2
| A | B
|===
end"""
        indexer = AsciiDocIndexer(content.splitlines())

        self.assertEqual(len(indexer.blocks), 1)
        block = indexer.blocks[0]
        self.assertEqual(block.delimiter, '|===')
        self.assertFalse(block.verbatim)


class TestConditionalLookup(unittest.TestCase):
    """Test the conditional lookup configuration"""

    def setUp(self):
        self.config = {
            'attributes': {
                'platform': ['azure', 'aws', 'onprem'],
                'product': ['rhel', 'ocp']
            },
            'conditionals': [
                {'name': 'azure', 'attribute': 'platform', 'value': 'azure'},
                {'name': 'aws', 'attribute': 'platform', 'value': 'aws'},
                {'name': 'rhel', 'attribute': 'product', 'value': 'rhel'}
            ]
        }
        self.lookup = ConditionalLookup(self.config)

    def test_is_supported(self):
        """Test checking if a conditional is supported"""
        self.assertTrue(self.lookup.is_supported('azure'))
        self.assertTrue(self.lookup.is_supported('rhel'))
        self.assertFalse(self.lookup.is_supported('unknown'))

    def test_find_attribute_value_ifdef(self):
        """Test finding attribute/value for ifdef"""
        s = self.lookup.get_role_string_for_conditional('azure', ".", ifdef=True)
        self.assertEqual(s, 'platform:azure')

    def test_find_attribute_value_ifndef(self):
        """Test finding attribute/value for ifndef"""
        s = self.lookup.get_role_string_for_conditional('azure', ".", ifdef=False)
        self.assertEqual(s, 'platform:aws.platform:onprem')

    def test_find_unknown_conditional(self):
        """Test error handling for unknown conditional"""
        with self.assertRaises(ValueError):
            self.lookup.get_role_string_for_conditional('unknown', ".")


class TestConditionalValidation(unittest.TestCase):
    """Test conditional validation logic"""

    def setUp(self):
        config = {
            'attributes': {'platform': ['azure', 'aws']},
            'conditionals': [
                {'name': 'azure', 'attribute': 'platform', 'value': 'azure'},
                {'name': 'aws', 'attribute': 'platform', 'value': 'aws'}
            ]
        }
        self.lookup = ConditionalLookup(config)

    def test_reject_ifeval(self):
        """Test that ifeval conditionals are rejected"""
        content = """text
ifeval::["{attr}"=="value"]
content
endif::[]"""
        indexer = AsciiDocIndexer(content.splitlines())
        cond = indexer.get_conditional_by_opening_line(1)  # Line 1 (0-based) = "ifeval..."

        result = is_conditional_processable(cond, indexer, self.lookup, -1)
        self.assertFalse(result)

    def test_reject_nested(self):
        """Test that nested conditionals are rejected"""
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        content = """text
ifdef::azure[]
outer content
ifdef::aws[]
inner content
endif::[]
more outer
endif::[]"""
        indexer = AsciiDocIndexer(content.splitlines())

        # Process outer conditional first - should succeed
        outer_cond = indexer.get_conditional_by_opening_line(1)  # Line 1 (0-based)
        result1 = is_conditional_processable(outer_cond, indexer, self.lookup, -1)
        self.assertTrue(result1)

        # Now try to process inner conditional - should be rejected as nested
        # previous_end_line_number is 7 (the outer endif's line)
        inner_cond = indexer.get_conditional_by_opening_line(3)  # Line 3 (0-based)
        result2 = is_conditional_processable(inner_cond, indexer, self.lookup, 7)

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertFalse(result2)
        self.assertIn('nested conditionals NOT supported', output)

    def test_reject_cross_block_boundary(self):
        """Test that conditionals crossing block boundaries are rejected"""
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        content = """text
ifdef::azure[]
----
code
endif::[]
----"""
        indexer = AsciiDocIndexer(content.splitlines())
        cond = indexer.get_conditional_by_opening_line(1)  # Line 1 (0-based)

        result = is_conditional_processable(cond, indexer, self.lookup, -1)

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertFalse(result)
        self.assertIn('block boundary', output)

    def test_reject_inside_verbatim_block(self):
        """Test that conditionals inside verbatim blocks are rejected"""
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        content = """text
----
code
ifdef::azure[]
more code
endif::[]
----"""
        indexer = AsciiDocIndexer(content.splitlines())
        cond = indexer.get_conditional_by_opening_line(3)  # Line 3 (0-based) = "ifdef::azure[]"

        result = is_conditional_processable(cond, indexer, self.lookup, -1)

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertFalse(result)
        self.assertIn('verbatim blocks NOT supported', output)

    def test_reject_inside_table_block(self):
        """Test that conditionals inside table blocks are rejected"""
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        content = """text
|===
| Col
ifdef::azure[]
| More
endif::[]
|==="""
        indexer = AsciiDocIndexer(content.splitlines())
        cond = indexer.get_conditional_by_opening_line(3)  # Line 3 (0-based) = "ifdef::azure[]"

        result = is_conditional_processable(cond, indexer, self.lookup, -1)

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertFalse(result)
        self.assertIn('table blocks NOT supported', output)

    def test_reject_empty_conditional(self):
        """Test that empty conditionals are rejected"""
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        content = """text
ifdef::azure[]
endif::[]
more text"""
        indexer = AsciiDocIndexer(content.splitlines())
        cond = indexer.get_conditional_by_opening_line(1)  # Line 1 (0-based) = "ifdef::azure[]"

        result = is_conditional_processable(cond, indexer, self.lookup, -1)

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertFalse(result)
        self.assertIn('empty conditionals NOT supported', output)


class TestParablockBoundaryDetection(unittest.TestCase):
    """Test parablock boundary detection logic"""

    def test_start_first_line(self):
        """Test conditional starting at first line"""
        content = """ifdef::azure[]
content
endif::[]"""
        indexer = AsciiDocIndexer(content.splitlines())
        cond = indexer.get_conditional_by_opening_line(0)  # Line 0 (0-based) = "ifdef::azure[]"

        result = is_conditional_processable_as_parablock_start(cond, content.splitlines(), indexer)
        self.assertTrue(result)

    def test_start_after_blank_line(self):
        """Test conditional starting after blank line"""
        content = """text

ifdef::azure[]
content
endif::[]"""
        indexer = AsciiDocIndexer(content.splitlines())
        cond = indexer.get_conditional_by_opening_line(2)  # Line 2 (0-based) = "ifdef::azure[]"

        result = is_conditional_processable_as_parablock_start(cond, content.splitlines(), indexer)
        self.assertTrue(result)

    def test_start_after_block_end(self):
        """Test conditional starting after block end"""
        content = """----
code
----
ifdef::azure[]
content
endif::[]"""
        indexer = AsciiDocIndexer(content.splitlines())
        cond = indexer.get_conditional_by_opening_line(3)  # Line 3 (0-based) = "ifdef::azure[]"

        result = is_conditional_processable_as_parablock_start(cond, content.splitlines(), indexer)
        self.assertTrue(result)

    def test_end_last_line(self):
        """Test conditional ending at last line"""
        content = """text
ifdef::azure[]
content
endif::[]"""
        indexer = AsciiDocIndexer(content.splitlines())
        cond = indexer.get_conditional_by_opening_line(1)  # Line 1 (0-based) = "ifdef::azure[]"

        result = is_conditional_processable_as_parablock_end(cond, content.splitlines(), indexer)
        self.assertTrue(result)

    def test_end_before_blank_line(self):
        """Test conditional ending before blank line"""
        content = """text
ifdef::azure[]
content
endif::[]

more text"""
        indexer = AsciiDocIndexer(content.splitlines())
        cond = indexer.get_conditional_by_opening_line(1)  # Line 1 (0-based) = "ifdef::azure[]"

        result = is_conditional_processable_as_parablock_end(cond, content.splitlines(), indexer)
        self.assertTrue(result)


class TestConditionalProcessing(unittest.TestCase):
    """Test conditional processing (parablock and inline)"""

    def setUp(self):
        config = {
            'attributes': {'platform': ['azure', 'aws']},
            'conditionals': [
                {'name': 'azure', 'attribute': 'platform', 'value': 'azure'}
            ]
        }
        self.lookup = ConditionalLookup(config)

    def test_process_simple_parablock(self):
        """Test processing a simple parablock conditional"""
        content = """
ifdef::azure[]
This is a paragraph.
endif::[]
"""
        lines = content.splitlines()
        indexer = AsciiDocIndexer(lines)

        to_insert_lines = {}
        to_delete_lines = []
        cond = indexer.get_conditional_by_opening_line(1)  # Line 1 (0-based) = "ifdef::azure[]"

        process_parablock_conditional(lines, cond, 'platform:azure', 'platform:azure', indexer, to_insert_lines, to_delete_lines)

        # Should have inserted a role line before line 2 (the paragraph)
        self.assertIn(2, to_insert_lines)
        self.assertIn('role=', to_insert_lines[2])
        self.assertIn('platform:azure', to_insert_lines[2])

        # Should mark ifdef and endif lines for deletion
        self.assertIn(1, to_delete_lines)  # ifdef::azure[] line
        self.assertIn(3, to_delete_lines)  # endif::[] line

    def test_process_inline_conditional(self):
        """Test processing an inline conditional"""
        content = """This is a paragraph with
ifdef::azure[]
some conditional text
endif::[]
in the middle."""
        lines = content.splitlines()
        indexer = AsciiDocIndexer(lines)

        to_delete_lines = []
        cond = indexer.get_conditional_by_opening_line(1)  # Line 1 (0-based) = "ifdef::azure[]"

        process_inline_conditional(lines, cond, 'platform:azure', indexer, to_delete_lines)

        # Should mark ifdef (line 1) and endif (line 3) for deletion
        self.assertIn(1, to_delete_lines)
        self.assertIn(3, to_delete_lines)

        # Should have added role markers to content line (line 2)
        self.assertIn('[.platform:azure]#', lines[2])
        self.assertTrue(lines[2].endswith('#'))

    def test_apply_line_modifications(self):
        """Test applying line insertions and deletions"""
        lines = ['line0', 'line1', 'line2', 'line3', 'line4']
        to_insert = {2: 'inserted'}
        to_delete = [3]

        apply_line_modifications(lines, to_insert, to_delete)

        # Check insertion happened
        self.assertIn('inserted', lines)
        # Check deletion happened
        self.assertNotIn('line3', lines)

    def test_apply_line_modifications_overlap_detection(self):
        """Test that overlapping insert/delete on same line raises error"""
        lines = ['line0', 'line1', 'line2', 'line3']
        to_insert = {2: 'inserted'}
        to_delete = [2]  # Same line number as insert - should error

        with self.assertRaises(ValueError) as context:
            apply_line_modifications(lines, to_insert, to_delete)

        self.assertIn('both insert and delete lists', str(context.exception))

    def test_end_to_end_parablock(self):
        """Test end-to-end processing of parablock conditional"""
        content = """Some intro text.

ifdef::azure[]
This is conditional content.
endif::[]

More text after."""
        lines = content.splitlines()
        indexer = AsciiDocIndexer(lines)

        process_conditionals(lines, indexer, self.lookup)

        # The ifdef and endif lines should be removed
        # And role should be added to the content
        result = '\n'.join(lines)
        self.assertNotIn('ifdef::azure[]', result)
        self.assertNotIn('endif::[]', result)
        self.assertIn('role=', result)
        self.assertIn('platform:azure', result)

    def test_code_block_with_blank_line_and_paragraph(self):
        """Test parablock conditional with code block followed by blank line and paragraph"""
        content = """ifdef::azure[]
Intro paragraph.

----
code content
----

Final paragraph.
endif::[]"""
        lines = content.splitlines()
        indexer = AsciiDocIndexer(lines)

        to_insert_lines = {}
        to_delete_lines = []
        cond = indexer.get_conditional_by_opening_line(0)

        process_parablock_conditional(lines, cond, 'platform:azure', 'platform:azure', indexer, to_insert_lines, to_delete_lines)

        # Apply the modifications
        apply_line_modifications(lines, to_insert_lines, to_delete_lines)

        result = '\n'.join(lines)

        # Should have roles for intro paragraph, code block, and final paragraph
        self.assertIn('[role="platform:azure"]', result)

        # The final paragraph should have the role immediately before it, not on the blank line
        # Check that we don't have role followed immediately by blank line
        self.assertNotIn('[role="platform:azure"]\n\n', result)

        # Split to verify structure
        result_lines = result.split('\n')

        # Find the final paragraph line
        final_para_idx = None
        for i, line in enumerate(result_lines):
            if 'Final paragraph' in line:
                final_para_idx = i
                break

        self.assertIsNotNone(final_para_idx, "Final paragraph not found")

        # The line immediately before "Final paragraph" should be the role
        self.assertIn('[role="platform:azure"]', result_lines[final_para_idx - 1])


if __name__ == '__main__':
    # Run with verbosity
    unittest.main(verbosity=2)
