$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Temp = Join-Path ([System.IO.Path]::GetTempPath()) ("guardrails install " + [guid]::NewGuid())
$Project = Join-Path $Temp "project"
$Venv = Join-Path $Temp "venv"

try {
  New-Item -ItemType Directory -Force -Path $Project | Out-Null
  git -C $Project init -q -b main
  git -C $Project config user.email test@example.com
  git -C $Project config user.name Test

  New-Item -ItemType Directory -Force -Path (Join-Path $Project ".codex") | Out-Null
  @'
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {"type": "command", "command": "user-existing-hook"}
        ]
      }
    ]
  }
}
'@ | Set-Content -Encoding utf8 (Join-Path $Project ".codex/hooks.json")

  python -m venv $Venv
  $Python = Join-Path $Venv "Scripts/python.exe"
  $Installer = Join-Path $Root "install.ps1"

  & $Installer -Project $Project -Python $Python | Out-Null
  & $Installer -Project $Project -Python $Python | Out-Null

  foreach ($name in @("CLAUDE.md", "AGENTS.md")) {
    $text = Get-Content -Raw -Encoding utf8 (Join-Path $Project $name)
    if ([regex]::Matches($text, "coding-agent-guardrails:discipline:start").Count -ne 1) {
      throw "$name discipline block is not idempotent"
    }
  }

  $hooks = Get-Content -Raw -Encoding utf8 (Join-Path $Project ".codex/hooks.json") | ConvertFrom-Json
  $allCommands = @(
    foreach ($event in $hooks.hooks.PSObject.Properties) {
      foreach ($group in $event.Value) {
        foreach ($hook in $group.hooks) { $hook.commandWindows; $hook.command }
      }
    }
  ) -join "`n"
  if ($allCommands -notmatch "hook-turn-start") { throw "Codex turn-start recorder missing" }
  if ($allCommands -notmatch "hook-turn-end") { throw "Codex turn-end recorder missing" }
  if ($allCommands -notmatch "user-existing-hook") { throw "existing user hook was overwritten" }
  if ([regex]::Matches($allCommands, "hook-turn-start").Count -ne 2) {
    throw "turn-start hook duplicated or missing command/commandWindows"
  }
  if ([regex]::Matches($allCommands, "hook-turn-end").Count -ne 2) {
    throw "turn-end hook duplicated or missing command/commandWindows"
  }

  $corridor = Get-Content -Raw -Encoding utf8 (Join-Path $Project ".slime/corridor.md")
  if ($corridor -notmatch "(?m)^## Rigor\r?\nnormal$") { throw "normal corridor not seeded" }
  if (-not (Test-Path (Join-Path $Project ".agents/skills/slime-navigate/SKILL.md"))) {
    throw "Codex skill not installed"
  }
  if (-not (Test-Path (Join-Path $Project ".github/workflows/corridor.yml"))) {
    throw "Corridor workflow not installed"
  }
  $workflow = Get-Content -Raw -Encoding utf8 (Join-Path $Project ".github/workflows/corridor.yml")
  if ($workflow -notmatch "coding-agent-guardrails:managed corridor-ci-v12" -or
      $workflow -notmatch "corridor-ci@corridor-ci-v12") {
    throw "installed Corridor workflow is not the managed v12 template"
  }

  # The exact official v11 template upgrades; user-authored workflow content
  # is preserved and gets an explicit stale-version warning.
  Copy-Item -LiteralPath (Join-Path $Root "tests/fixtures/corridor-v11-workflow.yml") `
    -Destination (Join-Path $Project ".github/workflows/corridor.yml") -Force
  & $Installer -Project $Project -Python $Python | Out-Null
  $workflow = Get-Content -Raw -Encoding utf8 (Join-Path $Project ".github/workflows/corridor.yml")
  if ($workflow -notmatch "corridor-ci@corridor-ci-v12") {
    throw "official v11 workflow was not upgraded"
  }
  "# custom corridor workflow" | Set-Content -Encoding utf8 (Join-Path $Project ".github/workflows/corridor.yml")
  $customOutput = (& $Installer -Project $Project -Python $Python 3>&1 | Out-String)
  $workflow = (Get-Content -Raw -Encoding utf8 (Join-Path $Project ".github/workflows/corridor.yml")).Trim()
  if ($workflow -ne "# custom corridor workflow") { throw "custom workflow was overwritten" }
  if ($customOutput -notmatch "custom workflow is not overwritten") {
    throw "custom workflow did not produce a preservation warning"
  }

  & $Python -m agentcam.cli version | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "agentcam not installed into selected Python" }

  # A pip preflight failure must not leave project files or hook directories.
  $FailProject = Join-Path $Temp "preflight-failure"
  New-Item -ItemType Directory -Force -Path $FailProject | Out-Null
  git -C $FailProject init -q -b main
  $FakePython = Join-Path $Temp "fake-python.cmd"
  @'
@echo off
if "%1"=="-m" if "%2"=="pip" exit /b 77
python %*
'@ | Set-Content -Encoding ascii $FakePython
  $failed = $false
  try { & $Installer -Project $FailProject -Python $FakePython | Out-Null }
  catch { $failed = $true }
  if (-not $failed) { throw "fake pip failure unexpectedly succeeded" }
  foreach ($relative in @("CLAUDE.md", "AGENTS.md", ".codex", ".agents", ".slime", ".github")) {
    if (Test-Path (Join-Path $FailProject $relative)) {
      throw "preflight failure left $relative behind"
    }
  }

  # A later mutation failure must restore every managed path already touched.
  $RollbackProject = Join-Path $Temp "rollback-project"
  New-Item -ItemType Directory -Force -Path $RollbackProject | Out-Null
  git -C $RollbackProject init -q -b main
  "original instructions" | Set-Content -Encoding utf8 (Join-Path $RollbackProject "CLAUDE.md")
  "user-owned obstacle" | Set-Content -Encoding utf8 (Join-Path $RollbackProject ".codex")
  $failed = $false
  try { & $Installer -Project $RollbackProject -Python $Python | Out-Null }
  catch { $failed = $true }
  if (-not $failed) { throw "post-mutation obstacle unexpectedly succeeded" }
  if ((Get-Content -Raw -Encoding utf8 (Join-Path $RollbackProject "CLAUDE.md")).Trim() -ne "original instructions") {
    throw "rollback did not restore CLAUDE.md"
  }
  if ((Get-Content -Raw -Encoding utf8 (Join-Path $RollbackProject ".codex")).Trim() -ne "user-owned obstacle") {
    throw "rollback did not restore the pre-existing .codex path"
  }
  foreach ($relative in @("AGENTS.md", ".agents", ".slime", ".github")) {
    if (Test-Path (Join-Path $RollbackProject $relative)) {
      throw "rollback left $relative behind"
    }
  }

  Write-Host "install.ps1 toolkit test OK"
}
finally {
  Remove-Item -Recurse -Force $Temp -ErrorAction SilentlyContinue
}
