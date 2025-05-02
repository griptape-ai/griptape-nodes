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
    powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
} catch {
    ColorWrite "Failed to install uv with the default method. You may need to install it manually." 'Red'
    exit
}

# Verify uv is on the user's PATH
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    ColorWrite "Error: Griptape Nodes dependency 'uv' was installed but requires the terminal instance to be restarted to be run." 'Red'
    ColorWrite "Please close this terminal, open a new terminal, and then re-run the install command you performed earlier." 'Red'
    exit 1
}

ColorWrite "`nInstalling Griptape Nodes Engine...`n" 'Cyan'
uv tool install --force --python python3.12 griptape-nodes

ColorWrite "**************************************" 'Green'
ColorWrite "*      Installation complete!        *" 'Green'
ColorWrite "*  Run 'griptape-nodes' (or 'gtn')   *" 'Green'
ColorWrite "*      to start the engine.          *" 'Green'
ColorWrite "**************************************" 'Green'

