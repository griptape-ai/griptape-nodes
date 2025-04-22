# Frequently Asked Questions

## Where is my workspace (where do my files save)?

Run this command and it will report back your workspace location:

```bash
gtn config | grep workspace
```

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

## How do I uninstall?

Need to part ways with Griptape Nodes? It's a simple goodbye with a single command:

```bash
griptape-nodes uninstall
```

When regret inevitably washes over you, have no fear. Open arms await; just revisit [Getting Started](getting_started.md)

## Where can I provide feedback or ask questions?

You can connect with us through several channels:

- [Website](https://www.griptape.ai) - Visit our homepage for general information
- [Discord](https://discord.gg/gnWRz88eym) - Join our community for questions and discussions
- [GitHub](https://github.com/griptape-ai/griptape-nodes) - Submit issues or contribute to the codebase

These same links are also available as the three icons in the footer (bottom right) of every documentation page.
