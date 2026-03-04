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

# Check if uv is already installed
$existingUv = Get-Command uv -ErrorAction SilentlyContinue
if ($existingUv) {
    ColorWrite "uv is already installed. Using existing installation..." 'Cyan'
    $uvInstallPath = $existingUv.Source
} else {
    ColorWrite "Installing uv..." 'Cyan'
    $env:UV_UNMANAGED_INSTALL = Join-Path $env:USERPROFILE '.local\share\griptape_nodes\bin'
    $uvInstallPath = Join-Path $env:USERPROFILE '.local\share\griptape_nodes\bin\uv.exe'
    try {
        powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex" > $null
    } catch {
        ColorWrite "Failed to install uv with the default method. You may need to install it manually." 'Red'
        exit 1
    }
}
ColorWrite "uv installed successfully." 'Green'

ColorWrite "`nInstalling Griptape Nodes Engine...`n" 'Cyan'

# Verify uv installation
if (-not (Test-Path $uvInstallPath)) {
    ColorWrite "Error: uv installation failed at expected path: $uvInstallPath" 'Red'
    exit 1
}

# Install griptape-nodes
& $uvInstallPath tool install --force --python python3.12 griptape-nodes > $null

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
