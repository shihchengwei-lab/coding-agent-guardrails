# Slime Coding

[![CI](https://github.com/shihchengwei-lab/slime-coding/actions/workflows/ci.yml/badge.svg)](https://github.com/shihchengwei-lab/slime-coding/actions/workflows/ci.yml)

**Slime Coding — 讓最聰明的 AI，跟最沒腦的黏菌學會克制。**

![Slime Coding — Think more. Drift less.](assets/slime-coding.png)

每天用 AI 寫 code 的人都知道：現在的問題通常不是 AI 做不出來，而是它太容易把任務往外延伸。

它會加一層你沒要求的抽象、碰幾個本來不用碰的檔案、引入新套件、改掉既有資料流，甚至引用一個 repo 裡根本不存在的函數。功能最後也許能跑，但 diff 會多出一堆你沒有打算維護的東西。

Slime Coding 管的是這件事：**最小語義位移**。

不是最小 diff，也不是最少行數。它在意的是：只改這次需求必須改的行為，不順手移動既有架構、命名、API、資料流和責任邊界。

## 它做什麼？

Slime Coding 不是再寫一段「請不要過度實作」給 AI 看。那種文字只是提醒，AI 忙起來會忘。

它把幾個容易失控的點接成自動關卡：

- **動手前先框範圍**：AI 要先寫出這次要碰哪些檔案、要完成什麼、哪些事不做。沒框好就不能改專案程式碼。
- **範圍外的修改會被擋**：如果 AI 順手改了不在範圍內的程式碼，收工時會被擋下來。
- **新增套件會被擋**：AI 不能默默多加套件。要嘛說清楚為什麼留，要嘛拿掉。
- **引用不存在的接點會被擋**：可選。你可以接型別檢查或語法檢查，讓 AI 不能靠想像中的 helper / class / API 收工。
- **紅燈不能假裝完成**：如果你設定了測試指令，測試紅燈時 AI 不能直接收工。它要修綠，或把放棄的路記下來，避免下輪重走。
- **commit message 會留下證據**：commit 時自動補上這次範圍、碰了哪些檔案、有沒有走廊外修改、有沒有新套件、怎麼驗證。

簡單說就是：

> 多想一點，少偏離一點。

## 什麼時候有用？

適合：

- 你已經每天用 Claude Code / Codex / 其他 AI coding 工具改 repo。
- 你的 repo 已經有架構、命名、helper、測試和約定。
- 你在意 AI 不要把一個小需求擴成一串旁支。
- 你常遇到「功能有做完，但 diff 看起來很不對」。

不太適合：

- 一次性試作品。
- 你就是想讓 AI 大幅重構。
- 專案沒有測試、沒有型別檢查，也不在意檔案邊界。

## 怎麼用？

每個要套 Slime Coding 的專案，各跑一次：

```bash
git clone <這個 repo> ~/slime-coding
cd /你的專案
~/slime-coding/install.sh .
```

安裝會做幾件事：

- 把 Claude 的自動關卡接進 `.claude/settings.json`。
- 裝 `/slime-corridor` 和 `/slime-prune` 指令。
- 建立 `.slime/corridor.md` 和 `.slime/PRUNED.md` 範本。
- 接上 Git commit hook，讓 commit message 自動帶證據。

需要 `python3` 和 `git`。安裝可以重跑，會備份既有設定。

最後手動一步：把 [`templates/CLAUDE.slime.md`](templates/CLAUDE.slime.md) 的內容貼進你專案的 `CLAUDE.md`，讓 AI 知道這套規則怎麼用。

## Benchmark 怎麼看？

這不是「AI coding 已被解決」的證明，只是一個時間點快照：在同一批任務上，裝 Slime Coding 之後，AI 有沒有更少漂移。

2026-06-29，用 Ponytail-derived task pool 跑 Claude Haiku：

- 19 題
- `baseline` / `ponytail` / `slime-coding` 三組
- 每題每組 4 次
- 共 228 個有效樣本
- 429 額度失敗與跑太久中斷的樣本已重跑
- `slime-coding` 使用目前預設的嚴格版本：範圍外程式碼修改會被擋

| 組別 | 通過率 | touched files | 總 LOC | vs baseline LOC | 平均 cost | 平均 tokens | 平均時間 |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 69/76 = 90.8% | 115 | 5744 | baseline | $0.0897 | 331k | 49.8s |
| ponytail | 72/76 = 94.7% | 147 | 5055 | -12.0% | $0.1047 | 299k | 55.6s |
| slime-coding | 76/76 = 100.0% | 107 | 4351 | -24.3% | $0.1223 | 478k | 76.6s |

直覺讀法：

- Slime Coding 在這批任務通過率最高。
- 它碰的檔案最少。
- 它產生的總 LOC 最少。
- 代價是 token、時間、cost 都比較高。

所以它不是省錢工具，也不是加速工具。它比較像一個保守的防護欄：多花一點思考成本，換比較小的改動面。

完整資料在 [`benchmark/`](benchmark/)。

## 限制

- 它不是安全沙盒。真正的安全邊界還是權限、sandbox、CI、測試和人工 review。
- 它不能判斷所有設計好壞，只能擋幾個明確事實：範圍外檔案、新套件、紅燈收工、型別檢查失敗。
- 沒有測試或型別檢查的 repo，效果會打折。
- 它會增加流程成本。benchmark 也顯示它更耗 token、時間和錢。

如果你要的是「便宜、快、能跑就好」，這不是它的方向。

如果你要的是「AI 可以寫，但不要把每個小需求都擴成一輪大改動」，這就是它想解的問題。

## 更多細節

- 概念說明：[`docs/CONCEPT.md`](docs/CONCEPT.md)
- 機制設計：[`docs/DESIGN.md`](docs/DESIGN.md)
- benchmark 原始資料：[`benchmark/`](benchmark/)
- 變更紀錄：[`CHANGELOG.md`](CHANGELOG.md)

## License

MIT — 見 [`LICENSE`](LICENSE)。
