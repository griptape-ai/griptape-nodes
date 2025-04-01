Param(
    [string]$API_KEY
)

# --- Set up paths and variables ---
$ConfigDir = Join-Path $Env:APPDATA "griptape_nodes"
$ConfigFile = Join-Path $ConfigDir "griptape_nodes_config.json"

# --- Write/update the config file if API key is provided ---
if ($API_KEY) {
    # Ensure the config directory exists
    if (!(Test-Path $ConfigDir)) {
        New-Item -ItemType Directory -Path $ConfigDir | Out-Null
    }

    # Check if the file already exists
    if (Test-Path $ConfigFile) {
        Write-Host "A config file already exists at '$ConfigFile', overwriting..."
    } 
        # Write the API key to the config file
'{
  "env": {
      "Griptape": {
        "GT_CLOUD_API_KEY": "' + $API_KEY + '"
      }
  }
}' | Out-File $ConfigFile
    Write-Host "API key saved to $ConfigFile"
} else {
    Write-Host "No API key provided. Skipping config file creation."
}

Write-Host "`nInstalling uv...`n"
try {
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
} catch {
    Write-Host "Failed to install uv with the default method. You may need to install it manually."
}

# Verify uv is on the user's PATH
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Griptape Nodes dependency 'uv' was installed, but requires the terminal to be restarted to be run."
    Write-Host "Please close this terminal and open a new one, then run the install command you performed earlier."
    return
}

Write-Host "`nInstalling Griptape Nodes Engine...`n"
uv tool install --force --python python3.13 --from "git+https://github.com/griptape-ai/griptape-nodes.git@latest" griptape_nodes

# --- Install Griptape Nodes Library and Scripts ---
if (-not $Env:XDG_DATA_HOME) {
    $Env:XDG_DATA_HOME = Join-Path $Env:LOCALAPPDATA ".local\share"
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
Copy-Item -Path (Join-Path $RepoName "nodes") -Destination (Join-Path $DestDir "nodes") -Recurse -Force

# Copy the scripts/ directory
Copy-Item -Path (Join-Path $RepoName "scripts") -Destination (Join-Path $DestDir "scripts") -Recurse -Force

Pop-Location
Remove-Item -Recurse -Force $TmpDir

Write-Host "`nInstallation complete!`n"
Write-Host "Run 'griptape-nodes' (or just 'gtn') to start the engine."
Write-Host ""
