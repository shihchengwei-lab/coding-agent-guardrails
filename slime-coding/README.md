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

**機制層**：hook 在它宣稱要觸發的 git 事實上會觸發（沒走廊就擋編輯、新增依賴就擋收工、type checker 紅燈就擋收工），安裝可重跑、不壞既有設定。自動測試與 CI 用來守住這一層。

**效果層（裝了 Slime，AI 真的會少寫 garbage 嗎？）**：現在有一組可公開、但只算方向性的 benchmark。

2026-06-29，用 Ponytail-derived task pool 跑 Claude Haiku：19 題，`baseline` / `ponytail` / `slime-coding` 三組，每題每組 4 次，共 228 個有效樣本。429 額度失敗與 timeout 樣本已重跑；Slime 的 `cache` safety 失敗保留，因為那是真失敗，不是基礎設施問題。

| 組別 | 通過率 | 總 LOC | vs baseline LOC | 平均 cost | 平均 tokens | 平均時間 |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 69/76 = 90.8% | 5744 | baseline | $0.0897 | 331k | 49.8s |
| ponytail | 72/76 = 94.7% | 5055 | -12.0% | $0.1047 | 299k | 55.6s |
| slime-coding | 74/76 = 97.4% | 4544 | -20.9% | $0.1159 | 465k | 69.9s |

讀法很簡單：Slime 在這組任務提高通過率、縮小總 diff；代價是更多 token、更多錢、更久時間，並且有 1 次 safety regression。完整資料在 [`benchmark/`](benchmark/)。

## License

MIT — 見 [`LICENSE`](LICENSE)。變更紀錄在 [`CHANGELOG.md`](CHANGELOG.md)。
