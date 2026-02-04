#!/usr/bin/env python3
"""
Utility to generate attribute roles for conditional values.
By default, inverts the user-provided set (ifndef behavior).
"""

import sys
import argparse
import re
from typing import Set
from preprocess_conditionals import dotroles, attroles


def parse_values(args_list):
    """
    Parse values from command line arguments.
    Supports:
    - Space separated: values-ifndef.py a b c
    - Comma separated: values-ifndef.py "a,b,c"
    - Mixed: values-ifndef.py "a, b, c"
    - Combinations: values-ifndef.py a "b,c" d
    """
    all_values = []
    for arg in args_list:
        # Split by comma first, then by spaces
        parts = re.split(r'[,\s]+', arg)
        all_values.extend([p.strip() for p in parts if p.strip()])
    return set(all_values)


def main():
    parser = argparse.ArgumentParser(
        description="Generate attribute roles for conditional values",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s a b c
  %(prog)s "a,b,c"
  %(prog)s "a, b, c"
  %(prog)s --ifdef a b
  %(prog)s --dot --ifdef "container-install,aap-install"
  %(prog)s --list custom.lst operator-mesh
        """
    )
    parser.add_argument("values",
                       nargs="*",
                       help="Values to process (space or comma separated)")
    parser.add_argument("--list",
                       default="conditionals.lst",
                       help="List file containing all conditional values (default: conditionals.lst)")
    parser.add_argument("--dot",
                       action="store_true",
                       help="Use dotroles() format instead of attroles()")
    parser.add_argument("--ifdef",
                       action="store_true",
                       help="Use exact values provided (don't invert the set)")

    args = parser.parse_args()

    # Read list file and create full values set
    try:
        with open(args.list, 'r', encoding='utf-8') as f:
            all_values = set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        print(f"Error: List file '{args.list}' not found", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error reading list file: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse user-provided values
    if not args.values:
        print("Error: No values provided", file=sys.stderr)
        parser.print_help(sys.stderr)
        sys.exit(1)

    user_values = parse_values(args.values)

    # Determine which values to use
    if args.ifdef:
        # Use exact values provided by user
        output_values = user_values
    else:
        # Invert: all values NOT in user set (ifndef behavior)
        output_values = all_values - user_values

    # Generate output (sort for deterministic output)
    if not output_values:
        # No values to output - just print empty string
        print()
    else:
        sorted_values = sorted(output_values)
        if args.dot:
            print(dotroles(sorted_values))
        else:
            print(attroles(sorted_values))


if __name__ == "__main__":
    main()
