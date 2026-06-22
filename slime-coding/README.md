# Slime Coding

[![CI](https://github.com/shihchengwei-lab/slime-coding/actions/workflows/ci.yml/badge.svg)](https://github.com/shihchengwei-lab/slime-coding/actions/workflows/ci.yml)

![Slime Coding — grow both frontiers, commit only the minimal corridor](assets/slime-coding.png)

黏菌走迷宮，會從兩頭同時伸觸鬚出去找食物。碰到食物的觸鬚變粗、沒碰到的萎縮。最後留下的，就是兩點之間活下來的那條路——沒人「設計」它。

**Slime Coding** 把這條路長出來的方式，搬到 AI 寫程式上。

想像你叫 AI「加一個登入功能」。常見的版本：它順手蓋了一個你沒要求的設定系統、為「之後可能會用到」鋪了一層抽象、改了五個檔——但你只想要登入。

Slime Coding 讓 AI 也從兩頭伸觸鬚：

- 一頭往**這次的需求**長——只從「加登入功能」這句話往下挖，需要什麼。
- 另一頭往**現有的 code** 長——從專案已經有的東西往上找，哪裡可以接上。

兩頭碰上才動手；碰不上的方向被剪掉、記到一個檔案。下次 AI 一開始就看到上次否決過哪些方向。

→ 完整比喻：[`docs/CONCEPT.md`](docs/CONCEPT.md)

## 怎麼做到？

寫在 `CLAUDE.md` 的「不要過度實作」是**請求**——AI 可以略過。Slime Coding 把它變成**自動關卡**：AI 每次想動 code 都會跑、跳不過。關卡只看明確的事實，不靠感覺判斷：

- **AI 動手前，自己得先寫清楚「這次要碰哪幾個檔、目標是什麼」**。它寫好一個小檔（30 秒），你確認方向對，它才開始改。沒寫就連改一行都被自己的關卡擋住。
  - 例外：`.gitignore`、`LICENSE` 這類跟程式邏輯無關的設定檔不用寫範圍就能改。

- **AI 加進新套件會被擋**。要嘛它說明「為什麼要留」、要嘛拿掉，才能收工。

- **AI 引用一個不存在的函數或變數會被擋**（選用）。它有時候會用一個聽起來合理、但 repo 裡根本沒有的名字——關卡會跑一輪語法檢查、把這種「憑空捏的接點」拒收。

- **被否決的方向留到下次**。下個 session 一開始 AI 就看到上次否決過哪些方向。

- **多寫了多少、超出範圍的檔，會列出來**（只列、不擋）。不誤擋合理的擴大，但讓你看到。

→ 機制細節：[`docs/DESIGN.md`](docs/DESIGN.md)

## 怎麼用？

每個你想用它的專案，各跑一次安裝：

```bash
git clone <這個 repo> ~/slime-coding
cd /你的專案
~/slime-coding/install.sh .
```

它會把關卡接上、把指令連好。需要 `python3` 跟 `git`。安裝會備份你原本的設定、可以重跑、不會壞。

最後手動一步：把 `templates/CLAUDE.slime.md` 的內容貼進你專案的 `CLAUDE.md`，這樣 AI 才知道紀律寫在哪。

### 搭配 coding-guidelines（選用）

如果你也用 [coding-guidelines](https://github.com/shihchengwei-lab/coding-guidelines)（另一套 prompt 紀律），安裝時加 `--with-cg` 一次裝完兩個：

```bash
~/slime-coding/install.sh /你的專案 --with-cg ~/coding-guidelines
```

兩套各自獨立，分開用也行。

## 目前驗證到哪？

還在實驗階段。

**關卡本身會動**：該擋的地方會擋、安裝不會壞、可以重跑——29 個自動測試 + CI 都過。

**Slime 對「AI 寫過多 code」這目標，現有證據答不出來**。

06-21 跟 06-22 跑的那 ~90 個對照 cell 都是 sandbox fixture（115 行的 cli-notes、115 行的 csv-tsv-pipeline）、單檔加一個 subcommand 等級的任務。在這個規模上沒有架構決定空間、AI 自然不會蓋 garbage——不論裝不裝 Slime。當這幾份報告原本要把這描述成「Slime 沒效果」時、結論其實是「測試沒給 Slime 機會發揮」，不是「Slime 不行」。要真的回答這條問題，需要的不是更大的 sandbox，而是真實生產任務上的 instrumentation（大 codebase、模糊規格、AI 自然選擇怎麼做、不靠合成 bait）——超出 sandbox benchmark 能做的範圍。

**hooks 設計的另一面用處——接住「AI 偷加套件」「AI 引用不存在的函數或變數」「跨 session 把上次否決的設計復活」**——06-18 的 mechanism verification 測過這幾條 gate 在 git fact 上**會 trigger**、但「真實任務裡這些 failure mode 多常出現、Slime 接住多少」沒 effect-size 證據。這幾個 gate 在 sandbox benchmark 也沒被 agents 誘發、所以同樣沒進入結論射程。

**讀者該怎麼用這結果**：
- 想靠 Slime 抑制 AI 過度實作——目前沒任何證據支持也沒任何證據反對。**真正抑制 garbage 的核心機制是寫進 `CLAUDE.md` 的紀律 prose**（06-18 extensibility 測到的訊號是 prose 的、不是 hook 的）；Slime 可以幫你貼那段 prose、但 prose 本身不需要 hook。
- 想接住「偷加套件 / 寫憑空捏的 reference / 帶紅燈收工」這幾種 git 事實——hook 是設計來幹這個的，機制有測過、effect size 沒測過。

詳細數據：[`reports/2026-06-21-bvc.md`](reports/2026-06-21-bvc.md)（B vs C, Opus）、[`reports/2026-06-22-model-class.md`](reports/2026-06-22-model-class.md)（跨 model + baseline）、[`reports/2026-06-22-bench.md`](reports/2026-06-22-bench.md)（含 architectural room 的 fixture）。後續驗證計畫：[`docs/VALIDATION_PLAN.md`](docs/VALIDATION_PLAN.md)。

## License

MIT — 見 [`LICENSE`](LICENSE)。變更紀錄在 [`CHANGELOG.md`](CHANGELOG.md)。
