# 設計與參考

Slime Coding 的機制細節。理念與手動流程見 [`CONCEPT.md`](CONCEPT.md);機制驗證
狀態見 [README](../README.md)。

## 核心原則：請求 vs 強制

- **prompt 是請求。** 寫在 `CLAUDE.md` / `AGENTS.md` 的「不要做 X」，模型可以略過。
- **hook 對可觀察事件是強制流程。** 條件命中就每次執行，不依賴模型記得；它不是 filesystem sandbox，也不能預測所有 shell 副作用。
- **牙齒只能長在可重現的訊號上。** 用模糊判斷去 hard-block，誤攔會訓練使用者把
  hook 關掉，比沒有閘門更糟。路徑、命令 exit code、manifest 差異與檔案數都可
  重現；touched / new files 只作成本回報，除非它命中明確的 trivial 單檔規則。

## 四層

| 層 | 承載 | 機制 | 牙齒 |
|---|---|---|---|
| L0 紀律 | frontier 規則、走廊 artifact | `CLAUDE.md` / `AGENTS.md` + `slime-navigate` skill + `corridor.md` | 無（請求） |
| L1 狀態 | 剪枝紀錄的跨輪保存 | `PRUNED.md` + 注入 hook | 注入確定，內容為狀態 |
| L2 閘門 | git 事實的硬擋 | command-type hook（block） | 有 |
| L3 量測 | 模糊成本訊號 | report-only hook | 無（只回報） |

### L0 紀律
`slime-navigate` 先用 Goal / Start Frontier 找到接點，再只把執行契約寫入 artifact：
Rigor、Outcome、Paths、支持／反證 Evidence、Stop Condition；high 再加入 High-risk Controls
（Failure mode、Rollback、Independent check ID）。把
紀律文本由 monorepo 根安裝器寫進專案的 `CLAUDE.md` 與 `AGENTS.md`（單一來源是
根目錄 `templates/DISCIPLINE.md`；`install-codex.ps1` 讀同一份）。走廊寫成
`.slime/corridor.md`，供 L2、L3 讀。
> 內建 Explore / Plan 子 agent 會跳過 `CLAUDE.md`，所以探索階段的紀律綁在主
> agent 上。

### L1 狀態（剪枝紀錄）
要修的失敗：agentic loop 復活上一輪已否決的設計，因為否決理由不在 context。
- 檔案 `.slime/PRUNED.md`：git 進版、跨 session 存活、append-only。
- `bin/prune-inject` 掛 SessionStart + UserPromptSubmit，透過 `additionalContext`
  注入主 agent。
- **衰減**：只注入與當前走廊相關、或近 N 筆的剪枝（`SLIME_PRUNE_RECENT`，預設
  5），避免 `PRUNED.md` 單調成長線性燒 token。
- 抵達編輯子 agent：子 agent 有獨立 context、不吃主 session 注入。靠兩件事補——
  `CLAUDE.md` 寫「編輯前先讀 `.slime/PRUNED.md`」，或 planner 委派時把剪枝摘要
  寫進 task prompt。

### L2 閘門（可重現事實）
`bin/patch-cost` 執行六個硬擋：

- **turn baseline**：SessionStart／UserPromptSubmit create-if-absent 地保存 HEAD、髒檔
  content/index fingerprint、dependency baseline 與 corridor hash 到
  `<git-dir>/slime/turns/<hashed-id>/baseline.json`。Stop 成功才清除；阻擋時保留。
  本輪 delta 也納入 baseline HEAD 到目前 HEAD 的 committed paths，因此既有髒檔未變
  不算，修改／stage／commit／rename／delete／restore 都算。payload 無 id 或 baseline
  缺失時退回 HEAD 比對並標成 partial，不會靜默放行。
