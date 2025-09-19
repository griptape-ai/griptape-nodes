#!/usr/bin/env python3
"""Test script for the Executor class functionality."""

import sys
import os

# Add the source directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from griptape_nodes.executor import Executor, ExecutorMethod, executor_method
from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
from griptape_nodes.node_library.library_registry import LibraryRegistry, Library, LibrarySchema, LibraryMetadata, NodeDefinition, NodeMetadata, Dependencies
from griptape_nodes.exe_types.node_types import BaseNode


class SampleAdvancedLibrary(AdvancedNodeLibrary):
    """Sample advanced library with executor methods."""

    def utility_method(self, x: int, y: int) -> int:
        """Add two numbers together."""
        return x + y

    def format_text(self, text: str, prefix: str = "Result: ") -> str:
        """Format text with a prefix."""
        return f"{prefix}{text}"

    def calculate_stats(self, numbers: list[int]) -> dict:
        """Calculate basic statistics for a list of numbers."""
        if not numbers:
            return {"count": 0, "sum": 0, "mean": 0, "min": 0, "max": 0}

        return {
            "count": len(numbers),
            "sum": sum(numbers),
            "mean": sum(numbers) / len(numbers),
            "min": min(numbers),
            "max": max(numbers)
        }


class SampleNode(BaseNode):
    """Sample node class with executor methods."""

    @staticmethod
    @executor_method
    def executor_validate_email(email: str) -> bool:
        """Validate if a string is a valid email format."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    @executor_method
    def string_utilities_executor(text: str, operation: str) -> str:
        """Perform various string operations."""
        if operation == "upper":
            return text.upper()
        elif operation == "lower":
            return text.lower()
        elif operation == "reverse":
            return text[::-1]
        elif operation == "length":
            return str(len(text))
        else:
            return text


def test_executor():
    """Test the Executor class functionality."""
    print("🚀 Testing Executor Class")
    print("=" * 50)

    # Create a sample library for testing
    print("\n📦 Creating sample library...")

    library_data = LibrarySchema(
        name="test_library",
        library_schema_version="0.2.0",
        metadata=LibraryMetadata(
            author="Test Author",
            description="Test library for executor functionality",
            library_version="1.0.0",
            engine_version="1.0.0",
            tags=["test", "executor"],
            dependencies=Dependencies()
        ),
        categories=[],
        nodes=[
            NodeDefinition(
                class_name="SampleNode",
                file_path="sample_node.py",
                metadata=NodeMetadata(
                    category="test",
                    description="Sample node for testing",
                    display_name="Sample Node",
                    tags=["test"]
                )
            )
        ]
    )

    # Create advanced library instance
    advanced_library = SampleAdvancedLibrary()

    # Register the library
    try:
        library = LibraryRegistry.generate_new_library(
            library_data,
            mark_as_default_library=True,
            advanced_library=advanced_library
        )

        # Manually register the node class for testing
        library.register_new_node_type(SampleNode, NodeMetadata(
            category="test",
            description="Sample node for testing",
            display_name="Sample Node",
            tags=["test"]
        ))

        print(f"✅ Created library: {library_data.name}")

    except KeyError as e:
        print(f"⚠️ Library already exists: {e}")
        library = LibraryRegistry.get_library("test_library")

    # Test the Executor
    print("\n🔧 Testing Executor functionality...")
    executor = Executor()

    # Refresh methods to load from registered libraries
    print("Loading methods from libraries...")
    executor.refresh_methods()

    # List all available methods
    print(f"\n📋 Available methods ({len(executor.list_methods())}):")
    for method in executor.list_methods():
        print(f"  • {method.name} ({method.source_type} from {method.library_name})")
        print(f"    └─ {method.description}")

    print("\n🧪 Testing method execution:")

    # Test advanced library methods
    print("\n1. Testing advanced library methods:")
    try:
        if executor.has_method("utility_method"):
            result = executor.execute("utility_method", 5, 3)
            print(f"   utility_method(5, 3) = {result}")

        if executor.has_method("format_text"):
            result = executor.execute("format_text", "Hello World", ">>> ")
            print(f"   format_text('Hello World', '>>> ') = '{result}'")

        if executor.has_method("calculate_stats"):
            result = executor.execute("calculate_stats", [1, 2, 3, 4, 5])
            print(f"   calculate_stats([1,2,3,4,5]) = {result}")

    except Exception as e:
        print(f"   ❌ Error testing advanced library methods: {e}")

    # Test node class methods
    print("\n2. Testing node class methods:")
    try:
        if executor.has_method("validate_email"):
            result1 = executor.execute("validate_email", "test@example.com")
            result2 = executor.execute("validate_email", "invalid-email")
            print(f"   validate_email('test@example.com') = {result1}")
            print(f"   validate_email('invalid-email') = {result2}")

        if executor.has_method("string_utilities"):
            result = executor.execute("string_utilities", "Hello", "upper")
            print(f"   string_utilities('Hello', 'upper') = '{result}'")

    except Exception as e:
        print(f"   ❌ Error testing node methods: {e}")

    # Test method information
    print("\n📊 Method information:")
    for method_name in ["utility_method", "validate_email"]:
        if executor.has_method(method_name):
            method_info = executor.get_method_info(method_name)
            signature = executor.get_method_signature(method_name)
            print(f"   {method_name}: {signature}")

    # Test error handling
    print("\n⚠️ Testing error handling:")
    try:
        executor.execute("non_existent_method")
    except KeyError as e:
        print(f"   ✅ Correctly caught KeyError: {e}")

    print(f"\n🎉 Executor testing completed!")
    print(f"   Total methods loaded: {len(executor.list_methods())}")


if __name__ == "__main__":
    test_executor()