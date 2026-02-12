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

function Get-RequirementImports {
  param(
    [string]$RequirementsPath
  )

  if (-not (Test-Path $RequirementsPath)) {
    throw "Requirements file not found: $RequirementsPath"
  }

  $distributionToModule = @{
    "pydantic-settings" = "pydantic_settings"
    "python-dotenv"     = "dotenv"
  }

  $imports = New-Object System.Collections.Generic.List[string]
  Get-Content $RequirementsPath | ForEach-Object {
    $line = ($_ -replace "^\uFEFF", "").Trim()
    if (-not $line) { return }
    if ($line.StartsWith("#")) { return }
    $line = ($line -split "#", 2)[0].Trim()
    if (-not $line) { return }
    $line = ($line -split ";", 2)[0].Trim()
    if (-not $line) { return }

    $match = [regex]::Match($line, '^([A-Za-z0-9._-]+)(\[[^\]]+\])?')
    if (-not $match.Success) { return }
    $distributionName = $match.Groups[1].Value.ToLowerInvariant()
    if ($distributionToModule.ContainsKey($distributionName)) {
      $imports.Add($distributionToModule[$distributionName])
      return
    }

    $moduleName = $distributionName.Replace("-", "_").Replace(".", "_")
    if ($moduleName) {
      $imports.Add($moduleName)
    }
  }

  return $imports | Sort-Object -Unique
}

Write-Host "Installing build dependencies..."
conda run -n local_world_sim python -m pip install --upgrade pip
conda run -n local_world_sim python -m pip install -r backend/requirements.txt
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

$collectAllImports = @()
Get-RequirementImports -RequirementsPath "backend/requirements.txt" | ForEach-Object {
  $collectAllImports += @("--collect-all", $_)
}

if ($collectAllImports.Count -eq 0) {
  throw "No dependency modules discovered from backend/requirements.txt"
}

$collectModuleNames = @($collectAllImports | Where-Object { $_ -ne "--collect-all" } | Sort-Object -Unique)
Write-Host "Collect-all modules:" ($collectModuleNames -join ", ")

$pyinstallerArgs = @(
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name", $name,
  "--add-data", $uiData
) + $paths + $hiddenImports + $collectAllImports + @($script)

if ($NoConsole) {
  $pyinstallerArgs = @("--noconsole") + $pyinstallerArgs
}

Write-Host "Running PyInstaller..."
conda run -n local_world_sim pyinstaller @pyinstallerArgs

Write-Host "Done. Output: dist/$name.exe"
