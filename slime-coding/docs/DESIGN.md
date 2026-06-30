# 設計與參考

Slime Coding 的機制細節。理念與手動流程見 [`CONCEPT.md`](CONCEPT.md);機制驗證
狀態見 [README](../README.md)。

## 核心原則：請求 vs 強制

- **prompt 是請求。** 寫在 `CLAUDE.md` 的「不要做 X」，模型可以略過。
- **hook 是強制。** 條件命中就每次執行，不依賴模型記得。
- **牙齒只能長在無歧義的訊號上。** 用模糊判斷去 hard-block，誤攔會訓練使用者把
  hook 關掉，比沒有閘門更糟——所以閘門只收 git 事實。路徑是否落在
  `corridor.md` 的 `## Paths` 內也是 git 事實，所以走廊外 product-code edit 預設擋；
  touched files、API 變動這類模糊成本訊號只回報。

## 四層

| 層 | 承載 | 機制 | 牙齒 |
|---|---|---|---|
| L0 紀律 | frontier 規則、走廊 artifact | `CLAUDE.md` + `slime-navigate` skill + `corridor.md` | 無（請求） |
| L1 狀態 | 剪枝紀錄的跨輪保存 | `PRUNED.md` + 注入 hook | 注入確定，內容為狀態 |
| L2 閘門 | git 事實的硬擋 | command-type hook（block） | 有 |
| L3 量測 | 模糊成本訊號 | report-only hook | 無（只回報） |

### L0 紀律
`slime-navigate` skill 模板化：Goal Frontier、Start Frontier、Meeting
Corridor、Semantic Delta、Non-goals、Pruned Paths、Stop Condition。把
`templates/CLAUDE.slime.md` 貼進專案的 `CLAUDE.md`。走廊寫成
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

### L2 閘門（全 command-type，零推論）
`bin/patch-cost` 只收 git 事實，三個硬擋：
- **新增依賴**：Stop hook 比對 `pubspec.yaml` 的 `dependencies` 鍵集 → 新增就
  block，要求確認保留或移除。
- **typecheck 閘門（接觸感測器）**：Stop 時跑 `SLIME_TYPECHECK_CMD`（如
  `dart analyze`），紅燈就 block。它擋的是 agentic AI 最危險的幻覺——**虛構踏板**
  （在兩個真接點之間插一個命名漂亮、但 repo 裡 resolve 不出來的符號 / API）。
  type checker 就是「這根觸鬚有沒有碰到實體」的感測器。**它沒有 log-and-leave
  出口**(這是它跟下面紅燈閘的關鍵差別)：resolve 不出來的 reference 是**壞掉的
  code**,不是「放棄但已記錄的設計」,只能修掉、或承認它是新工作回去更新走廊。
  opt-in（env 未設則退化）；只看 exit code、不解析輸出（不解析正是避免在自己身上
  過度實作）；指令找不到 / timeout 一律退化、不誤擋。
- **收工紅燈閘**（牙齒長在無歧義事實「**Stop 時 `SLIME_TEST_CMD` 紅燈**」上，
  不是長在「有沒有剪枝」這種腦內判斷上——放棄一個設計不是 git 事實）：
  `SLIME_TEST_CMD` exit ≠ 0 且 `PRUNED.md` **相對 HEAD 沒有未提交變更** → block。
  兩條出路：把檢查弄綠，或（若這是放棄的設計）把它寫進 `PRUNED.md` 再收工——
  寫 `PRUNED.md` 只是「帶紅燈收工」的確認動作，不是這道閘的本體。判定用
  `git status --porcelain`（working-tree dirty），不是 Claude Code 的 session
  boundary。
