param(
  [string]$Project = ".",
  # Override python detection (tests use this to exercise the quoted-path
  # branch on runners where the py launcher exists).
  [string]$PythonCommand = ""
)

$ErrorActionPreference = "Stop"
$SlimeHome = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$Project = (Resolve-Path -LiteralPath $Project).Path

function Find-PythonCommand {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    return "py -3"
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return '"' + $python.Source + '"'
  }
  throw "python is required (py -3 or python must be on PATH)."
}

function Convert-ToHashtable {
  param($InputObject)
  if ($null -eq $InputObject) { return $null }
  if ($InputObject -is [System.Collections.IDictionary]) {
    $out = [ordered]@{}
    foreach ($key in @($InputObject.Keys)) { $out[[string]$key] = Convert-ToHashtable $InputObject[$key] }
    return $out
  }
  if ($InputObject -is [System.Management.Automation.PSCustomObject]) {
    $out = [ordered]@{}
    foreach ($prop in $InputObject.PSObject.Properties) { $out[$prop.Name] = Convert-ToHashtable $prop.Value }
    return $out
  }
  if ($InputObject -is [System.Collections.IEnumerable] -and $InputObject -isnot [string]) {
    return ,@($InputObject | ForEach-Object { Convert-ToHashtable $_ })
  }
  return $InputObject
}

function ConvertFrom-JsonCompat {
  # Windows PowerShell 5.1 has no ConvertFrom-Json -AsHashtable; falling into
  # the caller's catch there used to silently discard the user's existing
  # hooks. Parse to objects and convert instead.
  param([string]$Text)
  if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey("AsHashtable")) {
    return $Text | ConvertFrom-Json -AsHashtable
  }
  return Convert-ToHashtable ($Text | ConvertFrom-Json)
}

