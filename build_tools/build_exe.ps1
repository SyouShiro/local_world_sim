Param(
  [switch]$NoObf,
  [switch]$NoConsole
)

$ErrorActionPreference = "Stop"

function Get-AppModuleNames {
  param(
    [string]$RootDir
  )

  $modules = New-Object System.Collections.Generic.List[string]
  Get-ChildItem -Path $RootDir -Recurse -Filter "*.py" | ForEach-Object {
    $fullPath = $_.FullName.Replace("\", "/")
    $marker = "/app/"
    $idx = $fullPath.IndexOf($marker)
    if ($idx -ge 0) {
      $relative = $fullPath.Substring($idx + 1) # app/...
      if ($relative.EndsWith("__init__.py")) {
        $pkg = $relative.Substring(0, $relative.Length - "__init__.py".Length).TrimEnd("/")
        if ($pkg) { $modules.Add(($pkg -replace "/", ".")) }
      } else {
        $moduleName = $relative.Substring(0, $relative.Length - ".py".Length) -replace "/", "."
        if ($moduleName) { $modules.Add($moduleName) }
      }
    }
  }
  return $modules | Sort-Object -Unique
}

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
  $moduleRoot = "backend/app"
} else {
  Write-Host "Obfuscating with PyArmor..."
  conda run -n local_world_sim pyarmor gen -O build/obf -r $entry backend/app
  $paths = @("--paths", "build/obf")
  $script = "build/obf/pack_entry.py"
  $moduleRoot = "build/obf/app"
}

$uiData = "frontend;frontend"
$name = "worldline_sim"
$hiddenImports = @()
Get-AppModuleNames -RootDir $moduleRoot | ForEach-Object {
  $hiddenImports += @("--hidden-import", $_)
}

if ($hiddenImports.Count -eq 0) {
  throw "No app modules discovered for hidden imports under: $moduleRoot"
}

$pyinstallerArgs = @(
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name", $name,
  "--add-data", $uiData
) + $paths + $hiddenImports + @(
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
