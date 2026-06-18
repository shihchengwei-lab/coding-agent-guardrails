# Slime Coding

把 Slime Coding 落到 Claude Code 的工作流：clone 這個 repo，跑 `install.sh` 把
紀律接進專案的 hooks / skill / commands。

Slime Coding 約束 agentic AI 的過度實作：不從 prompt 直接生成 code，而是先讓
需求與現有 repo 各自長出 frontier，只在兩者交會的最小走廊（corridor）動手，沒有
evidence 的路徑剪掉並記錄。這個 repo 把那套紀律綁到 Claude Code 真正會強制執行的
機制上。

## 核心原則：請求 vs 強制

- **prompt 是請求。** 寫在 `CLAUDE.md` 的「不要做 X」，模型可以略過。
- **hook 是強制。** 條件命中就每次執行，不依賴模型記得。
- **牙齒只能長在無歧義的訊號上。** 用模糊判斷去 hard-block，誤攔會訓練使用者把
  hook 關掉，比沒有閘門更糟——所以閘門只收 git 事實，模糊訊號只回報。

## 四層

| 層 | 承載 | 機制 | 牙齒 |
|---|---|---|---|
| L0 紀律 | frontier 規則、走廊 artifact | `CLAUDE.md` + `slime-navigate` skill + `corridor.md` | 無（請求） |
| L1 狀態 | 剪枝紀錄的跨輪保存 | `PRUNED.md` + 注入 hook | 注入確定，內容為狀態 |
| L2 閘門 | git 事實的硬擋 | command-type hook（block） | 有 |
| L3 量測 | 模糊成本訊號 | report-only hook | 無（只回報） |

### L0 紀律
`slime-navigate` skill 模板化五個輸出：Goal Frontier、Start Frontier、Meeting
Corridor、Pruned Paths、Stop Condition。把 `templates/CLAUDE.slime.md` 貼進專案
的 `CLAUDE.md`。走廊寫成 `.slime/corridor.md`，供 L2、L3 讀。
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

### L2 閘門（全 command-type，零推論）
`bin/patch-cost` 只收 git 事實，三個硬擋：
- **新增依賴**：Stop hook 比對 `pubspec.yaml` 的 `dependencies` 鍵集 → 新增就
  block，要求確認保留或移除。
- **剪枝補登**：Stop hook，`SLIME_TEST_CMD` exit ≠ 0 且 `PRUNED.md` **相對 HEAD
  沒有未提交變更**（即這輪沒補登剪枝）→ block，要求把否決走廊寫進 `PRUNED.md`
  再結束。判定用 `git status --porcelain`，是 working-tree dirty，不是 Claude
  Code 的 session boundary。
- **走廊閘門**：PreToolUse 掛 `Edit|Write`，`.slime/corridor.md` 不存在、或還是
  template（id `example-feature`、`## Paths` 空、或仍是範例 glob）就 `deny`；但
  寫 `.slime/` 底下的 artifact 本身永遠放行，避免「沒走廊不能建走廊」的死鎖。

### L3 量測（永不 block）
`bin/patch-cost` 在 Stop 時當 `systemMessage` 回報模糊訊號：touched / new files
計數、public API 變更（Dart `export` / `class` / …）、走廊外檔案（讀
`corridor.md` 的 `## Paths` 判定）。`systemMessage` 是給**使用者**看的（L3 的定位
就是給人看的成本訊號）；因為不擋，誤判不會升級成棄用。

## 安裝（clone 下來自己裝，不走 plugin）

把這個 repo clone 到任何位置，對目標專案跑一次 `install.sh`：

```bash
git clone <this-repo> ~/slime-coding
cd /path/to/your/project
~/slime-coding/install.sh .        # 省略參數時預設裝到當前目錄
```

`install.sh` 會（可重跑、idempotent，會備份 settings.json）：

1. 把三個 hook 接進專案 `.claude/settings.json`，command 用**這個 clone 的絕對
   路徑**（有加引號，路徑含空白也不會壞）——只取代既有的 Slime Coding hook，不
   動你其他的 hook。
2. 把 `slime-navigate` skill 與 `/slime-corridor`、`/slime-prune` 兩個 command
   **symlink** 進 `.claude/`（之後 `git pull` 這個 clone 就會更新）。
3. 若專案還沒有 `.slime/`，把 `templates/.slime/` 種進去（先換成你自己的內容再
   寫 code，template corridor 會被 L2 擋）。

剩一步手動（L0 紀律是請求、不強制）：把 `templates/CLAUDE.slime.md` 貼進專案
`CLAUDE.md`。

> hook script 是純 Python 3 stdlib，`install.sh` 也只依賴 python3。手動安裝的人
> 可直接把 `hooks/hooks.template.json` 裡的 `__SLIME_HOME__` 換成 clone 絕對路徑，
> merge 進 `.claude/settings.json`。

## 設定（env）

| 變數 | 預設 | 作用 |
|---|---|---|
| `SLIME_PRUNE_RECENT` | `5` | L1 注入時保留的近 N 筆剪枝；`0` = 不注入近期、只靠走廊比對；非數字 / 負數會 fallback 回 5（不會 crash） |
| `SLIME_TEST_CMD` | 無 | L2 剪枝閘門用的檢查指令；未設則此閘門退化 |
| `SLIME_TEST_TIMEOUT` | `600` | 檢查的 timeout（秒） |
| `SLIME_PUBSPEC` | `pubspec.yaml` | 依賴清單路徑（非 Dart 專案可改） |

## Slash commands

- `/slime-corridor [id]` — 產出 / 更新 `.slime/corridor.md`。
- `/slime-prune [理由]` — 把否決走廊 append 進 `.slime/PRUNED.md`。

## artifact 格式

`.slime/corridor.md` 需含 `# Corridor: <id>` 與 `## Paths` 清單（glob）。
`.slime/PRUNED.md` 每筆以 `## [date] corridor:<id>` 開頭。範例見
`templates/.slime/`。

## 結構

```text
slime-coding/
├── install.sh                           # clone 後對目標專案跑這個
├── hooks/hooks.template.json            # hook 接線範本（__SLIME_HOME__ 佔位）
├── bin/
│   ├── patch-cost                        # L2 確定子集 + L3 模糊子集
│   └── prune-inject                      # L1 注入 + 衰減
├── skills/slime-navigate/SKILL.md        # L0
├── commands/{slime-prune,slime-corridor}.md
├── templates/
│   ├── CLAUDE.slime.md                   # L0 貼進專案 CLAUDE.md
│   └── .slime/{corridor.md,PRUNED.md}    # artifact 範例
└── README.md
```

## 前提與限制

- 需求要能寫成可觀察的驗收條件；寫不出來的模糊任務先做 discovery。
- 剪枝補登閘門依賴可執行的測試或檢查（`SLIME_TEST_CMD`）；沒有可跑的檢查時這條
  退化。
- 衰減鍵（走廊 id / 近 N 筆）決定 context 成本上界；近 N 由 `SLIME_PRUNE_RECENT`
  控制。
- L2 的依賴閘門目前針對 Dart/Flutter 的 `pubspec.yaml`；換語言時改 `SLIME_PUBSPEC`
  與 `bin/patch-cost` 的解析。

## 參考

- Hooks: https://code.claude.com/docs/en/hooks
- Sub-agents: https://code.claude.com/docs/en/sub-agents
- Settings（hooks 寫在 `.claude/settings.json`）: https://code.claude.com/docs/en/settings

## License

MIT — see [`LICENSE`](LICENSE)。變更紀錄見 [`CHANGELOG.md`](CHANGELOG.md)。
