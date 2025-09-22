#!/usr/bin/env python3
"""Test the execute method in the advanced media library."""

import sys
import os

# Add the source directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from griptape_nodes.common.node_executor import NodeExecutor


def test_media_library_execute():
    """Test that the execute method is available from the media library."""
    print("🧪 Testing Advanced Media Library Execute Method")
    print("=" * 50)

    # Get the NodeExecutor singleton and refresh methods
    executor = NodeExecutor()
    executor.refresh()

    # List available methods
    methods = executor.list_methods()
    print(f"📋 Available methods ({len(methods)}):")
    for method in methods:
        print(f"  • {method}")

    # Test if execute method is available
    if "execute" in methods:
        print(f"\n✅ Found 'execute' method from Advanced Media Library")

        # Create a mock node for testing
        class MockNode:
            def __init__(self, name: str):
                self.name = name

        mock_node = MockNode("test_node")

        try:
            # Test calling the execute method
            result = executor.execute_method("execute", mock_node)
            print(f"✅ Successfully called execute method: {result}")
        except Exception as e:
            print(f"❌ Error calling execute method: {e}")
    else:
        print(f"\n❌ 'execute' method not found")
        print(f"Available methods: {methods}")

    print(f"\n🎉 Test completed!")


if __name__ == "__main__":
    test_media_library_execute()