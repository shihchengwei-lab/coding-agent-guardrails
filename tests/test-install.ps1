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

  & $Python -m agentcam.cli version | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "agentcam not installed into selected Python" }

  Write-Host "install.ps1 toolkit test OK"
}
finally {
  Remove-Item -Recurse -Force $Temp -ErrorAction SilentlyContinue
}
