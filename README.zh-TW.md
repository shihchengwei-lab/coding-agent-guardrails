# Coding Agent Guardrails

[English](README.md)

**CI 綠了不等於做完。做完的定義是：人類接得了手。**

Coding agent 會把任務做完，測試會過，檢查會變綠。然後一個人類要接手這份
diff——讀它、擁有它、維護它。這個工具包裝在 agent 那一側：一個指令裝好
四個工具，蓋住從「agent 開始打字」到「人類按下 merge」的整條走廊。

| 關卡 | 工具 | 它補上什麼 |
|---|---|---|
| agent 動工之前 | [kiss-my-diff](kiss-my-diff/) × [slime-coding](slime-coding/) 規則 | 一份統一紀律區塊進你的 `CLAUDE.md`（[templates/DISCIPLINE.md](templates/DISCIPLINE.md)）：最小可讀改動、最小語義位移、做完就停。 |
| agent 工作途中 | [slime-coding](slime-coding/) hooks | 自動關卡，把 agent 押在它動工前宣告的走廊裡。 |
| agent 說做完之後 | [agentcam](agentcam/) | 錄下實際改了什麼——檔案、風險旗標、diff 統計——並從實錄起草 PR 交接單。 |
| 人類 review 之前 | [corridor-ci](corridor-ci/) | 用實際 diff 驗證五行交接單，並把實錄證據附進 PR 報告。 |

## 安裝（一個指令）

```bash
git clone <這個 repo> ~/guardrails
~/guardrails/install.sh /path/to/your/project
pip install agentcam
```

重跑安全。安裝器會把紀律區塊接進 `CLAUDE.md`、裝好 slime-coding 的
hooks、放一份 corridor-ci 起手 workflow（你已有的不會被覆蓋）。

## 閉環

工具互相餵——這就是打包的意義：

1. **實錄** — `agentcam run -- <agent 指令>`（或在裝了 slime hooks 的
   Claude Code 裡工作）。agent 改的一切記錄在 `.git/agentcam/runs/`。
2. **交接** — `agentcam handoff` 從實錄印出五行交接單。貼進 PR 內文，
   再補上 `Decision` 和 `Verified`——只有作者知道的兩行。
3. **附證據** — `agentcam export latest --files .agentcam/` 把去敏後的
   實錄寫成可 commit 的檔案，隨 PR 一起提交。
4. **關卡** — corridor-ci 在 PR 上用實際 diff 驗證交接單，並把實錄證據
   （風險旗標、diff 統計）附進報告。證據只給 reviewer 看，
   永遠不影響檢查過不過。

每個工具都可以單獨使用——各子目錄有自己的 README。

## 版本規則

一個 repo、四個工具，release tag 以工具名為前綴：`agentcam-v0.3.0`、
`corridor-ci-v11`⋯⋯。更早的版本（`v0.2.0`、`v10`⋯⋯）留在各工具原本的
repo 裡。

## 歷史

每個工具原本是獨立 repo，搬進來時完整保留 commit 歷史——在任何子目錄裡
`git log`，都能一路回到該工具的第一個 commit。

## 授權

MIT——整個工具包與其中每個工具皆是。
