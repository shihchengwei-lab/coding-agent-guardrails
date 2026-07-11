param(
  [string]$Project = ".",
  [string]$Python = "",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ToolkitHome = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$Installer = Join-Path $ToolkitHome "installer/guardrails_installer.py"

function Resolve-PythonInvocation {
  if ($Python) {
    return @{ Exe = (Resolve-Path -LiteralPath $Python).Path; Prefix = @() }
  }
  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCommand) {
    return @{ Exe = $pythonCommand.Source; Prefix = @() }
  }
  $pyCommand = Get-Command py -ErrorAction SilentlyContinue
  if ($pyCommand) {
    return @{ Exe = $pyCommand.Source; Prefix = @("-3") }
  }
  throw "Python 3.11 or newer is required."
}

$PythonInfo = Resolve-PythonInvocation
& $PythonInfo.Exe @($PythonInfo.Prefix) -c `
  "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 or newer is required." }
$PythonExe = (& $PythonInfo.Exe @($PythonInfo.Prefix) -c "import sys; print(sys.executable)").Trim()

$Arguments = @(
  $Installer, "install", $Project,
  "--source", $ToolkitHome,
  "--python", $PythonExe
)
if ($DryRun) { $Arguments += "--dry-run" }
& $PythonInfo.Exe @($PythonInfo.Prefix) @Arguments
if ($LASTEXITCODE -ne 0) { throw "Guardrails installer failed with exit code $LASTEXITCODE." }
