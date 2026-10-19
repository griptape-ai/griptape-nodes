"""What one open workflow is: its runtime, the state it holds, and how work is bound to it.

`WorkflowRuntime` holds one typed attribute per concern, each defined in a module of this package.
These are data and the operations on that data alone; managers hold the behavior that needs other
managers or events.
"""
