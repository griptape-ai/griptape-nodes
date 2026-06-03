# Libraries

A **library** is a bundle of nodes you can use in the editor. Some
ship with the engine, some you install from a Git URL, some you write
yourself. This page is for the artist installing and using libraries
— not the developer authoring them. (Library authors: see the
[Custom Nodes guide](developing_nodes/index.md) and
[Worker Mode](developing_nodes/worker_mode.md).)

If you're worried about installing two libraries that conflict, jump
to [Coexistence guarantees](#coexistence-guarantees) — the short
answer is that Python dependency conflicts cannot break your engine,
but two libraries with the same node name can be ambiguous and the
engine will tell you about it.

## What you start with

A fresh engine install gives you the **Sandbox Library** — a
scratchpad library that picks up `.py` node files from the sandbox
directory configured in your settings. What you see in the editor's
Sandbox category depends on what's actually in that directory; if
the directory isn't set or doesn't exist, the Sandbox Library is
empty.

During `gtn init`, you're offered the **Advanced Media Library**
(diffusion, image generation, video). You can register it then or
re-run `gtn init` later to add it. See the
[FAQ](faq.md#how-do-i-install-the-advanced-media-library-after-initial-setup)
for that path.

Other libraries — first-party or community — you install yourself.

## Installing a library

Two CLI commands, both via the `gtn` command (also spelled
`griptape-nodes`). `gtn` is the command-line tool the engine
installs alongside the editor; you run it from a terminal (Terminal
on macOS, PowerShell or Command Prompt on Windows, any shell on
Linux). If `gtn` isn't found, the engine installation didn't add it
to your PATH — see [Installation](installation.md).

### `gtn libraries download <git_url>`

Clone a library's Git repository and register it. The library's
`griptape-nodes-library.json` (its **manifest** — the file that
describes the library) is read; the library is added to your config
so it auto-loads on every future engine start. Dependencies are
installed at download time, before the command returns.

```bash
gtn libraries download https://github.com/some-org/some-library.git
```

If the URL is wrong, the repo is private and you don't have
credentials, the manifest is missing, or the target directory
already exists, the command returns a clear failure. A failed
download may leave a partially cloned directory on disk; if you
retry, pass `--overwrite` or remove that directory first.

Optional flags include `--branch`, `--target-dir`, and `--overwrite`.
Run `gtn libraries download --help` for the full list.

### `gtn libraries sync`

Update every registered library to its latest version. For each
library:

1. Pulls the latest commit from its Git remote (or, if the library
   was installed from a Git tag rather than a branch, re-fetches
   that tag in case it points to a new commit).
2. Re-installs the library's pinned dependencies into its
   per-library virtual environment.
3. Reloads the library in place so the new code and dependencies
   take effect immediately. You do not need to restart the engine.

Sync respects uncommitted changes: if you have local edits in a
library's clone, sync fails for that library and tells you so. Use
`gtn libraries sync --overwrite` only if you want to discard those
edits.

## Coexistence guarantees

The point of installing two libraries side-by-side is that they
can't break each other. Three layers control how well that holds:

### Python dependency isolation

Every registered library gets its own **virtual environment** — an
isolated set of Python packages that doesn't share state with the
engine's own packages or with any other library's. Library A can
pin `torch==2.4.1`; library B can pin `torch==2.0.0`. Both are
installed into separate `.venv` directories. When the engine loads
a library, it uses that library's `.venv` for that library's
imports.

For libraries that opt into [worker mode](developing_nodes/worker_mode.md),
the virtual environment is created and used inside the worker
subprocess rather than alongside the engine; from the artist's
perspective the isolation is the same, but if you go looking for
the `.venv` directory on disk you may not see it until the worker
has run for the first time.

**You can install incompatibly-pinned libraries together without
pip resolution conflicts.** This is the most important guarantee on
this page.

### Process isolation: opt-in via worker mode

If a library opts into worker mode (a `worker.enabled = true` entry
in its `griptape-nodes-library.json`), its nodes run in a separate
process from the rest of the engine. That gives you:

- **Fault tolerance.** If the library crashes, only that library
  goes down — the rest of the engine keeps running.
- **Resource isolation.** Anything the library loads into memory
  (model weights, GPU memory, background threads) lives in the
  library's own process and can't degrade other libraries.

Heavy ML libraries (diffusion, transformers, custom CUDA stacks)
typically opt in. Lightweight libraries (simple HTTP / data nodes)
typically don't.

You can tell whether a library is worker-isolated by looking at its
`griptape-nodes-library.json`: a `"worker": { "enabled": true }`
block under `metadata` means the library runs in its own process.

### Node-name collisions: not solved

If two libraries register a node class with the same name (e.g.
both ship a `MyImageNode`), the engine accepts both. **The engine
does not warn you at install time.** When you create that node:

- If the editor or your workflow names the library explicitly, it
  works.
- If it doesn't, the engine raises an error listing both libraries
  so you can disambiguate.

This is the one coexistence concern the engine doesn't solve for
you. If you suspect a collision, the safest fix is to remove the
library you don't want from your config (see
[I want to remove a library](#i-want-to-remove-a-library)).

## When something goes wrong

The "engine console" referenced below is the terminal window where
the engine is running — the same window you launched the engine
from. Error lines from libraries appear there with a `Worker-<id>`
prefix when they come from a worker library.

### "I installed the library but I don't see its nodes"

Most likely the library's dependencies failed to install. Check the
engine console for `Failed to install dependencies` lines. Common
causes:

- The library pins a wheel (a pre-built Python package) that doesn't
  exist for your Python version or platform — for example a `torch`
  wheel for an unsupported CUDA version.
- Your network blocked the install (corporate proxy, or no internet
  during the install step).
- Disk full (the engine reports this explicitly).

Fix the underlying issue, then re-run `gtn libraries sync`.

### "A node looks broken or red in the editor"

The engine couldn't construct that node — usually because its
library failed to load. The editor swaps in a placeholder so your
workflow file isn't corrupted. Check the engine console for the
library's load error; once you fix it (typically re-run
`gtn libraries sync`), reopening the workflow will use the real
node again.

### I want to remove a library

Edit `~/.config/griptape_nodes/griptape_nodes_config.json` (or the
platform equivalent — see [Engine Configuration](configuration.md))
and remove the library's entry from the
`app_events.on_app_initialization_complete.libraries_to_register`
list. On the next engine start it won't load. The clone on disk
stays put; delete its directory manually if you want the disk
space back.

## Where libraries are stored on disk

- **Config**: `~/.config/griptape_nodes/griptape_nodes_config.json`
  (or the platform equivalent — see
  [Engine Configuration](configuration.md)). The
  `app_events.on_app_initialization_complete.libraries_to_register`
  list inside it controls what loads.
- **Clones / venvs**: in the directory you cloned the library into
  (which becomes the directory containing the library's
  `griptape-nodes-library.json`); the `.venv` lives next to that
  manifest.
- **Sandbox library**: the sandbox directory is configured
  separately in your settings; defaults vary by platform.

## Quick reference

| You want to | Run |
|---|---|
| Install a library from Git | `gtn libraries download <git_url>` |
| Update all libraries | `gtn libraries sync` |
| Discard local edits while syncing | `gtn libraries sync --overwrite` |
| Remove a library | Edit `app_events.on_app_initialization_complete.libraries_to_register` in your config |
| Re-register Advanced Media Library | `gtn init`, answer `y` |
| See full options for a command | `gtn libraries <command> --help` |

For library authors: see [Custom Nodes](developing_nodes/index.md)
and [Worker Mode](developing_nodes/worker_mode.md).
