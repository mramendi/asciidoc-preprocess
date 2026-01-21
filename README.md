# AsciiDoc Conditional Preprocessor

A Python preprocessor that transforms AsciiDoc conditional directives (`ifdef`/`ifndef`) into DITA-compatible role markers for single-source, multi-variant documentation.

An additional script to find files with conditionals in a tree is provided.

## Overview

This preprocessor enables you to maintain a single AsciiDoc source file that contains platform-specific or product-specific content, and transform the conditional blocks into role attributes that can be filtered in DITA processing. Instead of generating multiple output files, you get one document where variant-specific content is marked with `.otherprops:value` role markers.

### What It Does

**Before preprocessing:**
```asciidoc
ifdef::azure[]
This paragraph is Azure-specific.
endif::[]
```

**After preprocessing:**
```asciidoc
[role=".otherprops:azure"]
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
[role=".otherprops:aws .otherprops:baremetal"]
This paragraph is specific to platforms other than Azure.
```

The `ifndef` conditional directives are removed and the content is tagged with role attributes using the DITA `otherprops` attribute format, enabling all the listed attributes except the one(s) ifdef'ed.




**Important:** This version works with a "single switch knob" set of conditions, where it is presumed that there is a fixed list of conditions and exactly one is enabled for any one build. The conditional attributes (converted to `otherprops` values) are configured in the list file (default: `conditionals.lst`)/


## Features

- **Block Mode**: Automatically adds `[role=".otherprops:value"]` before paragraphs, entire lists, and delimited blocks
- **Inline Mode**: Wraps inline text spans with `[.otherprops:value]#text#` for mid-paragraph conditionals
- **List Items**: Individual list items get inline markers like `* [.otherprops:value]#{empty}# Item text`
- **Joint List Item Groups**: Handles the pattern where multiple conditional list items share a common continuation marker (`+`)
- **Smart Detection**: Automatically determines whether to use block or inline mode based on parsing context
- **Configurable Values**: Reads the list of attribute values to process from a list file (default: `conditionals.lst`)
- **Safety Checks**: Warns about unsupported patterns and leaves them unchanged

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
  output_file             Output file path

Options:
  --list FILE            List file containing conditional values (default: conditionals.lst)
  --debug-output FILE    Write debug information to FILE (includes parse tree and conditional map)
  --log-level LEVEL      Set logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: WARNING)
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
[role=".otherprops:azure"]
This is an Azure-specific paragraph.
```

**Inline conditional (partial paragraph):**
```asciidoc
# Before
This paragraph has ifdef::aws[](AWS-specific content) in the middle.endif::[]

# After
This paragraph has [.otherprops:aws]#AWS-specific content# in the middle.
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

## How It Works

The preprocessor uses a three-phase approach:

1. **Parsing Phase** (`parser.py`): Reads the AsciiDoc file and builds a state stack for each line, tracking context like paragraphs, list items, delimited blocks, etc.

2. **Classification Phase** (`condmap.py`): Analyzes conditionals and classifies them into types:
   - `PARTIAL`: Mid-content conditional (inline mode)
   - `PART_START_LIST_ITEM`: Conditional starting at list item marker (partial item)
   - `SINGLE_LIST_ITEM`: One complete list item
   - `GROUP_START_LIST_ITEM`: Multiple list items sharing continuation
   - `BLOCKS`: Complete blocks (paragraphs, lists, delimited blocks)

3. **Processing Phase** (`preprocess_conditionals.py`): Applies role markers based on classification and removes conditional directives.

Debug output (via `--debug-output`) shows the parse tree and conditional classification, which is helpful for understanding how the tool interprets your document structure.

## Limitations

This is a work in progress. Some use cases that could in principle be supported are not currently implemented:

- **Conditionals in tables**: Any conditional within a table structure
- **Nested conditionals**: Conditionals inside other conditionals
- **Complex partial spans**: Conditionals that span multiple paragraphs but start or end in the middle of a paragraph (unlikely to be added due to edge cases)
- **Single lile conditionals**
- **ifeval**

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