- **走廊閘門**：PreToolUse 掛 `Edit|Write`，`.slime/corridor.md` 不存在、或還是
  template（id `example-feature`、`## Paths` 空、或仍是範例 glob）就 `deny`；但
  寫 `.slime/` 底下的 artifact 本身永遠放行，避免「沒走廊不能建走廊」的死鎖。
  另放行 repo 元資料檔（`.gitignore`、`.gitattributes`、`.editorconfig`、
  `LICENSE`(`.md`/`.txt`)、`CHANGELOG.md`，basename 比對）——這些不是 product
  code，沒有 frontier 可算，硬擋只是摩擦。
  Stop 時若 product-code edit 落在 `## Paths` 外，預設 `block`：要求先縮回走廊，
  或更新 corridor 並寫出新 evidence。`.slime/` artifact 與 repo metadata 仍不擋。
  > 代價：這不是硬安全邊界——agent 可以先改 `corridor.md` 把走廊撐大再動別的
  > 檔案。改走廊本身可能是合法的新 evidence，所以不直接擋，但會由 L3 顯示出來。
  > 若要退回只回報模式，可設定 `SLIME_STRICT_CORRIDOR=0`。

### L3 量測（成本訊號）
`bin/patch-cost` 在 Stop 時當 `systemMessage` 回報模糊訊號：touched / new files
計數、public API 變更（Dart `export` / `class` / …）、走廊外檔案（讀
`corridor.md` 的 `## Paths` 判定）、**這輪是否動過 `corridor.md`**。
`systemMessage` 是給**使用者**看的（L3 的定位就是給人看的成本訊號）。其中
走廊外 product-code edit 也會餵給 L2 Stop gate，預設 hard stop；其他成本訊號只回報。

### Git commit evidence（審查證據）
`bin/commit-evidence` 由 Git `prepare-commit-msg` hook 呼叫。它不 block commit，
只把目前 `.slime/corridor.md` 與 staged diff 的事實摘要 append 到 commit message：
Corridor id、Scope、Semantic Delta、Paths、staged touched files、走廊外檔案數、
新增依賴與 Stop Condition。這不是新的正確性證明；它的用途是讓 git history 保留
「這個 diff 對應哪條走廊」的審查線索。已經有 `Slime-Evidence:` 區塊時不重複附加。

## 安裝細節

`install.sh`（可重跑、idempotent，會備份 `settings.json`）：

1. 把兩個 Claude hook script（`prune-inject`、`patch-cost`）接進專案
   `.claude/settings.json`，共掛在四個 event（SessionStart、UserPromptSubmit、
   PreToolUse、Stop）；command 用**這個 clone 的絕對路徑**並以 `python3` 執行
   （有加引號，路徑含空白也不會壞、也不依賴 executable bit）——只取代既有的
   Slime Coding hook，不動你其他的 hook。
2. 把 Git `prepare-commit-msg` hook 接到 `bin/commit-evidence`。若原本已有 hook，
   會保留原內容，只替換 Slime 自己的區塊。
3. 把 `slime-navigate` skill 與 `/slime-corridor`、`/slime-prune` 兩個 command
   **symlink** 進 `.claude/`（之後 `git pull` 這個 clone 就會更新）。
4. 若專案還沒有 `.slime/`，把 `templates/.slime/` 種進去（先換成你自己的內容再
   寫 code，template corridor 會被 L2 擋）。

手動一步（L0 紀律是請求、不強制）：把 `templates/CLAUDE.slime.md` 貼進專案
`CLAUDE.md`。

> 手動安裝：把 `hooks/hooks.template.json` 裡的 `__SLIME_HOME__` 換成 clone 絕對
> 路徑，merge 進 `.claude/settings.json`。

## 設定（env）

