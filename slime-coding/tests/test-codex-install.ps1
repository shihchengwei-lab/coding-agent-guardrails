$ErrorActionPreference = "Stop"

$Root = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$Install = Join-Path $Root "install-codex.ps1"
$Pass = 0
$Fail = 0
$TmpDirs = @()

function Ok($Label) {
  Write-Host "  ok   $Label"
  $script:Pass += 1
}

function Bad($Label, $Got) {
  Write-Host "FAIL   $Label"
  Write-Host "       got: $Got"
  $script:Fail += 1
}

function New-TmpDir {
  $dir = Join-Path ([System.IO.Path]::GetTempPath()) ("slime-codex-test-" + [System.Guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  $script:TmpDirs += $dir
  return $dir
}

try {
  $Project = New-TmpDir
  git -C $Project init -q
  git -C $Project config user.email t@t.t
  git -C $Project config user.name t
  $seed = "# Existing`n`nKeep this.`n`n<!-- >>> Slime Coding Codex -->`nOld block from a pre-fusion install.`n<!-- <<< Slime Coding Codex -->"
  Set-Content -LiteralPath (Join-Path $Project "AGENTS.md") -Value $seed -Encoding utf8
  # A pre-existing user hook must survive install and reinstall (on Windows
  # PowerShell 5.1 this also exercises the ConvertFrom-Json fallback path).
  New-Item -ItemType Directory -Force -Path (Join-Path $Project ".codex") | Out-Null
  $userHooks = '{ "hooks": { "Stop": [ { "hooks": [ { "type": "command", "command": "echo user-stop-hook" } ] } ] } }'
  Set-Content -LiteralPath (Join-Path $Project ".codex/hooks.json") -Value $userHooks -Encoding utf8

  & powershell -NoProfile -ExecutionPolicy Bypass -File $Install -Project $Project | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "install-codex.ps1 failed with $LASTEXITCODE" }

  $Hooks = Join-Path $Project ".codex/hooks.json"
  $Skill = Join-Path $Project ".agents/skills/slime-navigate/SKILL.md"
  $Corridor = Join-Path $Project ".slime/corridor.md"
  $Pruned = Join-Path $Project ".slime/PRUNED.md"
  $Agents = Join-Path $Project "AGENTS.md"
  $GitHook = Join-Path $Project ".git/hooks/prepare-commit-msg"

  if (Test-Path -LiteralPath $Hooks) { Ok "1  writes .codex/hooks.json" } else { Bad "1  writes .codex/hooks.json" "missing" }
  $hookJson = Get-Content -LiteralPath $Hooks -Raw | ConvertFrom-Json
  $hookText = Get-Content -LiteralPath $Hooks -Raw
  if ($hookText -notmatch "__SLIME_HOME__" -and $hookText -match "commandWindows" -and $hookText -match "patch-cost") {
    Ok "2  hooks are baked for Codex including Windows command"
  } else {
    Bad "2  hooks are baked for Codex including Windows command" $hookText
  }
  if ($hookJson.hooks.PreToolUse[0].matcher -match "Edit" -and
      $hookJson.hooks.PostToolUse[0].matcher -match "Bash" -and
      $hookJson.hooks.UserPromptSubmit.Count -ge 1 -and
      $hookJson.hooks.Stop.Count -ge 1) {
    Ok "3  hook events include baseline, PreToolUse, Bash PostToolUse and Stop"
  } else {
    Bad "3  hook events include baseline, PreToolUse, Bash PostToolUse and Stop" $hookText
  }
  if (Test-Path -LiteralPath $Skill) { Ok "4  installs repo-local Codex skill" } else { Bad "4  installs repo-local Codex skill" "missing" }
  if ((Test-Path -LiteralPath $Corridor) -and (Test-Path -LiteralPath $Pruned)) { Ok "5  seeds .slime artifacts" } else { Bad "5  seeds .slime artifacts" "missing" }
  $corridorText = Get-Content -LiteralPath $Corridor -Raw
  if ($corridorText -match "(?ms)^## Rigor\s+normal\s*$") {
    Ok "5b seeds a normal-rigor corridor"
  } else {
    Bad "5b seeds a normal-rigor corridor" $corridorText
  }

  $agentsText = Get-Content -LiteralPath $Agents -Raw
  if ($agentsText.Trim() -eq $seed.Trim()) {
    Ok "6  standalone installer leaves AGENTS.md untouched"
  } else {
    Bad "6  standalone installer leaves AGENTS.md untouched" $agentsText
  }
  if ($agentsText -match ">>> Slime Coding Codex") {
    Ok "6b standalone installer does not rewrite legacy user text"
  } else {
    Bad "6b standalone installer does not rewrite legacy user text" $agentsText
  }
  if (-not (Test-Path -LiteralPath $GitHook)) { Ok "7  does not add redundant commit-message evidence" } else { Bad "7  does not add redundant commit-message evidence" "unexpected hook" }

  Add-Content -LiteralPath $Corridor -Value "`n<!-- keep-existing-corridor -->"
  & powershell -NoProfile -ExecutionPolicy Bypass -File $Install -Project $Project | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "second install-codex.ps1 failed with $LASTEXITCODE" }
  $agentsText2 = Get-Content -LiteralPath $Agents -Raw
  if ($agentsText2.Trim() -eq $seed.Trim()) { Ok "8  reinstall still leaves AGENTS.md untouched" } else { Bad "8  reinstall still leaves AGENTS.md untouched" $agentsText2 }
  if ((Get-Content -LiteralPath $Corridor -Raw) -match "keep-existing-corridor") {
    Ok "8b reinstall preserves the existing corridor"
  } else {
    Bad "8b reinstall preserves the existing corridor" "marker missing"
  }

  $hookText2 = Get-Content -LiteralPath $Hooks -Raw
  $hookJson2 = $hookText2 | ConvertFrom-Json
  if ($hookText2 -match "user-stop-hook") {
    Ok "9  pre-existing user hook survives install + reinstall"
  } else {
    Bad "9  pre-existing user hook survives install + reinstall" $hookText2
  }
  $stopGroups = @($hookJson2.hooks.Stop)
  if ($stopGroups.Count -eq 2) {
    Ok "9b reinstall does not duplicate hook groups"
  } else {
    Bad "9b reinstall does not duplicate hook groups" "Stop groups=$($stopGroups.Count)"
  }

  # Quoted absolute python path (the no-py-launcher branch) must yield valid
  # JSON and pass the real preflight: the path goes through JSON escaping
  # before template substitution.
  $Project2 = New-TmpDir
  git -C $Project2 init -q
  $PythonDir = Join-Path $Project2 "Python Tools"
  New-Item -ItemType Directory -Force -Path $PythonDir | Out-Null
  $PythonWrapper = Join-Path $PythonDir "python wrapper.cmd"
  "@echo off`r`npython %*`r`n" | Set-Content -LiteralPath $PythonWrapper -Encoding ascii
  $QuotedPython = '"' + $PythonWrapper + '"'
  & powershell -NoProfile -ExecutionPolicy Bypass -File $Install -Project $Project2 `
    -PythonCommand $QuotedPython | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "install-codex.ps1 with -PythonCommand failed with $LASTEXITCODE" }
  $Hooks2 = Join-Path $Project2 ".codex/hooks.json"
  try {
    $quotedJson = Get-Content -LiteralPath $Hooks2 -Raw | ConvertFrom-Json
    $cmdWin = [string]$quotedJson.hooks.PreToolUse[0].hooks[0].commandWindows
    if ($cmdWin -match 'Python Tools' -and $cmdWin.StartsWith('"')) {
      Ok "10 quoted python path bakes into valid JSON"
    } else {
      Bad "10 quoted python path bakes into valid JSON" $cmdWin
    }
  } catch {
    Bad "10 quoted python path bakes into valid JSON" "hooks.json did not parse: $_"
  }
} finally {
  foreach ($dir in $TmpDirs) {
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
  }
}

Write-Host ""
Write-Host "$Pass passed, $Fail failed"
if ($Fail -ne 0) { exit 1 }
