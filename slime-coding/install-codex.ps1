param(
  [string]$Project = "."
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
    [string]$Name
  )
  $start = "<!-- >>> $Name -->"
  $end = "<!-- <<< $Name -->"
  $managed = "$start`n$Block`n$end"
  $content = ""
  if (Test-Path -LiteralPath $Path) {
    $content = Get-Content -LiteralPath $Path -Raw
  }
  $pattern = "(?s)" + [regex]::Escape($start) + ".*?" + [regex]::Escape($end) + "\s*"
  $content = [regex]::Replace($content, $pattern, "").TrimEnd()
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
  $templateText = $templateText.Replace("__PYTHON_WIN__", $PythonWin)
  $template = $templateText | ConvertFrom-Json

  $settings = [ordered]@{ hooks = [ordered]@{} }
  if (Test-Path -LiteralPath $SettingsPath) {
    Copy-Item -LiteralPath $SettingsPath -Destination ($SettingsPath + ".bak-" + (Get-Date -Format "yyyyMMddHHmmss")) -Force
    try {
      $settings = Get-Content -LiteralPath $SettingsPath -Raw | ConvertFrom-Json -AsHashtable
    } catch {
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

$pythonWin = Find-PythonCommand

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

$agentsBlock = Get-Content -LiteralPath (Join-Path $SlimeHome "templates/AGENTS.slime.md") -Raw
Install-ManagedBlock -Path (Join-Path $Project "AGENTS.md") -Block $agentsBlock.Trim() -Name "Slime Coding Codex"
Write-Host "  installed AGENTS.md block -> $(Join-Path $Project 'AGENTS.md')"

Install-GitHook -PythonWin $pythonWin

Write-Host ""
Write-Host "Done. Restart Codex or start a new Codex run in the target repo so AGENTS.md and hooks are reloaded."
Write-Host "Review and trust project hooks with /hooks if Codex marks them as untrusted."
