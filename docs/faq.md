# Frequently Asked Questions

## Where is my workspace (where do my files save)?

Run this command and it will report back your workspace location:

```bash
gtn config show | grep workspace
```

## Can I run the Engine on a different machine than the Editor?

Absolutely! The Engine and Editor can run on completely separate machines. Just remember that any files you save or libraries you register will be stored on the machine where the Engine is running. So if you're looking for your files and can't find them right away, double-check which machine the Engine is running on.

## Where is Griptape Nodes installed?

Looking for the exact installation location of your Griptape Nodes? This command will show you precisely where it's installed:

For Mac/Linux:

```bash
dirname $(dirname $(readlink -f $(which griptape-nodes)))
```

For Windows PowerShell:

```powershell
$(Split-Path -Parent (Split-Path -Parent (Get-Command griptape-nodes | Select-Object -ExpandProperty Source)))
```

## Can I see or edit my config file?

You can! To get a path to the file, go to the top Settings menu in the Editor, and select **Copy Path to Settings**. That will copy the config file path to your clipboard.

If you prefer working in the command line, you can also use:

```
gtn config show
```

## How do I uninstall Griptape Nodes?

Need to part ways with Griptape Nodes? It's a simple goodbye with a single command:

```bash
griptape-nodes self uninstall
```

When regret inevitably washes over you, have no fear. Open arms await; just revisit [installation](installation.md)

## How do I update Griptape Nodes?

Griptape Nodes will automatically check if it needs to update every time it runs. If it does, you will be prompted to answer with a (y/n) response. Respond with a y and it will automatically update to the latest version of the Engine.

If you would like to _manually_ update, you can always use either of these commands:

```bash
griptape-nodes self update
griptape-nodes assets update
```

or

```bash
gtn self update
gtn assets update
```

## I'm seeing "failed to locate pyvenv.cfg: The system cannot find the file specified." - What should I do?

It is possible, that during a previous uninstall things were not _fully_ uninstalled. Simply perform an uninstall again, and then [re-install](installation.md).

## I'm seeing "Attempted to create a Flow with a parent 'None', but no parent with that name could be found." - What should I do?

The good news is, this is usually harmless, and you can usually disregard it. If you're getting it in a way that stops work, please restart your engine, and that should take care of it.

That said, we apologize for this elusive bug. We're working to catch and fix it as soon as possible. If you are so inclined, we'd be grateful if you wanted to [log a bug](https://github.com/griptape-ai/griptape-nodes/issues/new?template=bug_report.yml&title=Attempted%20to%20create%20flow%20with%20a%20parent%20%27None%27) and provide any context around what may have led to the issue when you see it!

## Where can I provide feedback or ask questions?

You can connect with us through several channels:

- [Website](https://www.griptape.ai) - Visit our homepage for general information
- [Discord](https://discord.gg/gnWRz88eym) - Join our community for questions and discussions
- [GitHub](https://github.com/griptape-ai/griptape-nodes) - Submit issues or contribute to the codebase

These same links are also available as the three icons in the footer (bottom right) of every documentation page.
