# Coding Agent Guardrails

[English](README.md)

**CI 綠了不等於做完。做完的定義是：人類接得了手。**

Coding agent 會把任務做完，測試會過，檢查會變綠。然後一個人類要接手這份
diff——讀它、擁有它、維護它。這個工具包裝在 agent 那一側：一個指令裝好
四個工具，蓋住從「agent 開始打字」到「人類按下 merge」的整條走廊。

| 關卡 | 工具 | 它補上什麼 |
|---|---|---|
| agent 動工之前 | [kiss-my-diff](kiss-my-diff/) × [slime-coding](slime-coding/) 規則 | 一份統一紀律區塊進你的 `CLAUDE.md` 與 `AGENTS.md`（[templates/DISCIPLINE.md](templates/DISCIPLINE.md)）：最小可讀改動、最小語義位移、做完就停。 |
| agent 工作途中 | [slime-coding](slime-coding/) hooks | 自動關卡，把 agent 押在它動工前宣告的走廊裡。 |
| agent 說做完之後 | [agentcam](agentcam/) | 錄下實際改了什麼——檔案、風險旗標、diff 統計——並從實錄起草 PR 交接單。 |
| 人類 review 之前 | [corridor-ci](corridor-ci/) | 用實際 diff 驗證五行交接單，並把實錄證據附進 PR 報告。 |

## Look Ma, no PRs

老實揭露：我不是軟體工程師，一行程式碼都不會寫，沒審過 PR，也沒逐行
讀過 diff。翻這個 repo 的歷史就知道——commit 都是 agent 直接推上 main 的，
少數幾個 PR 也是 agent 開來拿這些工具測自己用的。我對那幾個 PR 的
review 流程：看到綠燈，按下 merge。對，正是這個工具包要抓的那種行為。
一個純粹的 vibe coder。

而這正是這個工具包存在的原因。我無條件信任 agent 的產出，因為我沒有
能力不信。剩下能懷疑的只有工作過程：到底改了什麼、檢查有沒有真的跑、
下一個人接不接得了手。這裡的每個工具都在做同一件事——把「相信我」換成
「有紀錄的事實」。這套 guardrails 不是圍著程式碼蓋的，是圍著一個讀不懂
程式碼的人的工作流程蓋的。

## 安裝（一個指令）

```bash
git clone https://github.com/shihchengwei-lab/coding-agent-guardrails ~/guardrails
~/guardrails/install.sh /path/to/your/project
```

重跑安全。安裝器會把紀律區塊（規則＋agentcam 交接循環）接進
`CLAUDE.md` 與 `AGENTS.md`（Claude Code 讀前者、Codex 等讀後者）、
裝好 slime-coding 的 hooks、放一份 corridor-ci 起手 workflow（你已有
的不會被覆蓋）、把 agentcam 從這份 checkout 直接 pip 裝進你目前的
Python（需 3.11 以上），並接好 agentcam 的 session 掛鉤——Claude Code
的 session 不用打 `agentcam run` 也會自動錄。

## 閉環

工具互相餵——這就是打包的意義：

1. **實錄** — `agentcam run -- <agent 指令>`（或直接在 Claude Code 裡
   工作：安裝器接好的 agentcam session 掛鉤會自動錄）。agent 改的一切
   記錄在 `.git/agentcam/runs/`。取捨先講明：hook 模式的證據比較薄——
   Claude Code 不會把終端輸出餵給掛鉤，所以輸出樣式型的風險旗標
   （`rm -rf` 之類）抓不到；要最完整的實錄，用 `agentcam run` 包著跑。
2. **驗證** — `agentcam verify -- pytest -q`。由 agentcam 親自執行測試，
   記下指令、退出碼、耗時——是儀器量到的事實，不是 agent 的自述。
   通過的檢查會自動草擬交接單的 `Verified` 行。
3. **交接** — `agentcam handoff` 從實錄印出五行交接單。貼進 PR 內文，
   再補上 `Decision`——只有作者知道的一行（沒有通過的驗證紀錄時，
   `Verified` 也留給作者填）。
4. **附證據** — `agentcam export latest --files .agentcam/` 把去敏後的
   實錄寫成可 commit 的檔案，隨 PR 一起提交。
5. **關卡** — corridor-ci 在 PR 上用實際 diff 驗證交接單，並把實錄證據
   （風險旗標、驗證紀錄、diff 統計）附進報告。證據只給 reviewer 看，
   永遠不影響檢查過不過。

每個工具都可以單獨使用——各子目錄有自己的 README。

## 版本規則

一個 repo、四個工具，release tag 以工具名為前綴：`agentcam-v0.3.2`、
`corridor-ci-v11`⋯⋯。更早的版本（`v0.2.0`、`v10`⋯⋯）留在各工具原本的
repo 裡。

## 歷史

每個工具原本是獨立 repo，搬進來時完整保留 commit 歷史——在任何子目錄裡
`git log`，都能一路回到該工具的第一個 commit。

## 授權

MIT——整個工具包與其中每個工具皆是。
