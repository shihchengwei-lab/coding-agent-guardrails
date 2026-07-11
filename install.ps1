param(
  [string]$Project = ".",
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$ToolkitHome = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$Project = (Resolve-Path -LiteralPath $Project).Path

function Resolve-Python {
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

function Invoke-SelectedPython {
  param([string[]]$Arguments)
  & $PythonInfo.Exe @($PythonInfo.Prefix) @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Python command failed with exit code $LASTEXITCODE."
  }
}

function Install-ManagedBlock {
  param([string]$Path, [string]$Body)
  $start = "<!-- coding-agent-guardrails:discipline:start -->"
  $end = "<!-- coding-agent-guardrails:discipline:end -->"
  $block = "$start`n$($Body.Trim())`n$end"
  $content = if (Test-Path -LiteralPath $Path) {
    Get-Content -LiteralPath $Path -Raw -Encoding utf8
  } else { "" }
  $pattern = "(?s)" + [regex]::Escape($start) + ".*?" + [regex]::Escape($end)
  if ([regex]::IsMatch($content, $pattern)) {
    $content = [regex]::Replace($content, $pattern, $block)
  } else {
    $content = $content.TrimEnd()
    if ($content) { $content += "`n`n" }
    $content += $block
  }
  [System.IO.File]::WriteAllText($Path, $content.TrimEnd() + "`n", [System.Text.UTF8Encoding]::new($false))
}

function Convert-ToHashtable {
  param($InputObject)
  if ($null -eq $InputObject) { return $null }
  if ($InputObject -is [System.Collections.IDictionary]) {
    $result = [ordered]@{}
    foreach ($key in @($InputObject.Keys)) {
      $result[[string]$key] = Convert-ToHashtable $InputObject[$key]
    }
    return $result
  }
  if ($InputObject -is [System.Management.Automation.PSCustomObject]) {
    $result = [ordered]@{}
    foreach ($property in $InputObject.PSObject.Properties) {
      $result[$property.Name] = Convert-ToHashtable $property.Value
    }
    return $result
  }
  if ($InputObject -is [System.Collections.IEnumerable] -and $InputObject -isnot [string]) {
    return ,@($InputObject | ForEach-Object { Convert-ToHashtable $_ })
  }
  return $InputObject
}

function Read-JsonHashtable {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return [ordered]@{} }
  $text = Get-Content -LiteralPath $Path -Raw -Encoding utf8
  if (-not $text.Trim()) { return [ordered]@{} }
  return Convert-ToHashtable ($text | ConvertFrom-Json)
}

function Test-AgentcamHookGroup {
  param($Group)
  foreach ($hook in @($Group["hooks"])) {
    $commands = @([string]$hook["command"], [string]$hook["commandWindows"])
    if (($commands -join " ") -match "hook-turn-(start|end)") { return $true }
  }
  return $false
}

$PythonInfo = Resolve-Python
Invoke-SelectedPython -Arguments @(
  "-c",
  "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
)
$PythonCommand = '"' + $PythonInfo.Exe + '"'
if ($PythonInfo.Prefix.Count) { $PythonCommand += " " + ($PythonInfo.Prefix -join " ") }

Write-Host "Toolkit home : $ToolkitHome"
Write-Host "Target       : $Project"
Write-Host "Python       : $($PythonInfo.Exe)"

$discipline = Get-Content -LiteralPath (Join-Path $ToolkitHome "templates/DISCIPLINE.md") -Raw -Encoding utf8
foreach ($name in @("CLAUDE.md", "AGENTS.md")) {
  Install-ManagedBlock -Path (Join-Path $Project $name) -Body $discipline
}

& (Join-Path $ToolkitHome "slime-coding/install-codex.ps1") `
  -Project $Project `
  -PythonCommand $PythonCommand | Out-Host

$workflow = Join-Path $Project ".github/workflows/corridor.yml"
if (-not (Test-Path -LiteralPath $workflow)) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $workflow) | Out-Null
  Copy-Item -LiteralPath (Join-Path $ToolkitHome "corridor-ci/examples/workflow.yml") -Destination $workflow
  Write-Host "  corridor workflow -> $workflow"
} else {
  Write-Host "  corridor workflow already present - left untouched"
}

Invoke-SelectedPython -Arguments @(
  "-m", "pip", "install", "--quiet", "--upgrade", (Join-Path $ToolkitHome "agentcam")
)

$hooksPath = Join-Path $Project ".codex/hooks.json"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $hooksPath) | Out-Null
$settings = Read-JsonHashtable -Path $hooksPath
if (-not $settings.Contains("hooks") -or $settings["hooks"] -isnot [System.Collections.IDictionary]) {
  $settings["hooks"] = [ordered]@{}
}
$hooks = $settings["hooks"]
$windowsBase = "$PythonCommand -m agentcam.cli"
foreach ($spec in @(
  @{ Event = "UserPromptSubmit"; Command = "hook-turn-start"; Message = "Starting agentcam turn recording" },
  @{ Event = "Stop"; Command = "hook-turn-end"; Message = "Finishing agentcam turn recording" }
)) {
  $kept = @($hooks[$spec.Event] | Where-Object { -not (Test-AgentcamHookGroup $_) })
  $kept += [ordered]@{
    hooks = @(
      [ordered]@{
        type = "command"
        command = "python3 -m agentcam.cli $($spec.Command)"
        commandWindows = "$windowsBase $($spec.Command)"
        statusMessage = $spec.Message
      }
    )
  }
  $hooks[$spec.Event] = $kept
}

$json = $settings | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($hooksPath, $json + "`n", [System.Text.UTF8Encoding]::new($false))
Write-Host "  agentcam Codex turn hooks -> $hooksPath"

Write-Host ""
Write-Host "Done. Start a new Codex run and review project hooks with /hooks."
Write-Host "Hook recordings are partial and report Risk: unknown when no flags are visible."
