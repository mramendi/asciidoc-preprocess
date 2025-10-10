#!/usr/bin/env python3
"""
Test script to demonstrate YAML schema validation.
Creates various invalid configurations and shows the error messages.
"""

import yaml
import tempfile
import os
import sys

# Add current directory to path to import the preprocessor module
sys.path.insert(0, '.')
exec(open('preprocess-conditionals-v4.py').read().replace('if __name__ == "__main__":', 'if False:'))

def test_config(description, config_dict):
    """Test a configuration and print the result."""
    print(f"\n{'='*70}")
    print(f"Test: {description}")
    print(f"{'='*70}")

    # Create a temporary YAML file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_dict, f)
        temp_path = f.name

    try:
        config = load_config(temp_path)
        print("✓ Configuration loaded successfully (unexpected!)")
    except SystemExit as e:
        print("✗ Configuration rejected (expected)")
    finally:
        os.unlink(temp_path)

# Test 1: Missing required 'attributes' key
test_config(
    "Missing 'attributes' key",
    {
        "conditionals": [
            {"name": "azure", "attribute": "platform", "value": "azure"}
        ]
    }
)

# Test 2: Missing required 'conditionals' key
test_config(
    "Missing 'conditionals' key",
    {
        "attributes": {
            "platform": ["azure", "aws"]
        }
    }
)

# Test 3: Conditional references non-existent attribute
test_config(
    "Conditional references non-existent attribute",
    {
        "attributes": {
            "platform": ["azure", "aws"]
        },
        "conditionals": [
            {"name": "rhel", "attribute": "product", "value": "rhel"}
        ]
    }
)

# Test 4: Conditional uses value not in attribute's list
test_config(
    "Conditional uses value not in attribute's list",
    {
        "attributes": {
            "platform": ["azure", "aws"]
        },
        "conditionals": [
            {"name": "gcp", "attribute": "platform", "value": "gcp"}
        ]
    }
)

# Test 5: Duplicate conditional names
test_config(
    "Duplicate conditional names",
    {
        "attributes": {
            "platform": ["azure", "aws"]
        },
        "conditionals": [
            {"name": "azure", "attribute": "platform", "value": "azure"},
            {"name": "azure", "attribute": "platform", "value": "aws"}
        ]
    }
)

# Test 6: Missing required field in conditional
test_config(
    "Missing 'value' field in conditional",
    {
        "attributes": {
            "platform": ["azure", "aws"]
        },
        "conditionals": [
            {"name": "azure", "attribute": "platform"}
        ]
    }
)

# Test 7: Empty attributes
test_config(
    "Empty attributes dictionary",
    {
        "attributes": {},
        "conditionals": []
    }
)

# Test 8: Invalid attribute name (doesn't match pattern)
test_config(
    "Invalid attribute name with spaces",
    {
        "attributes": {
            "invalid name": ["value1", "value2"]
        },
        "conditionals": []
    }
)

# Test 9: Attribute with empty values array
test_config(
    "Attribute with empty values array",
    {
        "attributes": {
            "platform": []
        },
        "conditionals": []
    }
)

# Test 10: Attribute with duplicate values
test_config(
    "Attribute with duplicate values",
    {
        "attributes": {
            "platform": ["azure", "azure", "aws"]
        },
        "conditionals": [
            {"name": "azure", "attribute": "platform", "value": "azure"}
        ]
    }
)

print(f"\n{'='*70}")
print("All validation tests completed!")
print(f"{'='*70}\n")
