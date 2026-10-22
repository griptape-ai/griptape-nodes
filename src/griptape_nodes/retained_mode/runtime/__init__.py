"""What one open workflow is: its runtime and the state it holds.

`WorkflowRuntime` holds one typed attribute per concern, each defined in a module of this package.
These are data and the operations on that data alone; managers hold the behavior that needs other
managers or events. `OpenWorkflowSet` holds the runtimes of the workflows the engine has open.
"""
