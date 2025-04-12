# Frequently Asked Questions

## Where does my stuff save?

Run this command in your terminal to reveal where stuff is stored:

For Mac/Linux:
```bash
find ~/.local -name "*griptape*" -o -name "*gtn*" | sort
```

For Windows PowerShell:
```powershell
Get-ChildItem -Path $env:LOCALAPPDATA -Recurse -Filter "*griptape*" | Select-Object FullName
```

## Where is Griptape [nodes] installed?

Looking for the exact installation location of your Griptape [nodes]? This command will show you precisely where it's installed:

For Mac/Linux:
```bash
echo -e "Main executable: $(readlink -f $(which gtn))\nApp directory: $(find ~/.local/share -type d -name "griptape_nodes" -o -name "griptape-nodes" | head -1)"
```

For Windows PowerShell:
```powershell
Write-Host "Main executable: $(Get-Command gtn | Select-Object -ExpandProperty Source)"
Write-Host "App directory: $(Get-ChildItem -Path $env:LOCALAPPDATA -Recurse -Directory -Filter "*griptape*" | Select-Object -First 1 -ExpandProperty FullName)"
```

## How do I uninstall?

Need to part ways with Griptape [nodes]? It's a simple goodbye with a single command:

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