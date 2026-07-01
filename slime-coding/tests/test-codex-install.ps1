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
  Set-Content -LiteralPath (Join-Path $Project "AGENTS.md") -Value "# Existing`n`nKeep this." -Encoding utf8

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
  if ($hookJson.hooks.PreToolUse[0].matcher -match "Edit" -and $hookJson.hooks.Stop.Count -ge 1) {
    Ok "3  hook events include PreToolUse and Stop"
  } else {
    Bad "3  hook events include PreToolUse and Stop" $hookText
  }
  if (Test-Path -LiteralPath $Skill) { Ok "4  installs repo-local Codex skill" } else { Bad "4  installs repo-local Codex skill" "missing" }
  if ((Test-Path -LiteralPath $Corridor) -and (Test-Path -LiteralPath $Pruned)) { Ok "5  seeds .slime artifacts" } else { Bad "5  seeds .slime artifacts" "missing" }

  $agentsText = Get-Content -LiteralPath $Agents -Raw
  if ($agentsText -match ">>> Slime Coding Codex" -and $agentsText -match "minimal semantic displacement" -and $agentsText -match "Keep this\.") {
    Ok "6  appends AGENTS.md managed block without dropping existing text"
  } else {
    Bad "6  appends AGENTS.md managed block without dropping existing text" $agentsText
  }
  if (Test-Path -LiteralPath $GitHook) { Ok "7  wires prepare-commit-msg hook" } else { Bad "7  wires prepare-commit-msg hook" "missing" }

  & powershell -NoProfile -ExecutionPolicy Bypass -File $Install -Project $Project | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "second install-codex.ps1 failed with $LASTEXITCODE" }
  $agentsText2 = Get-Content -LiteralPath $Agents -Raw
  $count = ([regex]::Matches($agentsText2, ">>> Slime Coding Codex")).Count
  if ($count -eq 1) { Ok "8  install is idempotent for AGENTS.md block" } else { Bad "8  install is idempotent for AGENTS.md block" "count=$count" }
} finally {
  foreach ($dir in $TmpDirs) {
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
  }
}

Write-Host ""
Write-Host "$Pass passed, $Fail failed"
if ($Fail -ne 0) { exit 1 }
