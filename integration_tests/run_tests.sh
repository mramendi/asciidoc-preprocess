#!/bin/bash

# Integration test runner for AsciiDoc conditional preprocessor
# This script regenerates all expected output files

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREPROCESS_SCRIPT="$SCRIPT_DIR/../preprocess-conditionals.py"

# Check if preprocessor script exists
if [ ! -f "$PREPROCESS_SCRIPT" ]; then
    echo "Error: Preprocessor script not found at $PREPROCESS_SCRIPT"
    exit 1
fi

echo "Regenerating integration test expected outputs..."
echo "================================================"
echo

# Counter for statistics
total=0
success=0
failed=0

# Process each input file (exclude .out. files)
for input_file in "$SCRIPT_DIR"/*.adoc; do
    # Skip if it's an output file
    if [[ "$input_file" == *.out.adoc ]]; then
        continue
    fi

    # Get base name without extension
    base=$(basename "$input_file" .adoc)
    output_file="$SCRIPT_DIR/${base}.out.adoc"

    echo -n "Processing $base.adoc ... "
    total=$((total + 1))

    # Run the preprocessor
    if python3 "$PREPROCESS_SCRIPT" "$input_file" "$output_file" 2>&1; then
        echo "✓ Generated ${base}.out.adoc"
        success=$((success + 1))
    else
        echo "✗ FAILED"
        failed=$((failed + 1))
    fi
done

echo
echo "================================================"
echo "Summary: $success/$total tests generated successfully"
if [ $failed -gt 0 ]; then
    echo "WARNING: $failed test(s) failed"
    exit 1
fi