- **走廊格式與路徑**：PreToolUse 掛 `Edit|Write|apply_patch`；Claude payload 讀
  `file_path`，Codex payload 解析 patch 的 Add／Update／Delete／Move targets。缺少
  有效 corridor、無法辨認目標、或目標不在 `## Paths` 內就 `deny`。Stop 再檢查
   本輪 delta。`PostToolUse: Bash` 在 shell 完成後立即檢查越界修改並要求復原，Stop
   再做最終阻擋；hook 不宣稱能在 shell 執行前預測所有寫入。`*`、`**`、`**/*` 會被視為
  match-all 而拒絕；`../` 與絕對 Paths 也不能授權 repo 外寫入。`.slime/` artifact 與保守列出的
  repo metadata 放行，避免 bootstrap
  死鎖。未寫 `## Rigor` 的 artifact 在產生 product delta 後會要求遷移；新格式依 tier
  驗 section 與固定 label。
- **新增依賴**：Stop 比對 pubspec、npm、requirements、pyproject、Cargo、Go
  manifest；新增 package 必須移除，或在 Evidence 寫
  `- Dependency: <package> — <reason>`。
- **trusted checks**：Stop Condition 只接受 `Check: <id>` 或具體 `Manual:`。
  ID 只從 `<git-dir>/guardrails/config.json` 解析為 argv，使用 `shell=False`、repo root cwd
  執行；repo 內 Markdown 不再提供 shell。失敗、timeout、未知 ID 或壞 config 都 block。
- **high secondary check**：`Independent check: <id>` 必須存在，且 ID 與 normalized argv
  都不同於 primary checks；每次 Stop 執行，紅燈或無法執行都 block。
- **trivial 範圍**：trivial corridor 最多改一個 product file；超過就縮小變更或改用
  normal。normal / high 不設任意檔案數上限，由 Paths 與驗證契約控制。

這些是流程閘門，不是權限安全邊界；能修改 hook 的 actor 仍能移除它們。direct edit
在寫前阻擋，shell 只能寫後偵測；只有 sandbox／OS 權限能提供 filesystem 硬邊界。

### L3 量測（成本訊號）
`bin/patch-cost` 在 Stop 時用 `systemMessage` 回報所選 Rigor、touched / new files、
走廊外檔案，以及這輪是否動過 `corridor.md`。它只呈現成本與邊界事實；真正影響
能否收工的規則都在 L2 明列。

## 安裝細節

`install.sh`（可重跑、idempotent；不留永久備份，失敗時由 transaction journal 還原）：

1. 把兩個 Claude hook script（`prune-inject`、`patch-cost`）接進專案
   `.claude/settings.json`，共掛在五個 event（SessionStart、UserPromptSubmit、
   PreToolUse、PostToolUse、Stop）；command 用**這個 clone 的絕對路徑**並以 `python3` 執行
   （有加引號，路徑含空白也不會壞、也不依賴 executable bit）——只取代既有的
   Slime Coding hook，不動你其他的 hook。
2. 把 `slime-navigate` skill 與 `/slime-corridor`、`/slime-prune` 兩個 command
   **symlink** 進 `.claude/`（之後 `git pull` 這個 clone 就會更新）。
3. 若專案還沒有 `.slime/`，把 `templates/.slime/` 種進去（先換成你自己的內容再
   寫 code，template corridor 會被 L2 擋）。

L0 紀律文本（請求、不強制）由 monorepo 根安裝器寫進 `CLAUDE.md` 與
`AGENTS.md`，單一來源是根目錄 `templates/DISCIPLINE.md`。

> 手動安裝：把 `hooks/hooks.template.json` 裡的 `__SLIME_HOME__` 換成 clone 絕對
> 路徑，merge 進 `.claude/settings.json`。

`install-codex.ps1`（Windows / Codex，可重跑、idempotent）：

1. 把同一組 `prune-inject`、`patch-cost` 接進專案 `.codex/hooks.json`。Codex
   專用 template 是 `hooks/codex.hooks.template.json`，包含 `commandWindows`。
2. 把 `slime-navigate` skill 複製到 `.agents/skills/slime-navigate`，讓 Codex 的
   repo-local skill discovery 能看到它。
3. 把根目錄 `templates/DISCIPLINE.md` 插進 `AGENTS.md` 的 managed block（與根
   安裝器同一組標記，先跑誰都只留一塊）；重跑時只替換這個 block，不動既有
   專案指引。
4. 若專案還沒有 `.slime/`，把 `templates/.slime/` 種進去。

