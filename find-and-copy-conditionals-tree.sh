#!/bin/bash

# Check argument count
if [ $# -lt 2 ] || [ $# -gt 3 ]; then
    echo "Usage: $0 source-dir output-dir [master-list]"
    exit 1
fi

SOURCE_DIR="$1"
OUT_DIR="$2"
MASTER_LIST="$3"

# Validate source directory
if [ ! -d "$SOURCE_DIR" ]; then
    echo "Error: Source directory '$SOURCE_DIR' does not exist"
    exit 1
fi

# Validate master list if provided
if [ -n "$MASTER_LIST" ] && [ ! -f "$MASTER_LIST" ]; then
    echo "Error: Master list file '$MASTER_LIST' does not exist"
    exit 1
fi

# Create output directory
mkdir -p "$OUT_DIR"

# Step 1: Get list of files with conditionals
if [ -n "$MASTER_LIST" ]; then
    # Read paths from master list, prepend SOURCE_DIR, check each
    FILES_WITH_CONDS=$(while IFS= read -r relpath; do
        # Skip empty lines
        [ -z "$relpath" ] && continue
        echo "$SOURCE_DIR/$relpath"
    done < "$MASTER_LIST" | \
    xargs -r grep -H '^ifdef::\|^ifndef::' 2>/dev/null | \
    grep -v 'ifdef::context\|ifdef::parent\|ifndef::context\|ifndef::parent' | \
    cut -d: -f1 | sort -u)
else
    # Search all .adoc files in tree
    FILES_WITH_CONDS=$(find "$SOURCE_DIR" -type f -name "*.adoc" -exec grep -H '^ifdef::\|^ifndef::' {} + 2>/dev/null | \
    grep -v 'ifdef::context\|ifdef::parent\|ifndef::context\|ifndef::parent' | \
    cut -d: -f1 | sort -u)
fi

# Check if any files were found
if [ -z "$FILES_WITH_CONDS" ]; then
    echo "No files with conditionals found"
    exit 0
fi

# Step 2: For each file, preserve directory structure
count=0
for file in $FILES_WITH_CONDS; do
    # Get relative path from SOURCE_DIR
    relpath="${file#$SOURCE_DIR/}"

    # Create directory structure in OUT_DIR
    mkdir -p "$OUT_DIR/$(dirname "$relpath")"

    # Copy file
    cp "$file" "$OUT_DIR/$relpath"
    count=$((count + 1))
done

echo "Copied $count files to $OUT_DIR"
