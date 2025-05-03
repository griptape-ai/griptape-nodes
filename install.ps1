Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --------- styling helpers ---------
Function ColorWrite {
    param(
        [string]$Text,
        [ConsoleColor]$Color = 'White'
    )
    Write-Host $Text -ForegroundColor $Color
}
# -----------------------------------

ColorWrite "`nInstalling uv...`n" 'Cyan'
try {
    powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex" > $null
} catch {
    ColorWrite "Failed to install uv with the default method. You may need to install it manually." 'Red'
    exit
}
ColorWrite "uv installed successfully." 'Green'

ColorWrite "`nInstalling Griptape Nodes Engine...`n" 'Cyan'
$uvPath = "$HOME\.local\bin\uv.exe"
# uv tool install --force --python python3.12 griptape-nodes
& $uvPath tool install --force --python python3.12 git+https://github.com/griptape-ai/griptape-nodes > $null

ColorWrite "**************************************" 'Green'
ColorWrite "*      Installation complete!        *" 'Green'
ColorWrite "*  Run 'griptape-nodes' (or 'gtn')   *" 'Green'
ColorWrite "*      to start the engine.          *" 'Green'
ColorWrite "**************************************" 'Green'

