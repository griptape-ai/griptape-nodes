# Stop immediately on errors
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# 2. Install uv if needed
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

# 3. Download the latest Griptape Nodes release archive (.zip)
Write-Host "`nDownloading the Griptape Nodes release (.zip)...`n"
$zipFile = "griptape-nodes-latest.zip"
Invoke-WebRequest `
    -Uri "https://github.com/griptape-ai/griptape-nodes/archive/refs/tags/latest.zip" `
    -OutFile $zipFile

# 4. Install the Griptape Nodes engine from that local .zip
Write-Host "`nInstalling Griptape Nodes Engine from the .zip...`n"
uv tool install --force --python python3.13 .\griptape-nodes-latest.zip

# 5. Extract from the same .zip to copy library/workflow files
Write-Host "`nExtracting library + workflow files...`n"
if (-not $Env:XDG_DATA_HOME) {
    $Env:XDG_DATA_HOME = Join-Path $HOME ".local\share"
}

# Make a temporary folder to extract into
$tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $tmpDir | Out-Null

Expand-Archive -LiteralPath $zipFile -DestinationPath $tmpDir

# The extracted folder is typically: griptape-nodes-latest
# We'll build that name and confirm it exists
# (We know there's only one top-level folder in the .zip)
$topLevelDir = Join-Path $tmpDir "griptape-nodes-latest"

if (-not (Test-Path $topLevelDir)) {
    Write-Host "Error: Could not find top-level extracted directory."
    exit 1
}

# Make sure the final library folder exists
$destDir = Join-Path $Env:XDG_DATA_HOME "griptape_nodes"
if (-not (Test-Path $destDir)) {
    New-Item -ItemType Directory -Path $destDir | Out-Null
}

# Copy over 'nodes' and 'workflows' from the extracted folder
Copy-Item -Path (Join-Path $topLevelDir "nodes") -Destination $destDir -Recurse -Force
Copy-Item -Path (Join-Path $topLevelDir "workflows") -Destination $destDir -Recurse -Force

# Clean up
Remove-Item -LiteralPath $tmpDir -Recurse -Force
Remove-Item -LiteralPath $zipFile -Force

Write-Host "**************************************"
Write-Host "*      Installation complete!        *"
Write-Host "*  Run 'griptape-nodes' (or 'gtn')   *"
Write-Host "*      to start the engine.          *"
Write-Host "**************************************"

