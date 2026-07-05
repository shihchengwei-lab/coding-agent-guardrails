# Coding Agent Guardrails

[English](README.md)

**CI 綠了不等於做完。做完的定義是：人類接得了手。**

Coding agent 會把任務做完，測試會過，檢查會變綠。然後呢？一個人類要接手這份
diff——讀它、擁有它、維護它。agent 留下的一切，最後都會落在那個人的桌上。

這個 repo 是四個裝在 agent 側的工具，在「下 prompt」到「按下 merge」之間的
四個關卡，把 agent 押在交接標準上。每個工具背後是一個工作哲學：

| 關卡 | 工具 | 哲學 | 是什麼 |
|---|---|---|---|
| agent 動工之前 | [kiss-my-diff](kiss-my-diff/) | 奧卡姆剃刀 | 一份極小的 `AGENT.md` 規則檔：最小可讀改動、做完就停。實測：patch 小 31%、碰的檔案少 20%。 |
| agent 工作途中 | [slime-coding](slime-coding/) | 黏菌哲學 | Claude Code hooks + skills，管的是最小語義位移——只改這次需求必須改的，不順手動架構和命名。 |
| agent 說做完之後 | [agentcam](agentcam/) | 看你怎麼做，不看你怎麼說 | 本機優先的 CLI 外殼，錄下 agent 實際改了什麼，產出 Markdown 執行報告。 |
| 人類 review 之前 | [corridor-ci](corridor-ci/) | 第一性原理：寫 code 便宜了，review 沒有 | GitHub Action，要求每個非瑣碎 PR 先交五行交接單——範圍、從哪讀起、驗證了什麼——才配得到 review 注意力。 |

每個工具可以單獨用；合起來，它們蓋住從「agent 開始打字」到「人類按下 merge」
的整條走廊。

## 快速開始

- **kiss-my-diff** — 把 [`kiss-my-diff/AGENT.md`](kiss-my-diff/AGENT.md)
  複製進你的 repo，安裝就結束了。
- **slime-coding** — clone 這個 repo，然後
  `./slime-coding/install.sh /path/to/your/project`。
- **agentcam** — `pip install agentcam`
  （[PyPI](https://pypi.org/project/agentcam/)）。
- **corridor-ci** — 在你的 workflow 裡：
  `uses: shihchengwei-lab/coding-agent-guardrails/corridor-ci@<tag>`。

細節與文件在各工具自己的 README。

## 版本規則

一個 repo、四個工具，所以 release tag 以工具名為前綴：
`agentcam-v0.3.0`、`corridor-ci-v11`⋯⋯。更早的版本
（`v0.2.0`、`v10`⋯⋯）留在各工具原本的 repo 裡。

## 歷史

每個工具原本是獨立 repo，搬進來時完整保留 commit 歷史——在任何子目錄裡
`git log`，都能一路回到該工具的第一個 commit。

## 授權

MIT——整個合集與其中每個工具皆是。
