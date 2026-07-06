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

function Install-ManagedBlock {
  param(
    [string]$Path,
    [string]$Block,
    [string]$Start,
    [string]$End
  )
  $managed = "$Start`n$Block`n$End"
  $content = ""
  if (Test-Path -LiteralPath $Path) {
    $content = Get-Content -LiteralPath $Path -Raw
  }
  $pattern = "(?s)" + [regex]::Escape($Start) + ".*?" + [regex]::Escape($End) + "\s*"
  $content = [regex]::Replace($content, $pattern, "")
  # Pre-fusion installs wrote a "Slime Coding Codex" block; clear it so an
  # upgrade does not leave two overlapping discipline texts behind.
  $legacy = "(?s)" + [regex]::Escape("<!-- >>> Slime Coding Codex -->") + ".*?" + [regex]::Escape("<!-- <<< Slime Coding Codex -->") + "\s*"
  $content = [regex]::Replace($content, $legacy, "").TrimEnd()
  if ($content.Length -gt 0) {
    $content = "$content`n`n$managed`n"
  } else {
    $content = "$managed`n"
  }
  Set-Content -LiteralPath $Path -Value $content -Encoding utf8
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
    Copy-Item -LiteralPath $SettingsPath -Destination ($SettingsPath + ".bak-" + (Get-Date -Format "yyyyMMddHHmmss")) -Force
    try {
      $settings = ConvertFrom-JsonCompat (Get-Content -LiteralPath $SettingsPath -Raw)
    } catch {
      Write-Host "  warning: existing $SettingsPath is not valid JSON; starting fresh (backup kept next to it)"
      $settings = [ordered]@{ hooks = [ordered]@{} }
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

function Install-GitHook {
  param([string]$PythonWin)
  $gitPath = (& git -C $Project rev-parse --git-path hooks/prepare-commit-msg 2>$null)
  if (-not $gitPath) {
    Write-Host "  git hook skipped (target is not a git repo)"
    return
  }
  if ([System.IO.Path]::IsPathRooted($gitPath)) {
    $hookPath = $gitPath
  } else {
    $hookPath = Join-Path $Project $gitPath
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $hookPath) | Out-Null
  $start = "# >>> Slime Coding commit evidence"
  $end = "# <<< Slime Coding commit evidence"
  $block = @"
$start
$PythonWin "$SlimeHome\bin\commit-evidence" "`$@"
$end
"@
  $content = ""
  if (Test-Path -LiteralPath $hookPath) {
    $content = Get-Content -LiteralPath $hookPath -Raw
  }
  $pattern = "(?s)" + [regex]::Escape($start) + ".*?" + [regex]::Escape($end) + "\s*"
  $content = [regex]::Replace($content, $pattern, "").TrimEnd()
  if (-not $content.StartsWith("#!")) {
    $content = "#!/usr/bin/env sh`n" + $content
  }
  Set-Content -LiteralPath $hookPath -Value ($content.TrimEnd() + "`n`n" + $block + "`n") -Encoding utf8
  Write-Host "  wired git hook -> $hookPath"
}

$pythonWin = if ($PythonCommand) { $PythonCommand } else { Find-PythonCommand }
# A bare interpreter path with spaces (user-supplied, or with its quotes eaten
# at a process boundary) would split into two tokens in every baked command
# line; wrap it. Launcher forms like `py -3` stay untouched.
if ($pythonWin -notmatch '^"' -and $pythonWin -match '\s' -and $pythonWin -match '(?i)\.exe$') {
  $pythonWin = '"' + $pythonWin + '"'
}

Write-Host "Slime Coding home : $SlimeHome"
Write-Host "Target project    : $Project"

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

# The discipline text is the toolkit-wide single source: the root
# templates/DISCIPLINE.md, written with the same markers the root
# installer uses, so running either installer leaves exactly one block.
$disciplineFile = Join-Path (Split-Path -Parent $SlimeHome) "templates/DISCIPLINE.md"
$agentsBlock = Get-Content -LiteralPath $disciplineFile -Raw
Install-ManagedBlock -Path (Join-Path $Project "AGENTS.md") -Block $agentsBlock.Trim() `
  -Start "<!-- coding-agent-guardrails:discipline:start -->" `
  -End "<!-- coding-agent-guardrails:discipline:end -->"
Write-Host "  installed discipline block (root templates/DISCIPLINE.md) -> $(Join-Path $Project 'AGENTS.md')"

Install-GitHook -PythonWin $pythonWin

Write-Host ""
Write-Host "Done. Restart Codex or start a new Codex run in the target repo so AGENTS.md and hooks are reloaded."
Write-Host "Review and trust project hooks with /hooks if Codex marks them as untrusted."
