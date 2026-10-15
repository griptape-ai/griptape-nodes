# Undo and Redo

Undo takes back your last change to the workflow, and Redo puts it back. You can step back through
the last 100 changes.

| Action | macOS       | Windows / Linux        |
| ------ | ----------- | ---------------------- |
| Undo   | Cmd+Z       | Ctrl+Z                 |
| Redo   | Shift+Cmd+Z | Shift+Ctrl+Z or Ctrl+Y |

The **Undo** and **Redo** buttons at the left of the canvas toolbar do the same. Hover over one to see
what it will undo or redo, such as "Undo Move 3 nodes". A short message at the bottom of the canvas
confirms each step.

While you're typing in a text field, these shortcuts undo and redo your typing in that field instead.

## What you can undo

- Adding, deleting, duplicating, and pasting nodes
- Moving, resizing, collapsing, and arranging nodes
- Changing a parameter's value
- Connecting and disconnecting parameters
- Renaming and locking nodes
- Creating groups, deleting them, and moving nodes in and out of them
- Adding and removing parameters on nodes that let you

Each action is one step, however much it changes. Dragging ten nodes, pasting a group, or deleting a
node along with its connections all undo with a single press.

Undoing a change to a node's parameters marks the node as needing to run again, the same as changing
it by hand.

## What isn't undone

- **Running a workflow.** Results stay as they are. Undo and Redo are unavailable while a workflow
    is running.
- **Saving.** Undo changes what's on the canvas, not the saved file. Save again to keep the result.
- **Settings, libraries, and workflow variables.**

Opening or switching workflows starts a fresh history. Reloading the editor keeps it, because the
history lives in the engine. Restarting the engine clears it.

Changes made by the [assistant](../agent/index.md) or an
[external MCP client](../mcp/external_clients.md) can be undone too, one tool call at a time.

## When a step can't be undone

Undo puts back exactly what the step changed. If something outside the history has changed the
same part of the workflow since, for example a node the step would reconnect to was deleted by a
library, Undo leaves the workflow as it is and shows a warning instead. That step is dropped, and
the next Undo goes on to the step before it.
