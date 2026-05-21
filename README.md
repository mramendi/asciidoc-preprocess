# AsciiDoc Conditional Preprocessor

A Python preprocessor that transforms AsciiDoc conditional directives (`ifdef`/`ifndef`) into DITA-compatible role markers for single-source, multi-variant documentation.

An additional script to find files with conditionals in a tree is provided.

## Overview

This preprocessor enables you to maintain a single AsciiDoc source file that contains platform-specific or product-specific content, and transform the conditional blocks into role attributes that can be filtered in DITA processing. Instead of generating multiple output files, you get one document where variant-specific content is marked with `.otherprops:value` role markers.

The `--lint` option lets you check which conditionals in the source are unsupported or discouraged.

### What It Does

**Before preprocessing:**
```asciidoc
ifdef::azure[]
This paragraph is Azure-specific.
endif::[]
```

**After preprocessing:**
```asciidoc
[role="otherprops:azure"]
This paragraph is Azure-specific.
```

The `ifdef` conditional directives are removed and the content is tagged with role attributes using the DITA `otherprops` attribute format.


**Before preprocessing:**
```asciidoc
ifndef::azure[]
This paragraph is specific to platforms other than Azure.
endif::[]
```

**After preprocessing:**
```asciidoc
[role="otherprops:aws otherprops:baremetal"]
This paragraph is specific to platforms other than Azure.
```

The `ifndef` conditional directives are removed and the content is tagged with role attributes using the DITA `otherprops` attribute format, enabling all the listed attributes except the one(s) ifdef'ed.




**Important:** This version works with a "single switch knob" set of conditions, where it is presumed that there is a fixed list of conditions and exactly one is enabled for any one build. The conditional attributes (converted to `otherprops` values) are configured in the list file (default: `conditionals.lst`). If you use the `--lint` option, the conditional list is not read and conditionalising values are not checked - but the script checks what text you can and cannot condition.


## Features

- **Block Mode**: Automatically adds `[role="otherprops:value"]` before paragraphs, entire lists, sections, and delimited blocks
- **Inline Mode**: Wraps text spans with `[.otherprops:value]#text#` for partial paragraphs and list items (conditionals must still be on separate lines)
- **List Items**: Individual list items get inline markers like `* [.otherprops:value]#{empty}# Item text`
- **Joint List Item Groups**: Handles the pattern where multiple conditional list items share a common continuation marker (`+`)
- **Tables**: Allows conditionalizing entire rows in PSV tables
- **Sections**: Supports conditionalizing complete sections (but not module title or partial sections)
- **Single-Line Conditionals**: Supports single-line `ifdef::attr[content]` syntax where the whole line is the conditional (warns as discouraged)
- **Smart Detection**: Automatically determines whether to use block or inline mode based on parsing context
- **Configurable Values**: Reads the list of attribute values to process from a list file (default: `conditionals.lst`)
- **Safety Checks**: Warns about unsupported patterns and leaves them unchanged. Also warns about patterns that are supported but discouraged.

## Usage

### Basic Command

```bash
./preprocess_conditionals.py input.adoc output.adoc
```

### Command-Line Options

```
./preprocess_conditionals.py input.adoc output.adoc [OPTIONS]

Arguments:
  input_file              Input AsciiDoc file to preprocess
  output_file             Output file path. Do not supply this option in lint mode.

Options:
  --list FILE            List file containing conditional values (default: conditionals.lst)
  --debug-output FILE    Write debug information to FILE (includes parse tree and conditional map)
  --log-level LEVEL      Set logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
  --lint, -l             Check for unsupported or discouraged conditionals but do not create an output file
```

### List File Format

The list file (`conditionals.lst` by default) contains one attribute value per line:

```
azure
aws
onprem
```

Only conditionals using these values will be processed. For example, `ifdef::azure[]` will be processed but `ifdef::context[]` will not (unless "context" is in the list).

### Examples

**Block-level conditional:**
```asciidoc
# Before
ifdef::azure[]
This is an Azure-specific paragraph.
endif::[]

# After
[role="otherprops:azure"]
This is an Azure-specific paragraph.
```

**Partial paragraph (inline mode):**
```asciidoc
# Before
This paragraph starts here
ifdef::aws[]
and has this AWS-specific part
endif::[]
and continues after the conditional.

# After
This paragraph starts here
[.otherprops:aws]#and has this AWS-specific part#
and continues after the conditional.
```

**List item:**
```asciidoc
# Before
ifdef::onprem[]
* On-premises installation step
endif::[]

# After
* [.otherprops:onprem]#{empty}# On-premises installation step
```

**Joint list item group:**
```asciidoc
# Before
ifdef::azure[]
* Azure step
endif::[]
ifdef::aws[]
* AWS step
endif::[]
+
Common continuation for both

# After
* [.otherprops:azure]#Azure step# [.otherprops:aws]#AWS step#
+
Common continuation for both
```

**Single-line conditional:**
```asciidoc
# Before
ifdef::azure[This entire line is Azure-specific content]

# After
[.otherprops:azure]#This entire line is Azure-specific content#
```

