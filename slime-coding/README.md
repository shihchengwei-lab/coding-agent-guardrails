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

還在實驗階段。下面是目前測到的事實：

- **關卡本身會動**：該擋的地方會擋、安裝不會壞、可以重跑——29 個自動測試 + CI 都過。
- **效果有訊號、但很窄**。在小型 Python/Node 對照測試裡，當題目暗示「之後還會加更多」（例如「之後可能要支援其他格式」），沒用 Slime 的版本會蓋一個大架構（13/13），用了 Slime 的版本不會（1/13）——同功能、程式剩一半。**沒有那個暗示，看不出差異。** 其他容易誘發過度實作的場景（沒事亂重構、為了好看堆抽象）目前測不出差異。
- **關卡是安全網，不是放大鏡**。最近的同條件對照（[`reports/2026-06-21-bvc.md`](reports/2026-06-21-bvc.md)）顯示：真正讓 AI 守規矩的，是寫在 prompt 裡的紀律。關卡負責接住「紀律失靈」的那幾種情況：加進新套件、引用不存在的函數或變數。
- **跨 model + 更難 fixture 上 Slime 沒抑制 garbage、反而在 Sonnet 上加代價**。06-22 補了一個含 architectural room 的新 fixture（[`reports/2026-06-22-bench.md`](reports/2026-06-22-bench.md)）：multi-module Python 包、有 `readers/` 子目錄暗示 plugin pattern。跑 Haiku / Sonnet / Opus × baseline / hooked × N=3 = 18 cell。事實：
  - **Slime 沒抑制 dict-form registry**。Opus baseline 1/3 蓋 `READERS = {...}` dispatch dict、hooked **2/3**——hooked 比 baseline 更多。Sonnet/Haiku 兩條件都不蓋（但 Sonnet hooked 2/3 沒寫到 code、無從觀察）。
  - **Sonnet 在 hooked 條件 2/3 cell 空 implementation**（baseline 0/3）。跟 cli-notes 上同方向訊號（cli-notes Sonnet hooked 2/9）。
  - **沒任何 model 蓋 class-ABC garbage**（M1/M3/M5 全 18 cell 全 0）——score.py 設計的 class-form rubric 沒被觸發、garbage 都以 dict-form 出現。
  - 結論：在這 fixture 上、**Slime 沒幫任何 model 寫更少 garbage、反而對 Sonnet 加 wall-clock 代價、Opus 還可能蓋更多 dispatch dict**。N=3 個別 cell 是 noise 級、方向是 load-bearing 訊號。
  - hooks 的另一面用處（接住偷加套件、引用不存在的東西）在這 matrix 同樣沒觸發、不在這個結論的射程內。

詳細數據在 [`reports/`](reports/)、後續驗證計畫在 [`docs/VALIDATION_PLAN.md`](docs/VALIDATION_PLAN.md)。

## License

MIT — 見 [`LICENSE`](LICENSE)。變更紀錄在 [`CHANGELOG.md`](CHANGELOG.md)。
