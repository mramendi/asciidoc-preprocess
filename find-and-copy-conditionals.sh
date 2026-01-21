#!/bin/bash

# Script to find files with ifdef::/ifndef:: (excluding context/parent) and copy them flat

if [ $# -ne 2 ]; then
    echo "Usage: $0 <source_directory> <target_directory>"
    echo "Example: $0 downstream conditionals"
    exit 1
fi

SOURCE_DIR="$1"
TARGET_DIR="$2"

# Validate source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    echo "Error: Source directory '$SOURCE_DIR' does not exist"
    exit 1
fi

# Create target directory if it doesn't exist
mkdir -p "$TARGET_DIR"

echo "Searching for files with ifdef::/ifndef:: in $SOURCE_DIR"
echo "Excluding: ifdef::context, ifdef::parent, ifndef::context, ifndef::parent"
echo ""

# Find all matching files
TEMP_FILE=$(mktemp)
(
    rg '^ifdef::' "$SOURCE_DIR" --no-heading --with-filename | \
        grep -v 'ifdef::context' | \
        grep -v 'ifdef::parent' | \
        cut -d: -f1

    rg '^ifndef::' "$SOURCE_DIR" --no-heading --with-filename | \
        grep -v 'ifndef::parent' | \
        grep -v 'ifndef::context' | \
        cut -d: -f1
) | sort -u > "$TEMP_FILE"

TOTAL_FILES=$(wc -l < "$TEMP_FILE")
echo "Found $TOTAL_FILES files to copy"
echo ""

# Check for duplicate filenames before copying
echo "Checking for duplicate filenames..."
DUPLICATES=$(cat "$TEMP_FILE" | xargs -n1 basename | sort | uniq -d)

if [ -n "$DUPLICATES" ]; then
    echo "WARNING: Duplicate filenames detected!"
    echo "The following filenames appear multiple times:"
    echo "$DUPLICATES"
    echo ""
    echo "Files with duplicate names:"
    while IFS= read -r dup_name; do
        echo "  - $dup_name:"
        grep "/$dup_name$" "$TEMP_FILE" | sed 's/^/      /'
    done <<< "$DUPLICATES"
    echo ""
    read -p "Continue anyway? Later files will overwrite earlier ones. (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        rm "$TEMP_FILE"
        exit 1
    fi
fi

echo "Copying files to $TARGET_DIR..."
echo ""

COPIED=0
while IFS= read -r file; do
    cp "$file" "$TARGET_DIR/"
    echo "Copied: $(basename "$file")"
    ((COPIED++))
done < "$TEMP_FILE"

rm "$TEMP_FILE"

echo ""
echo "Done! Copied $COPIED files to $TARGET_DIR/"
echo "Final count: $(ls "$TARGET_DIR"/*.adoc 2>/dev/null | wc -l) files in target directory"