Note: Single-line conditionals must be on their own line - the `ifdef` must be at the start of the line.

**Table rows (PSV only):**
```asciidoc
# Before
|===
|Column 1 |Column 2
ifdef::azure[]
|Azure data |Azure value
endif::[]
|Common data |Common value
|===

# After
|===
|Column 1 |Column 2
|[.otherprops:azure]#{empty}# Azure data |Azure value
|Common data |Common value
|===
```

**Complete section:**
```asciidoc
# Before
ifdef::onprem[]
== On-premises configuration
Instructions for on-premises deployments.
endif::[]

# After
[role="otherprops:onprem"]
== On-premises configuration
Instructions for on-premises deployments.
```

## How It Works

The preprocessor uses a three-phase approach:

1. **Parsing Phase** (`lineparser.py`): Reads the AsciiDoc file and builds a state stack for each line, tracking context like paragraphs, list items, delimited blocks, etc.

2. **Classification Phase** (`condmap.py`): Analyzes conditionals and classifies them into types:
   - `SINGLE_LINE`: Single-line conditional like `ifdef::attr[content]`
   - `PARTIAL`: Mid-content conditional (inline mode)
   - `PART_START_LIST_ITEM`: Conditional starting at list item marker (partial item)
   - `SINGLE_LIST_ITEM`: One complete list item
   - `GROUP_START_LIST_ITEM`: Multiple list items sharing continuation
   - `TABLE_ROWS`: One or more complete table rows in PSV tables
   - `BLOCKS`: Complete blocks (paragraphs, lists, delimited blocks, sections)

3. **Processing Phase** (`preprocess_conditionals.py`): Applies role markers based on classification and removes conditional directives.

Debug output (via `--debug-output`) shows the parse tree and conditional classification, which is helpful for understanding how the tool interprets your document structure.

## Limitations and Unsupported Patterns

This is a work in progress. Some use cases that could in principle be supported are not currently implemented.

### Completely Unsupported

The following patterns will generate errors and be left unchanged in the output:

- **Nested conditionals**: Conditionals inside other conditionals
- **Conditionals in verbatim blocks**: Any conditionals inside listing blocks, literal blocks, or other verbatim content
- **Conditionals crossing block boundaries**: Conditionals that start inside one delimited block and end in another
- **Conditionals in tables**: 
  - Only conditionals of one or more whole rows in PSV tables are supported
  - You cannot conditionalize cells or anything within a cell
  - No conditionals are supported in CSV/TSV/DSV tables
- **Block prefixes before conditionals**: `[attributes]` or `.BlockTitle` immediately before an `ifdef` line
- **Empty conditionals**: Conditionals with no content between `ifdef` and `endif`
- **Multiple values with + operator**: Expressions like `ifdef::platform1+platform2[]` are not supported (use comma instead: `ifdef::platform1,platform2[]`)
- **Undefined values**: Conditional values not listed in the list file (unless using `--lint` mode)
- **ifeval**: The `ifeval` directive is not supported

### Restrictions for Procedure Modules

For files with `:_mod-docs-content-type: PROCEDURE`, conditionals **cannot contain**:

- **Fixed procedure block titles**: `.Prerequisites`, `.Procedure`, `.Verification`, `.Results`, `.Troubleshooting`, `.Next steps`, `.Additional resources`

These titles must remain outside conditionals as they define the procedure structure.

### Restrictions for All Modules

Conditionals **cannot contain**:

- **Module title** (level 1 heading): The main `= Title` must remain outside conditionals
- **Short description**: Paragraphs with `[role="_abstract"]` cannot be conditionalized
- **Partial sections**: If a conditional contains a section header, the entire section must be inside the conditional (section end must come before `endif`)
- **Mixed section levels**: If a conditional starts with a section header, all other section headers inside must be at the same level or deeper

### Discouraged but Supported Patterns

These patterns work but generate warnings because they may indicate authoring issues:

- **Single-line conditionals**: `ifdef::attr[content]` as a complete line (no endif needed) - works but consider using block style with `ifdef`/`endif` for clarity
- **Partial paragraphs/list items**: Conditionals that cover part of a paragraph or list item (the `ifdef` and `endif` are on separate lines, but the paragraph/list item continues before or after) - works but may be hard to maintain
- **Sections inside delimited blocks**: Supported but section counting may be inaccurate

**Unsupported conditionals are left unchanged** in the output file, so you can identify and handle them manually or with other tools.

## Requirements

- Python 3.9 or later
- No external dependencies (uses only the Python standard library)

## Conditional search script

```
./find-and-copy-conditionals.sh tree-dir out-dir
```

Finds every file in the tree under `tree-dir` that has any `ifdef::` or `ifndef::` line, except those referring to `context` or `parent`, sod copies all such files into out-dir without replicating the directory structure. Displays a warning if a filename is duplicated. 

## License

MIT License

## Author

Misha Ramendik (mramendi@redhat.com)
