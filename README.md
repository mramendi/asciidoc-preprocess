# AsciiDoc Conditional Preprocessor

A Python preprocessor that transforms AsciiDoc conditional directives (`ifdef`/`ifndef`) into roles for single-source, multi-variant documentation.

## Overview

This preprocessor enables you to maintain a single AsciiDoc source file that contains platform-specific or product-specific content, and transform the conditional blocks into roles that can be toggled in the rendered output, for example, by CSS or DITA means. Instead of generating multiple output files, you get one document where variant-specific content is marked with CSS classes or DITA attributes.

### What It Does

**Before preprocessing:**
```asciidoc
ifdef::azure[]
This paragraph is Azure-specific.
endif::[]
```

**After preprocessing:**
```asciidoc
[role="platform:azure"]
This paragraph is Azure-specific.
```

The conditional directives is gone but the content inside is now tagged with CSS roles that can be styled or toggled with JavaScript.

However, this is done only to supported and configured conditional directives. Others stay in place.


## Features

- **Paragraph/Block Mode**: Automatically adds `[role="attribute:value"]` to paragraphs, list items, and delimited blocks
- **Inline Mode**: Wraps inline text spans with `[.attribute:value]#text#` for mid-paragraph conditionals
- **List items**: A list item, not being either a block or fully inline, is marked with a special stub `[.attribute:value]#{empty}#` so you can add a role/class later with your scripts.
- **Smart Detection**: Automatically determines whether to use block or inline mode based on context
- **YAML Configuration**: Define your attributes and conditionals in a validated configuration file
- **Schema Validation**: Comprehensive validation ensures your configuration is correct before processing
- **Safety Checks**: Warns about unsupported patterns (conditionals that span a block boundary, conditionals in verbatim blocks, etc.)

### IMPORTANT: incomplete version

This is a proof-of-concept/incomplete version. Some use cases that could in principle be supported are not supported now:

- Conditionals anywhere in tables
- Nested converted conditionals (nesting other conditionals, which remain unchanged, is fine)
- Conditionals that span several paragraphs but start or end in the middle of a paragraph (this is unlikely to be added in the future, too many edge cased)

## Requirements

- Python 3.7+ (in theory - actually tested on 3.13)
- `PyYAML` library
- `jsonschema` library

Install dependencies:
```bash
pip install PyYAML jsonschema
```

## Configuration

Create a `conditionals.yaml` file that maps your conditional names to attributes and values.

### Basic Example

```yaml
attributes:
  platform: [azure, aws, onprem]
  product: [rhel, ocp, rosa]

conditionals:
  - name: azure
    attribute: platform
    value: azure
  - name: aws
    attribute: platform
    value: aws
  - name: onprem
    attribute: platform
    value: onprem
  - name: rhel
    attribute: product
    value: rhel
  - name: ocp
    attribute: product
    value: ocp
  - name: rosa
    attribute: product
    value: rosa
```

### How It Works

**1. Define attributes** - These are your variation categories (platform, product, version, etc.):
```yaml
attributes:
  platform: [azure, aws, gcp]
```

**2. Map conditionals to attributes** - Tell the preprocessor which `ifdef` names map to which attribute values:
```yaml
conditionals:
  - name: azure        # When you write ifdef::azure[]
    attribute: platform # It maps to the "platform" attribute
    value: azure       # With the value "azure"
```

**3. The preprocessor generates roles** - `ifdef::azure[]` becomes `[role="platform:azure"]`; `ifndef::azure[]` becomes `[role="platform:aws,gcp"]` (every possible value except `azure`)

### More Examples

**Single attribute (cloud platforms):**
```yaml
attributes:
  cloud: [aws, azure, gcp, ibm]

conditionals:
  - name: aws
    attribute: cloud
    value: aws
  - name: azure
    attribute: cloud
    value: azure
  - name: gcp
    attribute: cloud
    value: gcp
  - name: ibm
    attribute: cloud
    value: ibm
```

**Multiple independent attributes:**
```yaml
attributes:
  os: [linux, windows, macos]
  version: [v1, v2, v3]

conditionals:
  - name: linux
    attribute: os
    value: linux
  - name: windows
    attribute: os
    value: windows
  - name: v2
    attribute: version
    value: v2
  - name: v3
    attribute: version
    value: v3
```

### Configuration Rules

The preprocessor validates your configuration and will reject files that:

