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

  $GitDir = (git -C $Project rev-parse --absolute-git-dir).Trim()
  $Guardrails = Join-Path $GitDir "guardrails"
  $ManifestPath = Join-Path $Guardrails "install.json"
  if (-not (Test-Path -LiteralPath $ManifestPath)) { throw "install manifest missing" }
  $Manifest = Get-Content -Raw -Encoding utf8 $ManifestPath | ConvertFrom-Json
  if (-not (Test-Path -LiteralPath $Manifest.runtime)) { throw "versioned runtime missing" }
  if (-not (Test-Path -LiteralPath $Manifest.python)) { throw "versioned Python missing" }
  if (-not (Test-Path -LiteralPath (Join-Path $Project "guardrails.cmd"))) {
    throw "repo-local guardrails launcher missing"
  }
  & (Join-Path $Project "guardrails.cmd") doctor | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "guardrails doctor failed after install" }

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
  if ($allCommands -notmatch "patch-cost") { throw "Guardrails coordinator missing" }
  $hooksText = Get-Content -Raw -Encoding utf8 (Join-Path $Project ".codex/hooks.json")
  if ($hooksText -notmatch "guardrails-coordinator") { throw "coordinator ownership marker missing" }
  if ($allCommands -notmatch "user-existing-hook") { throw "existing user hook was overwritten" }
  if ($allCommands -notmatch [regex]::Escape($Guardrails)) {
    throw "hooks do not target the per-repo guardrails runtime"
  }
  if ($allCommands -match [regex]::Escape($Root)) {
    throw "hooks still depend on the toolkit checkout"
  }
  if (Test-Path (Join-Path $Project ".slime")) { throw "new install created obsolete .slime state" }
  if (Test-Path (Join-Path $Project ".agents/skills/slime-navigate")) {
    throw "obsolete Slime skill was installed"
  }
  if (-not (Test-Path (Join-Path $Project ".github/workflows/corridor.yml"))) {
    throw "Corridor workflow not installed"
  }
  $workflow = Get-Content -Raw -Encoding utf8 (Join-Path $Project ".github/workflows/corridor.yml")
  if ($workflow -notmatch "coding-agent-guardrails:managed corridor-ci-v14\.0\.0" -or
      $workflow -notmatch "corridor-ci@corridor-ci-v14\.0\.0") {
    throw "installed Corridor workflow is not the managed v12 template"
  }

  # Upgrade requires both the managed marker and an official hash. An old
  # unmarked template and user-authored workflow are both preserved.
  Copy-Item -LiteralPath (Join-Path $Root "tests/fixtures/corridor-v11-workflow.yml") `
    -Destination (Join-Path $Project ".github/workflows/corridor.yml") -Force
  $legacyOutput = (& $Installer -Project $Project -Python $Python 3>&1 | Out-String)
  $workflow = Get-Content -Raw -Encoding utf8 (Join-Path $Project ".github/workflows/corridor.yml")
  if ($workflow -notmatch "corridor-ci@corridor-ci-v11") {
    throw "unmarked legacy workflow was overwritten"
  }
  if ($legacyOutput -notmatch "custom workflow preserved") {
    throw "preserved legacy workflow did not produce a warning"
  }
  "# custom corridor workflow" | Set-Content -Encoding utf8 (Join-Path $Project ".github/workflows/corridor.yml")
  $customOutput = (& $Installer -Project $Project -Python $Python 3>&1 | Out-String)
  $workflow = (Get-Content -Raw -Encoding utf8 (Join-Path $Project ".github/workflows/corridor.yml")).Trim()
  if ($workflow -ne "# custom corridor workflow") { throw "custom workflow was overwritten" }
  if ($customOutput -notmatch "custom workflow preserved") {
    throw "custom workflow did not produce a preservation warning"
  }

  & $Manifest.python -m agentcam.cli version | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "agentcam not installed into selected Python" }
  if ((& $Manifest.python -m agentcam.cli version).Trim() -ne "agentcam 0.6.0") {
    throw "unexpected agentcam version"
  }

  if (Get-ChildItem -LiteralPath $Project -Recurse -Force -Filter "*.bak-*" -ErrorAction SilentlyContinue) {
    throw "successful install left permanent backup files"
  }

  # Dry-run and target validation do not mutate repositories.
  $DryProject = Join-Path $Temp "dry-run"
  New-Item -ItemType Directory -Force -Path $DryProject | Out-Null
  git -C $DryProject init -q -b main
  & $Installer -Project $DryProject -Python $Python -DryRun | Out-Null
  if (Test-Path (Join-Path $DryProject "AGENTS.md")) { throw "dry-run mutated project" }
  $Subdir = Join-Path $DryProject "subdir"
  New-Item -ItemType Directory -Force -Path $Subdir | Out-Null
  $failed = $false
  try { & $Installer -Project $Subdir -Python $Python 2>$null | Out-Null } catch { $failed = $true }
  if (-not $failed) { throw "subdirectory target unexpectedly succeeded" }

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
  try { & $Installer -Project $FailProject -Python $FakePython 2>$null | Out-Null }
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
  try { & $Installer -Project $RollbackProject -Python $Python 2>$null | Out-Null }
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

  # Dry-run uninstall changes nothing. Actual uninstall removes only proven
  # managed content, preserving trusted config, .slime history, and user hooks.
  New-Item -ItemType Directory -Force -Path (Join-Path $Project ".slime") | Out-Null
  "user archived history" | Set-Content -Encoding utf8 (Join-Path $Project ".slime/PRUNED.md")
  & (Join-Path $Project "guardrails.cmd") check set primary -- python -V | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "guardrails check set failed" }
  $ConfigPath = Join-Path $Guardrails "config.json"
  & (Join-Path $Project "guardrails.cmd") uninstall --dry-run | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "guardrails uninstall --dry-run failed" }
  if (-not (Test-Path $ManifestPath)) { throw "uninstall dry-run removed manifest" }
  $RuntimePath = $Manifest.runtime
  $EnvironmentPath = $Manifest.environment
  "user modified launcher" | Set-Content -Encoding utf8 (Join-Path $Project "guardrails")
  & (Join-Path $Project "guardrails.cmd") uninstall | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "guardrails uninstall failed" }
  if (Test-Path $ManifestPath) { throw "uninstall left install manifest" }
  if (Test-Path $RuntimePath) { throw "uninstall left versioned runtime" }
  if (Test-Path $EnvironmentPath) { throw "uninstall left versioned environment" }
  if (-not (Test-Path $ConfigPath)) { throw "uninstall removed trusted config" }
  if ((Get-Content -Raw -Encoding utf8 (Join-Path $Project ".slime/PRUNED.md")).Trim() -ne "user archived history") {
    throw "uninstall changed .slime history"
  }
  $hooksAfter = Get-Content -Raw -Encoding utf8 (Join-Path $Project ".codex/hooks.json")
  if ($hooksAfter -notmatch "user-existing-hook") { throw "uninstall removed user hook" }
  if ($hooksAfter -match "guardrails_managed") { throw "uninstall left managed hooks" }
  if ((Get-Content -Raw -Encoding utf8 (Join-Path $Project "guardrails")).Trim() -ne "user modified launcher") {
    throw "uninstall removed modified managed content"
  }
  Start-Sleep -Seconds 2
  if (Test-Path (Join-Path $Project "guardrails.cmd")) { throw "uninstall left Windows launcher" }

  Write-Host "install.ps1 toolkit test OK"
}
finally {
  Remove-Item -Recurse -Force $Temp -ErrorAction SilentlyContinue
}
