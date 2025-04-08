if (Get-Process griptape-nodes -ErrorAction SilentlyContinue) {
    Write-Host "Error: an instance of 'griptape-nodes' is currently running. Please close it before continuing."
    exit
}

Write-Host "`nInstalling uv...`n"
try {
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
} catch {
    Write-Host "Failed to install uv with the default method. You may need to install it manually."
    exit 
}

# Verify uv is on the user's PATH
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Griptape Nodes dependency 'uv' was installed, but requires the terminal to be restarted to be run."
    Write-Host "Please close this terminal and open a new one, then run the install command you performed earlier."
    exit
}

Write-Host "`nInstalling Griptape Nodes Engine...`n"
uv tool install --force --python python3.13 --from "git+https://github.com/griptape-ai/griptape-nodes.git@latest" griptape_nodes

# --- Install Griptape Nodes Library and Scripts ---
if (-not $Env:XDG_DATA_HOME) {
    $Env:XDG_DATA_HOME = Join-Path $HOME ".local\share"
}

Write-Host "`nInstalling Griptape Nodes Library...`n"
$RepoName = "griptape-nodes"
$TmpDir = New-TemporaryFile
Remove-Item $TmpDir
New-Item -ItemType Directory -Path $TmpDir | Out-Null

Push-Location $TmpDir

git clone --depth 1 --branch latest https://github.com/griptape-ai/griptape-nodes.git $RepoName

$DestDir = Join-Path $Env:XDG_DATA_HOME "griptape_nodes"
if (!(Test-Path $DestDir)) {
    New-Item -ItemType Directory -Path $DestDir | Out-Null
}

# Copy the nodes/ directory
Copy-Item -Path (Join-Path $RepoName "nodes") -Destination $DestDir -Recurse -Force

# Copy the scripts/ directory
Copy-Item -Path (Join-Path $RepoName "scripts") -Destination $DestDir -Recurse -Force

Pop-Location
Remove-Item -Recurse -Force $TmpDir

Write-Host "**************************************"
Write-Host "*      Installation complete!        *"
Write-Host "*  Run 'griptape-nodes' (or 'gtn')   *"
Write-Host "*      to start the engine.          *"
Write-Host "**************************************"