| 變數 | 預設 | 作用 |
|---|---|---|
| `SLIME_PRUNE_RECENT` | `5` | L1 注入時保留的近 N 筆剪枝；`0` = 只靠走廊比對；非數字 / 負數 fallback 回 5（不會 crash） |
| `SLIME_TYPECHECK_CMD` | 無 | L2 typecheck 閘門的指令（Dart 建議 `dart analyze`）；未設則此閘門退化 |
| `SLIME_TEST_CMD` | 無 | L2 收工紅燈閘的檢查指令；未設則此閘門退化 |
| `SLIME_TEST_TIMEOUT` | `600` | typecheck 與 check 共用的 timeout（秒） |
| `SLIME_PUBSPEC` | `pubspec.yaml` | 依賴清單路徑（非 Dart 專案可改） |
| `SLIME_STRICT_CORRIDOR` | strict | 預設阻擋走廊外 product-code edit；設為 `0` / `false` / `no` / `off` 時退回只回報。repo metadata 與 `.slime/` artifact 不擋 |

## Slash commands

- `/slime-corridor [id]` — 產出 / 更新 `.slime/corridor.md`。
- `/slime-prune [理由]` — 把否決走廊 append 進 `.slime/PRUNED.md`。

## artifact 格式

`.slime/corridor.md` 需含 `# Corridor: <id>`、`## Semantic Delta`、`## Non-goals`
與 `## Paths` 清單（glob）。
`.slime/PRUNED.md` 每筆以 `## [date] corridor:<id>` 開頭。範例見
`templates/.slime/`。

## 結構

```text
slime-coding/
├── install.sh                          # clone 後對目標專案跑這個
├── hooks/hooks.template.json           # hook 接線範本（__SLIME_HOME__ 佔位）
├── bin/
│   ├── patch-cost                      # L2 確定子集 + L3 模糊子集
│   ├── prune-inject                    # L1 注入 + 衰減
│   └── commit-evidence                 # Git commit message evidence
├── skills/slime-navigate/SKILL.md      # L0
├── commands/{slime-prune,slime-corridor}.md
├── templates/
│   ├── CLAUDE.slime.md                 # L0 貼進專案 CLAUDE.md
│   └── .slime/{corridor.md,PRUNED.md}  # artifact 範例
├── tests/test.sh                       # Claude hook 行為測試
├── tests/test-commit-evidence.sh       # Git commit evidence 測試
├── docs/                                # 概念、機制設計
└── README.md
```

## 測試

`tests/test.sh`（需要 python3 + git）跑 hook 的行為測試：走廊閘門、bootstrap
放行、template 拒絕、`SLIME_PRUNE_RECENT` 異常值、Stop 的依賴 / 紅燈 / typecheck
閘門、預設走廊外 product-code block，以及 `SLIME_STRICT_CORRIDOR=0` 的只回報降級。

```bash
./tests/test.sh
./tests/test-commit-evidence.sh
```

## 前提與限制

- 需求要能寫成可觀察的驗收條件；寫不出來的模糊任務先做 discovery。
- 收工紅燈閘依賴可執行的測試或檢查（`SLIME_TEST_CMD`）；沒有可跑的檢查時這條
  退化。
- typecheck 閘門（`SLIME_TYPECHECK_CMD`）只在「有可跑的 type checker / analyzer」
  的語言（Dart `dart analyze`、TS `tsc`…）有效；它擋得到「名字 resolve 不出來」，
  擋不到「名字在但語意選錯」。別把 analyzer 塞進 `SLIME_TEST_CMD`——那會讓「沒編
  譯過」變成可以「記一筆就帶紅燈收工」，而虛構踏板不該被這樣放過。這是**機制**，
  不宣稱「實測降低幻覺」。
- 衰減鍵（走廊 id / 近 N 筆）決定 context 成本上界；近 N 由 `SLIME_PRUNE_RECENT`
  控制。
- L2 的依賴閘門目前針對 Dart/Flutter 的 `pubspec.yaml`；換語言時改 `SLIME_PUBSPEC`
  與 `bin/patch-cost` 的解析。

## 參考

- Hooks: https://code.claude.com/docs/en/hooks
- Sub-agents: https://code.claude.com/docs/en/sub-agents
- Settings（hooks 寫在 `.claude/settings.json`）: https://code.claude.com/docs/en/settings
