Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "`nInstalling uv...`n"
try {
    powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
} catch {
    Write-Host "Failed to install uv with the default method. You may need to install it manually."
    exit
}

# Verify uv is on the user's PATH
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Griptape Nodes dependency 'uv' was installed but requires the terminal instance to be restarted to be run."
    Write-Host "Please close this terminal, open a new terminal, and then re-run the install command you performed earlier."
    exit 1
}

uv tool install --force --python python3.12 git+https://github.com/griptape-ai/griptape-nodes

Write-Host "**************************************"
Write-Host "*      Installation complete!        *"
Write-Host "*  Run 'griptape-nodes' (or 'gtn')   *"
Write-Host "*      to start the engine.          *"
Write-Host "**************************************"