Codex repo-local hooks 需要在 Codex 裡用 `/hooks` review/trust；AGENTS.md 和
repo-local skills 要在新 run 或重啟 Codex 後重新載入。

## 設定

Trusted check 設定存於 `<git-dir>/guardrails/config.json`，schema 1。每個 check 包含
非空字串 `argv` 陣列與可選的 `timeout_seconds`（1–3600，預設 600）。

| 變數 | 預設 | 作用 |
|---|---|---|
| `SLIME_PRUNE_RECENT` | `5` | L1 注入時保留的近 N 筆剪枝；`0` = 只靠走廊比對；非數字 / 負數 fallback 回 5（不會 crash） |
| `SLIME_TEST_TIMEOUT` | `3600` | trusted checks 的全域 timeout 上限（1–3600 秒） |
| `SLIME_PUBSPEC` | `pubspec.yaml` | 額外指定 pubspec 路徑；其他支援 manifest 由工具自動找出 |

## Slash commands

- `/slime-corridor [id]` — 產出 / 更新 `.slime/corridor.md`。
- `/slime-prune [理由]` — 把否決走廊 append 進 `.slime/PRUNED.md`。

## artifact 格式

`.slime/corridor.md` 一律需含 `# Corridor: <id>` 與 `## Paths` 清單（glob）。
新 artifact 明確加入 `## Rigor`：trivial 需 Outcome、Paths、Stop Condition；normal
再需含 `Supports:`／`Would falsify:` 的 Evidence；high 再需 `## High-risk Controls` 中的
`Failure mode:`、`Rollback:`、`Independent check:`。舊 artifact 不含 Rigor 時只要出現
product delta 就明確要求遷移。
`.slime/PRUNED.md` 每筆以 `## [date] corridor:<id>` 開頭。範例見
`templates/.slime/`。

## 結構

```text
slime-coding/
├── install.sh                          # clone 後對目標專案跑這個
├── install-codex.ps1                   # Codex / Windows installer
├── hooks/hooks.template.json           # hook 接線範本（__SLIME_HOME__ 佔位）
├── hooks/codex.hooks.template.json     # Codex hook template（含 commandWindows）
├── bin/
│   ├── patch-cost                      # L2 確定子集 + L3 模糊子集
│   └── prune-inject                    # L1 注入 + 衰減
├── skills/slime-navigate/SKILL.md      # L0
├── commands/{slime-prune,slime-corridor}.md
├── templates/
│   └── .slime/{corridor.md,PRUNED.md}  # artifact 範例（L0 文本 → 根 templates/DISCIPLINE.md）
├── tests/test.sh                       # Claude hook 行為測試
├── tests/test-codex-install.ps1        # Codex installer 測試
├── docs/                                # 概念、機制設計
└── README.md
```

## 測試

`tests/test.sh`（需要 python3 + git）跑 hook 的行為測試：走廊格式與實際 edit path、
三級 Rigor 與無 Rigor 拒絕、bootstrap 放行、template 拒絕、`SLIME_PRUNE_RECENT`
異常值、跨語言依賴、trusted checks、持續紅燈、走廊外 block 與 trivial
單檔限制。

```bash
./tests/test.sh
```

## 前提與限制

- 需求要能寫成可觀察的驗收條件；寫不出來的模糊任務先做 discovery。
- 完成閘依賴 trusted `Check:`；沒有可配置的工具檢查時必須使用具體 `Manual:`，不能
  把 repo 文字當成可執行 shell。
- 衰減鍵（走廊 id / 近 N 筆）決定 context 成本上界；近 N 由 `SLIME_PRUNE_RECENT`
  控制。
- L2 依賴閘目前支援 pubspec、npm package.json、requirements.txt、PEP 621 / Poetry
  pyproject、Cargo.toml、go.mod；TOML 解析需要 Python 3.11+ 的 `tomllib`。

## 參考

- Hooks: https://code.claude.com/docs/en/hooks
- Sub-agents: https://code.claude.com/docs/en/sub-agents
- Settings（hooks 寫在 `.claude/settings.json`）: https://code.claude.com/docs/en/settings
