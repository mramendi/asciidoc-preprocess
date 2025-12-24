#!/usr/bin/env python3
"""
Preprocess AsciiDoc files to handle conditional directives.
"""

import sys
import logging
import argparse
from parser import Parsed
from condmap import ConditionalsMap


def main():
    parser = argparse.ArgumentParser(description="Preprocess AsciiDoc files to handle conditional directives")
    parser.add_argument("input_file", help="Input AsciiDoc file")
    parser.add_argument("output_file", help="Output file")
    parser.add_argument("--list",
                       default="conditionals.lst",
                       help="List file containing conditional values (default: conditionals.lst)")
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

    # Write pretty output to output file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(parsed.pretty())
            f.write("\n\n")
            f.write(cond_map.pretty())
            f.write("\n")
    except IOError as e:
        print(f"Error writing output file: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Successfully processed {input_file} -> {output_file}")


if __name__ == "__main__":
    main()
