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
    exit 1
}
ColorWrite "uv installed successfully." 'Green'

ColorWrite "`nInstalling Griptape Nodes Engine...`n" 'Cyan'
$localBin = Join-Path $env:USERPROFILE '.local\bin'
$uvPath = Join-Path $localBin 'uv.exe'

# Install griptape-nodes
& $uvPath tool install --force --python python3.12 griptape-nodes > $null

if (-not (Get-Command griptape-nodes -ErrorAction SilentlyContinue)) {
    ColorWrite "**************************************" 'Green'
    ColorWrite "*      Installation complete!        *" 'Green'
    ColorWrite "*  Restart your terminal and run     *" 'Green'
    ColorWrite "*  'griptape-nodes' (or 'gtn')       *" 'Green'
    ColorWrite "*      to start the engine.          *" 'Green'
    ColorWrite "**************************************" 'Green'
} else {
    ColorWrite "**************************************" 'Green'
    ColorWrite "*      Installation complete!        *" 'Green'
    ColorWrite "*  Run 'griptape-nodes' (or 'gtn')   *" 'Green'
    ColorWrite "*      to start the engine.          *" 'Green'
    ColorWrite "**************************************" 'Green'
}
