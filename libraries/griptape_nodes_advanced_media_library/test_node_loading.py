#!/usr/bin/env python3
"""
Pytest smoke test for loading each node class defined in the advanced media library JSON.
Based on library_manager.py implementation for dynamic node loading.
"""

import json
import importlib.util
import sys
from pathlib import Path
from typing import Any, List, Dict
import pytest


def load_module_from_file(file_path: Path) -> Any:
    """Dynamically load a module from a Python file."""
    # Generate a unique module name
    module_name = f"dynamic_module_{file_path.name.replace('.', '_')}_{hash(str(file_path))}"
    
    # Load the module specification
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module specification from {file_path}")
    
    # Create the module
    module = importlib.util.module_from_spec(spec)
    
    # Add to sys.modules to handle recursive imports
    sys.modules[module_name] = module
    
    # Execute the module
    try:
        spec.loader.exec_module(module)
    except Exception as err:
        # Clean up sys.modules on failure
        if module_name in sys.modules:
            del sys.modules[module_name]
        raise ImportError(f"Module at '{file_path}' failed to load with error: {err}") from err
    
    return module


def load_class_from_file(file_path: Path, class_name: str) -> Any:
    """Dynamically load a class from a Python file."""
    try:
        module = load_module_from_file(file_path)
    except ImportError as err:
        raise ImportError(f"Failed to load class '{class_name}': {err}") from err
    
    # Get the class
    try:
        node_class = getattr(module, class_name)
    except AttributeError as err:
        raise AttributeError(f"Class '{class_name}' not found in module '{file_path}'") from err
    
    return node_class


def get_library_nodes() -> List[Dict[str, str]]:
    """Load node definitions from the library JSON file."""
    script_dir = Path(__file__).parent
    library_json_path = script_dir / "griptape_nodes_library.json"
    
    if not library_json_path.exists():
        pytest.fail(f"Library JSON file not found at {library_json_path}")
    
    try:
        with open(library_json_path, 'r', encoding='utf-8') as f:
            library_data = json.load(f)
    except Exception as err:
        pytest.fail(f"Failed to load library JSON: {err}")
    
    nodes = library_data.get('nodes', [])
    if not nodes:
        pytest.fail("No nodes found in library JSON")
    
    return nodes


@pytest.mark.parametrize("node_data", get_library_nodes(), ids=lambda node: node.get('class_name', 'unknown'))
def test_node_loading(node_data: Dict[str, str]) -> None:
    """Test that each node class can be dynamically loaded successfully."""
    class_name = node_data.get('class_name')
    file_path = node_data.get('file_path')
    
    if not class_name or not file_path:
        print(f"{class_name or 'unknown'} failed to load with the following error:")
        print("Missing class_name or file_path in node definition")
        pytest.fail("Missing class_name or file_path in node definition")
    
    # Get base directory (same directory as this test file)
    base_dir = Path(__file__).parent
    
    # Resolve relative path to absolute path
    node_file_path = Path(file_path)
    if not node_file_path.is_absolute():
        node_file_path = base_dir / node_file_path
    
    # Check if file exists
    if not node_file_path.exists():
        print(f"{class_name} failed to load with the following error:")
        print(f"Node file not found: {node_file_path}")
        pytest.fail(f"Node file not found: {node_file_path}")
    
    # Try to load the class
    try:
        node_class = load_class_from_file(node_file_path, class_name)
        
        if node_class is None:
            print(f"{class_name} failed to load with the following error:")
            print(f"Failed to load class {class_name}")
            pytest.fail(f"Failed to load class {class_name}")
        
        if not hasattr(node_class, '__name__'):
            print(f"{class_name} failed to load with the following error:")
            print(f"Loaded object is not a proper class: {class_name}")
            pytest.fail(f"Loaded object is not a proper class: {class_name}")
        
        if node_class.__name__ != class_name:
            print(f"{class_name} failed to load with the following error:")
            print(f"Class name mismatch: expected {class_name}, got {node_class.__name__}")
            pytest.fail(f"Class name mismatch: expected {class_name}, got {node_class.__name__}")
        
        # Success case
        print(f"{class_name} loaded with no errors")
        
    except Exception as err:
        import traceback
        print(f"{class_name} failed to load with the following error:")
        print(traceback.format_exc())
        pytest.fail(f"Failed to load class {class_name}: {err}")


if __name__ == "__main__":
    # Allow running directly with python for debugging
    nodes = get_library_nodes()
    print(f"Found {len(nodes)} nodes to test")
    
    for i, node_data in enumerate(nodes, 1):
        class_name = node_data.get('class_name')
        file_path = node_data.get('file_path')
        print(f"[{i}/{len(nodes)}] Testing {class_name} from {file_path}")
        
        try:
            test_node_loading(node_data)
            print(f"  ✅ SUCCESS: {class_name}")
        except Exception as err:
            print(f"  ❌ FAILED: {class_name} - {err}")
            sys.exit(1)
    
    print("\n✅ ALL NODES LOADED SUCCESSFULLY!")