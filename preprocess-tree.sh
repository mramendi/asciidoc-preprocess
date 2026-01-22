#!/bin/bash

# Check argument count
if [ $# -ne 2 ]; then
    echo "Usage: $0 input-dir output-dir"
    exit 1
fi

INPUT_DIR="$1"
OUTPUT_DIR="$2"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PREPROCESS_SCRIPT="$SCRIPT_DIR/preprocess_conditionals.py"

# Validate input directory
if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: Input directory '$INPUT_DIR' does not exist"
    exit 1
fi

# Validate preprocessor script exists
if [ ! -f "$PREPROCESS_SCRIPT" ]; then
    echo "Error: Preprocessor script '$PREPROCESS_SCRIPT' not found"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Find all .adoc files and process them
count=0
errors=0

find "$INPUT_DIR" -type f -name "*.adoc" | while IFS= read -r input_file; do
    # Get relative path from INPUT_DIR
    relpath="${input_file#$INPUT_DIR/}"

    # Construct output file path
    output_file="$OUTPUT_DIR/$relpath"

    # Create output subdirectory if necessary
    mkdir -p "$(dirname "$output_file")"

    # Print what we're processing
    echo "Processing $relpath ..."

    # Run the preprocessor
    if "$PREPROCESS_SCRIPT" "$input_file" "$output_file"; then
        count=$((count + 1))
    else
        errors=$((errors + 1))
        echo "  ERROR: Failed to process $relpath"
    fi
done

echo ""
echo "Processing complete: $count files processed successfully, $errors errors"
