# Frequently Asked Questions

## Where is my workspace (where do my files save)?

Run this command and it will report back your workspace location:

```bash
gtn config | grep workspace
```

- **Keep in mind** that the engine and editor can run in entirely different places, on different computers, even!
- It is possible, and even likely, that if you do _not_ shut down the engine on one machine, and try to go to [https://nodes.griptape.ai](https://nodes.griptape.ai) from another using the same account, you can easily end up in a situation where files save and load, and the libraries you've registered are not on the machine you are sitting at.

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

<a id="uninstall"></a>

## How do I uninstall?

Need to part ways with Griptape Nodes? It's a simple goodbye with a single command:

```bash
uv tool uninstall griptape-nodes
```

When regret inevitably washes over you, have no fear. Open arms await; just revisit [Getting Started](getting_started.md)

## failed to locate pyvenv.cfg: The system cannot find the file specified.

Seeing this message when trying to run or install griptape-nodes?

It is possible, that during a previous uninstall things were not _fully_ uninstalled. Simply run [uninstall](#uninstall) again, and then [re-install](getting_started.md).

## Where can I provide feedback or ask questions?

You can connect with us through several channels:

- [Website](https://www.griptape.ai) - Visit our homepage for general information
- [Discord](https://discord.gg/gnWRz88eym) - Join our community for questions and discussions
- [GitHub](https://github.com/griptape-ai/griptape-nodes) - Submit issues or contribute to the codebase

These same links are also available as the three icons in the footer (bottom right) of every documentation page.