function Copy-DirectoryFresh {
  param([string]$Source, [string]$Destination)
  if (Test-Path -LiteralPath $Destination) {
    Remove-Item -LiteralPath $Destination -Recurse -Force
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
  Copy-Item -LiteralPath $Source -Destination $Destination -Recurse
}

function Resolve-PythonInvocation {
  param([string]$Command)
  if ($Command -match '^"([^"]+)"(?:\s+(.*))?$') {
    $prefix = if ($Matches[2]) { @($Matches[2] -split '\s+') } else { @() }
    return @{ Exe = $Matches[1]; Prefix = $prefix }
  }
  $parts = @($Command -split '\s+' | Where-Object { $_ })
  if (-not $parts.Count) { throw "Python command is empty." }
  $resolved = Get-Command $parts[0] -ErrorAction SilentlyContinue
  if (-not $resolved) { throw "Python command was not found: $($parts[0])" }
  return @{ Exe = $resolved.Source; Prefix = @($parts | Select-Object -Skip 1) }
}

function Merge-Hooks {
  param(
    [string]$SettingsPath,
    [string]$TemplatePath,
    [string]$PythonWin
  )
  $templateText = Get-Content -LiteralPath $TemplatePath -Raw
  $templateText = $templateText.Replace("__SLIME_HOME_WIN__", $SlimeHome.Replace("\", "\\"))
  $templateText = $templateText.Replace("__SLIME_HOME__", $SlimeHome.Replace("\", "/"))
  # $PythonWin may be a quoted absolute path ("C:\...\python.exe"); escape it
  # for the JSON string context or the substituted template will not parse.
  $pythonJson = $PythonWin.Replace("\", "\\").Replace('"', '\"')
  $templateText = $templateText.Replace("__PYTHON_WIN__", $pythonJson)
  $template = $templateText | ConvertFrom-Json

  $settings = [ordered]@{ hooks = [ordered]@{} }
  if (Test-Path -LiteralPath $SettingsPath) {
    try {
      $settings = ConvertFrom-JsonCompat (Get-Content -LiteralPath $SettingsPath -Raw)
    } catch {
      throw "Existing $SettingsPath is not valid JSON; no project files were changed."
    }
  }
  if (-not $settings.Contains("hooks") -or $null -eq $settings["hooks"]) {
    $settings["hooks"] = [ordered]@{}
  }

  $ours = [regex]"[\\/]+bin[\\/]+(prune-inject|patch-cost)"
  foreach ($event in $template.hooks.PSObject.Properties.Name) {
    $existing = @()
    if ($settings["hooks"].Contains($event) -and $null -ne $settings["hooks"][$event]) {
      foreach ($group in @($settings["hooks"][$event])) {
        $isOurs = $false
        foreach ($hook in @($group.hooks)) {
          $cmd = [string]($hook.command)
          $cmdWin = [string]($hook.commandWindows)
          if ($ours.IsMatch($cmd) -or $ours.IsMatch($cmdWin)) {
            $isOurs = $true
          }
        }
        if (-not $isOurs) {
          $existing += $group
        }
      }
    }
    $settings["hooks"][$event] = @($existing) + @($template.hooks.$event)
  }

  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SettingsPath) | Out-Null
  $settings | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $SettingsPath -Encoding utf8
}

$pythonWin = if ($PythonCommand) { $PythonCommand } else { Find-PythonCommand }
# A bare interpreter path with spaces (user-supplied, or with its quotes eaten
# at a process boundary) would split into two tokens in every baked command
# line; wrap it. Launcher forms like `py -3` stay untouched.
if ($pythonWin -notmatch '^"' -and $pythonWin -match '\s' -and
    ((Test-Path -LiteralPath $pythonWin -PathType Leaf) -or $pythonWin -match '(?i)\.exe$')) {
  $pythonWin = '"' + $pythonWin + '"'
}

# Preflight all executables and templates before changing the project.
$gitCommand = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCommand) { throw "git is required." }
& $gitCommand.Source -C $Project rev-parse --git-dir *> $null
if ($LASTEXITCODE -ne 0) { throw "Target must be a git repository: $Project" }
$pythonInvocation = Resolve-PythonInvocation $pythonWin
& $pythonInvocation.Exe @($pythonInvocation.Prefix) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 or newer is required." }
foreach ($relative in @(
  "hooks/codex.hooks.template.json",
  "templates/.slime/corridor.md",
  "templates/.slime/PRUNED.md",
  "skills/slime-navigate/SKILL.md"
)) {
  $source = Join-Path $SlimeHome $relative
  if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Required installer source is missing: $source"
  }
}
try {
  Get-Content -LiteralPath (Join-Path $SlimeHome "hooks/codex.hooks.template.json") -Raw |
    ConvertFrom-Json | Out-Null
} catch {
  throw "Invalid Codex hook template JSON: $($_.Exception.Message)"
}

Write-Host "Slime Coding home : $SlimeHome"
Write-Host "Target project    : $Project"

$managedPaths = @(".codex", ".agents/skills/slime-navigate", ".slime")
$journal = Join-Path ([System.IO.Path]::GetTempPath()) ("slime-journal-" + [guid]::NewGuid())
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
Merge-Hooks `
  -SettingsPath (Join-Path $Project ".codex/hooks.json") `
  -TemplatePath (Join-Path $SlimeHome "hooks/codex.hooks.template.json") `
  -PythonWin $pythonWin
Write-Host "  wired hooks -> $(Join-Path $Project '.codex/hooks.json')"

Copy-DirectoryFresh `
  -Source (Join-Path $SlimeHome "skills/slime-navigate") `
  -Destination (Join-Path $Project ".agents/skills/slime-navigate")
Write-Host "  installed skill -> $(Join-Path $Project '.agents/skills/slime-navigate')"

$slimeDir = Join-Path $Project ".slime"
if (-not (Test-Path -LiteralPath (Join-Path $slimeDir "corridor.md"))) {
  New-Item -ItemType Directory -Force -Path $slimeDir | Out-Null
  Copy-Item -LiteralPath (Join-Path $SlimeHome "templates/.slime/corridor.md") -Destination (Join-Path $slimeDir "corridor.md")
  Copy-Item -LiteralPath (Join-Path $SlimeHome "templates/.slime/PRUNED.md") -Destination (Join-Path $slimeDir "PRUNED.md")
  Write-Host "  seeded $slimeDir (replace the template before editing code)"
} else {
  Write-Host "  .slime/ already present - left untouched"
}

} catch {
  foreach ($relative in $managedPaths) {
    $target = Join-Path $Project $relative
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    if ($existed.ContainsKey($relative)) {
      $backup = Join-Path $backupRoot $relative
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
      Copy-Item -LiteralPath $backup -Destination $target -Recurse -Force
    }
  }
  throw "Slime installation failed; project files were restored. $($_.Exception.Message)"
} finally {
  Remove-Item -LiteralPath $journal -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Done. Restart Codex or start a new Codex run in the target repo so hooks are reloaded."
Write-Host "Review and trust project hooks with /hooks if Codex marks them as untrusted."
