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

function Install-ManagedWorkflow {
  param([string]$Template, [string]$Destination)
  $parent = Split-Path -Parent $Destination
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  $temporary = Join-Path $parent ((Split-Path -Leaf $Destination) + ".tmp." + [guid]::NewGuid())
  Copy-Item -LiteralPath $Template -Destination $temporary
  if (Test-Path -LiteralPath $Destination) {
    $backup = $temporary + ".replace-backup"
    [System.IO.File]::Replace($temporary, $Destination, $backup, $true)
    Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
  } else {
    Move-Item -LiteralPath $temporary -Destination $Destination
  }
}

function Get-NormalizedSha256 {
  param([string]$Path)
  $bytes = [System.IO.File]::ReadAllBytes($Path)
  $text = [System.Text.Encoding]::UTF8.GetString($bytes).Replace("`r`n", "`n")
  $hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash(
    [System.Text.Encoding]::UTF8.GetBytes($text)
  )
  return ([System.BitConverter]::ToString($hash)).Replace("-", "").ToLowerInvariant()
}

$PythonInfo = Resolve-Python
Invoke-SelectedPython -Arguments @(
  "-c",
  "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
)
$gitCommand = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCommand) { throw "git is required." }
& $gitCommand.Source -C $Project rev-parse --git-dir *> $null
if ($LASTEXITCODE -ne 0) { throw "Target must be a git repository: $Project" }

$requiredSources = @(
  "templates/DISCIPLINE.md",
  "corridor-ci/examples/workflow.yml",
  "slime-coding/install-codex.ps1",
  "slime-coding/hooks/codex.hooks.template.json",
  "slime-coding/templates/.slime/corridor.md",
  "slime-coding/templates/.slime/PRUNED.md",
  "agentcam/pyproject.toml"
)
foreach ($relative in $requiredSources) {
  $source = Join-Path $ToolkitHome $relative
  if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Required installer source is missing: $source"
  }
}
try {
  Get-Content -LiteralPath (Join-Path $ToolkitHome "slime-coding/hooks/codex.hooks.template.json") -Raw -Encoding utf8 |
    ConvertFrom-Json | Out-Null
} catch {
  throw "Invalid Codex hook template JSON: $($_.Exception.Message)"
}

$PythonCommand = '"' + $PythonInfo.Exe + '"'
if ($PythonInfo.Prefix.Count) { $PythonCommand += " " + ($PythonInfo.Prefix -join " ") }

Write-Host "Toolkit home : $ToolkitHome"
Write-Host "Target       : $Project"
Write-Host "Python       : $($PythonInfo.Exe)"

# Install the Python package before touching the target project. A package may
# remain installed after a later rollback because it cannot damage the target.
Invoke-SelectedPython -Arguments @(
  "-m", "pip", "install", "--quiet", "--upgrade", (Join-Path $ToolkitHome "agentcam")
)

$managedPaths = @(
  "CLAUDE.md", "AGENTS.md", ".codex", ".agents/skills/slime-navigate",
  ".slime", ".github/workflows/corridor.yml"
)
$journal = Join-Path ([System.IO.Path]::GetTempPath()) ("guardrails-journal-" + [guid]::NewGuid())
$backupRoot = Join-Path $journal "backup"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$existed = @{}
foreach ($relative in $managedPaths) {
  $source = Join-Path $Project $relative
  if (Test-Path -LiteralPath $source) {
    $existed[$relative] = $true
    $destination = Join-Path $backupRoot $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
  }
}

try {
  $discipline = Get-Content -LiteralPath (Join-Path $ToolkitHome "templates/DISCIPLINE.md") -Raw -Encoding utf8
  foreach ($name in @("CLAUDE.md", "AGENTS.md")) {
    Install-ManagedBlock -Path (Join-Path $Project $name) -Body $discipline
  }

  & (Join-Path $ToolkitHome "slime-coding/install-codex.ps1") `
    -Project $Project `
    -PythonCommand $PythonCommand | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Slime installer failed with exit code $LASTEXITCODE." }

  $workflow = Join-Path $Project ".github/workflows/corridor.yml"
  $workflowTemplate = Join-Path $ToolkitHome "corridor-ci/examples/workflow.yml"
  if (-not (Test-Path -LiteralPath $workflow)) {
    Install-ManagedWorkflow -Template $workflowTemplate -Destination $workflow
    Write-Host "  corridor workflow -> $workflow"
  } else {
    $workflowText = Get-Content -LiteralPath $workflow -Raw -Encoding utf8
    $managed = $workflowText -match "(?m)^# coding-agent-guardrails:managed corridor-ci-v"
    $officialV11 = (Get-NormalizedSha256 $workflow) -eq "73506c8746a13741be6a70bd1800a3267337d8f8fbeabd9cbf68370b631739d6"
    if ($managed -or $officialV11) {
      Install-ManagedWorkflow -Template $workflowTemplate -Destination $workflow
      if ($officialV11) {
        Write-Host "  official corridor-ci-v11 workflow upgraded -> $workflow"
      } else {
        Write-Host "  managed corridor workflow updated -> $workflow"
      }
    } else {
      Write-Warning "custom workflow is not overwritten; verify it no longer pins an older Corridor version: $workflow"
    }
  }

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
} catch {
  foreach ($relative in $managedPaths) {
    $target = Join-Path $Project $relative
    if (Test-Path -LiteralPath $target) {
      Remove-Item -LiteralPath $target -Recurse -Force
    }
    if ($existed.ContainsKey($relative)) {
      $backup = Join-Path $backupRoot $relative
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
      Copy-Item -LiteralPath $backup -Destination $target -Recurse -Force
    }
  }
  throw "Installation failed; project files were restored. $($_.Exception.Message)"
} finally {
  Remove-Item -LiteralPath $journal -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Done. Start a new Codex run and review project hooks with /hooks."
Write-Host "Hook recordings are partial and report Risk: unknown when no flags are visible."
