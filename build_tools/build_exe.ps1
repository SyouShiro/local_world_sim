Param(
  [switch]$NoObf,
  [switch]$NoConsole
)

$ErrorActionPreference = "Stop"

Write-Host "Installing build dependencies..."
conda run -n local_world_sim python -m pip install --upgrade pip
conda run -n local_world_sim python -m pip install pyinstaller pyarmor

if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

$entry = "build_tools/pack_entry.py"
$pyPath = "backend"

if ($NoObf) {
  Write-Host "Building without obfuscation..."
  $paths = @("--paths", $pyPath)
  $script = $entry
} else {
  Write-Host "Obfuscating with PyArmor..."
  conda run -n local_world_sim pyarmor gen -O build/obf -r $entry backend/app
  $paths = @("--paths", "build/obf")
  $script = "build/obf/pack_entry.py"
}

$uiData = "frontend;frontend"
$name = "worldline_sim"

$pyinstallerArgs = @(
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name", $name,
  "--add-data", $uiData
) + $paths + @(
  "--hidden-import", "app",
  "--hidden-import", "app.main",
  "--collect-submodules", "app",
  "--collect-all", "uvicorn",
  "--collect-all", "fastapi",
  "--collect-all", "sqlalchemy",
  "--collect-all", "aiosqlite",
  "--collect-all", "pydantic",
  "--collect-all", "pydantic_settings",
  $script
)

if ($NoConsole) {
  $pyinstallerArgs = @("--noconsole") + $pyinstallerArgs
}

Write-Host "Running PyInstaller..."
conda run -n local_world_sim pyinstaller @pyinstallerArgs

Write-Host "Done. Output: dist/$name.exe"