- Missing `attributes` or `conditionals` sections
- Have duplicate conditional names
- Reference non-existent attributes (e.g., conditional uses `attribute: platform` but `platform` isn't defined)
- Use values not in the attribute's list (e.g., `value: gcp` when attribute only has `[azure, aws]`)
- Have empty attributes or conditionals sections
- Use invalid attribute names (must start with letter/underscore, contain only letters/numbers/underscores)

When validation fails, you'll get a helpful error message:
```
Configuration validation error in conditionals.yaml:
  Conditional 'gcp' at conditionals[2] uses value 'gcp' which is not
  in attribute 'platform' possible values: ['azure', 'aws']
```

## Usage

```bash
python3 preprocess-conditionals.py INPUT_FILE OUTPUT_FILE
```

### Example

```bash
python3 preprocess-conditionals.py docs/installation.adoc docs/installation-processed.adoc
```

## Supported Patterns

### ✅ Paragraph-Level Conditionals

**Input:**
```asciidoc
This is intro text.

ifdef::azure[]
This paragraph is Azure-specific.
It has multiple lines.
endif::[]

This is text after.
```

**Output:**
```asciidoc
This is intro text.

ifdef::azure[]
[role="platform:azure"]
This paragraph is Azure-specific.
It has multiple lines.
endif::[]

This is text after.
```

### ✅ Inline Conditionals

**Input:**
```asciidoc
This is a paragraph with
ifdef::aws[]
some AWS-specific text
endif::[]
in the middle of it.
```

**Output:**
```asciidoc
This is a paragraph with
[.platform:aws]#some AWS-specific text#
in the middle of it.
```

### ✅ List Items

**Input:**
```asciidoc
. First item
ifdef::rhel[]
. RHEL-specific item
endif::[]
. Last item
```

**Output:**
```asciidoc
. First item
ifdef::rhel[]
. [.product:rhel]#{empty}#RHEL-specific item
endif::[]
. Last item
```

### ✅ Delimited Blocks

**Input:**
```asciidoc
ifdef::ocp[]
[source,bash]
----
oc get pods
----
endif::[]
```

**Output:**
```asciidoc
ifdef::ocp[]
[source,bash,role="product:ocp"]
----
oc get pods
----
endif::[]
```

### ✅ ifndef Conditionals

The preprocessor supports `ifndef` directives and automatically generates the complementary role. For example, `ifndef::azure[]` becomes `role="platform:aws,onprem"` (all values except `azure`).

## Unsupported Patterns

The preprocessor will warn about and skip these patterns:

- ❌ **Nested conditionals**: Conditionals inside other conditionals
- ❌ **Block boundary crossing**: Conditionals that start inside one block and end in another
- ❌ **Verbatim blocks**: Conditionals inside listing (`----`), literal (`....`), passthrough (`++++`), or comment (`////`) blocks
- ❌ **Table blocks**: Conditionals inside table blocks (`|===`)
- ❌ **Empty conditionals**: Conditionals with no content
- ❌ **Multi-paragraph fragments**: Conditionals that span part of multiple paragraphs (without block boundaries)
- ❌ **ifeval directives**: Only `ifdef` and `ifndef` are supported

## How It Works

The preprocessor performs these steps:

1. **Parse**: Builds a complete index of all delimited blocks and conditionals in the document
2. **Validate**: Checks configuration schema and verifies all conditionals reference known attributes
3. **Filter**: Identifies processable conditionals (supported patterns, known attributes)
4. **Transform**: Adds appropriate roles based on context:
   - Block/paragraph boundaries → `[role="attr:value"]`
   - Inline spans → `[.attr:value]#text#`
   - List items → `. [.attr:value]#{empty}#text`
5. **Output**: Writes the transformed document with conditionals intact but content tagged with roles

## Testing

The `integration_tests/` directory contains example inputs and expected outputs:

- `01_simple_parablock.adoc` - Basic paragraph-level conditional
- `02_inline_conditional.adoc` - Inline text span
- `03_ifndef_conditional.adoc` - Negative conditional
- `04_list_items.adoc` - List item conditionals
- `05_with_code_block.adoc` - Code block with conditional
- `06_ifeval_ignored.adoc` - ifeval (ignored)
- `warn_*.adoc` - Unsupported patterns that generate warnings

Run tests:
```bash
# Process a single test
python3 preprocess-conditionals.py integration_tests/01_simple_parablock.adoc output.adoc
diff integration_tests/01_simple_parablock.out.adoc output.adoc

# Test configuration validation
python3 test_invalid_configs.py

# Unit tests for the internal components
python3 test_conditionals.py
```

## Contributing

When adding new features:

1. Add or modify unit tests in `test_conditionals.py` as appropriate
1. Add integration tests in `integration_tests/` with `.adoc` input and `.out.adoc` expected output
2. Update the schema in `CONDITIONALS_SCHEMA` if adding configuration options
3. Add validation logic in `validate_config_schema()` for semantic checks
4. Update this README with new supported patterns

## License

MIT

## Authors

Misha Ramendik
