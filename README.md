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

- **Paragraph/Block Mode**: Automatically adds `[role="attribute:value"]` to paragraphs, entire lists, and delimited blocks
- **Inline Mode**: Wraps inline text spans with `[.attribute:value]#text#` for mid-paragraph conditionals
- **List items**: A list item, not being either a block or fully inline, is marked with a special stub `[.attribute:value]#{empty}#` so you can add a role/class later with your scripts.
- **Diverged start of the list**: The start of a list item is conditionalized, then the continuation is common.
- **Smart Detection**: Automatically determines whether to use block or inline mode based on context
- **List Configuration**: The current version uses one attribute (otherprops); the list of values, equivalent to Asciidoc ifdef attributes, must be provided in `conditionals.lst`
- **Safety Checks**: Warns about unsupported patterns (conditionals that span a block boundary, conditionals in verbatim blocks, etc.)

### IMPORTANT: incomplete version

This is a work in progress. Some use cases that could in principle be supported are not supported now:

- Conditionals anywhere in tables
- Nested conditionals 
- Conditionals that span several paragraphs but start or end in the middle of a paragraph (this is unlikely to be added in the future, too many edge cases)

Unsupported conditionals remain unchanged in the file.

## License

MIT

## Authors

Misha Ramendik mramendi@redhat.com
