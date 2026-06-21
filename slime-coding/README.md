# Slime Coding

[![CI](https://github.com/shihchengwei-lab/slime-coding/actions/workflows/ci.yml/badge.svg)](https://github.com/shihchengwei-lab/slime-coding/actions/workflows/ci.yml)

![Slime Coding — grow both frontiers, commit only the minimal corridor](assets/slime-coding.png)

*[English](#english) · [中文](#中文)*

## English

A slime mould pushes tendrils out from both ends of a maze. Tubes that find
food thicken; tubes that find nothing wither. What's left is the path between
two points — not designed, just *what survived*.

**Slime Coding** does this to AI coding. The agent grows two frontiers — what
the requirement actually needs, and what the repo already offers — and only
edits the **minimal corridor where they meet**. Branches without evidence
wither. Rejected designs are pruned and recorded so they don't grow back next
round.

→ The metaphor in full (Food Points, frontiers, corridor, pruned paths, stop
condition): **[`docs/CONCEPT.md`](docs/CONCEPT.md)**.

This repo wires the discipline into Claude Code as **hooks**, so it's
enforced on git facts, not just requested in a prompt.

### Why hooks

A line in `CLAUDE.md` ("don't over-engineer") is a **request** — the model can
skip it. A **hook** runs every time. Slime Coding puts the teeth only on
unambiguous git facts:

- **No edit without a corridor.** Define the minimal change in
  `.slime/corridor.md` first, or `Edit`/`Write` is denied.
- **A new dependency is blocked at Stop** until you keep-or-remove it.
- **Hallucinated references are caught** (opt-in): a type checker
  (`dart analyze`, `tsc`, …) runs at Stop and blocks if the patch points at a
  symbol that doesn't resolve — i.e. an invented attachment point.
- **Pruned paths persist** in `.slime/PRUNED.md` and are re-injected next
  session, so the loop can't revive a rejected design.
- **Scope creep is reported** (touched / new files, out-of-corridor edits) —
  shown, never falsely blocked.

### Quick start

Slime Coding is **per-project** — opt in by running `install.sh` against each
repo you want it on (state lives in that repo's `.slime/`).

Clone anywhere, then run `install.sh` against your project (idempotent; backs up
`settings.json`):

```bash
git clone <this-repo> ~/slime-coding
cd /path/to/your/project
~/slime-coding/install.sh .
```

It wires the hooks into `.claude/settings.json` and links the `slime-navigate`
skill + `/slime-corridor` and `/slime-prune` commands. One manual step: paste
`templates/CLAUDE.slime.md` into your `CLAUDE.md`. Needs `python3` + `git`.

→ Mechanics, config, layout: **[`docs/DESIGN.md`](docs/DESIGN.md)** ·
the idea & manual method: **[`docs/CONCEPT.md`](docs/CONCEPT.md)**.

### Pairing with coding-guidelines (optional)

If you also use
[coding-guidelines](https://github.com/shihchengwei-lab/coding-guidelines) —
the two-prompt + Stop-self-check user-level companion — pass `--with-cg` to
install both in one shot:

```bash
~/slime-coding/install.sh /path/to/your/project --with-cg ~/coding-guidelines
```

This copies its three scripts into `~/.claude/scripts/` and merges its hook
entries into `~/.claude/settings.json` (backup kept, idempotent). The two
repos stay independent — cg works standalone without the flag, and slime
works without cg.

### Status — experimental, honestly

Not a validated framework; no "proven / production-ready" claims. What's known
so far (data in [`reports/`](reports/), plan in
[`docs/VALIDATION_PLAN.md`](docs/VALIDATION_PLAN.md)):

- **Mechanism: verified.** Gates fire on the git facts they claim, bootstrap
  doesn't deadlock, install is idempotent — `tests/test.sh` (25 checks) + CI.
- **Effect: a narrow, reproducible signal.** In small Python/Node A·B runs, when
  a prompt invites speculative extensibility ("we'll add more formats later"),
  the baseline builds a registry for the one required variant (13/13) while the
  Slime discipline suppresses it (1/13) — roughly half the code at equal
  behavior. **With no such invitation, there's no difference.** Other
  over-implementation baits (refactoring, gold-plating) didn't reproduce.
- **The gates are a backstop, not a multiplier.** An automated, same-modality
  B-vs-C benchmark ([`reports/2026-06-21-bvc.md`](reports/2026-06-21-bvc.md))
  finds the hooked gates add no measurable reduction beyond the prompt-only
  discipline on the abstraction axis (N=3): the prose carries the effect, and the
  gates catch the non-compliant case (a new dependency, a hallucinated reference)
  the prose can't guarantee away.

---

## 中文

黏菌在迷宮裡會從兩端同時伸觸鬚：接到食物的管變粗，沒接到的萎縮。剩下的就是兩點
之間的路——沒人「設計」，只是「活下來的」。

**Slime Coding** 把這個套在 AI 寫程式上。Agent 從需求跟現有 repo 各長出
frontier，只在兩者交會的**最小走廊（corridor）**動手；沒 evidence 的分支萎縮，
被剪掉的路徑記下來，下一輪不會悄悄復活。

→ 完整比喻（Food Points、frontier、走廊、剪枝路徑、停止條件）：
**[`docs/CONCEPT.md`](docs/CONCEPT.md)**。

這個 repo 把這套紀律接進 Claude Code 的 **hook**，用 git 事實強制執行，而不是
寫在 prompt 裡請求。

### 為什麼用 hook

寫在 `CLAUDE.md` 的「不要過度實作」是**請求**，模型可以略過；**hook** 每次都跑。
Slime Coding 的牙齒只長在無歧義的 git 事實上：

- **沒走廊不准改。** 先把最小修改寫進 `.slime/corridor.md`，否則 `Edit`/`Write`
  被擋。
- **新增依賴在 Stop 被擋**，要你保留或移除才放行。
- **虛構的 reference 會被擋**（選用）：Stop 時跑 type checker（`dart analyze`、
  `tsc`…），patch 指到 resolve 不出來的符號（憑空捏的接點）就擋。
- **剪枝跨輪存活**：寫進 `.slime/PRUNED.md`，下個 session 自動注入，loop 復活不了
  已否決的設計。
- **scope creep 會回報**（touched / new files、走廊外修改）——顯示，但不誤擋。

### 快速開始

Slime Coding 是 **per-project** 工具——每個你想用它的 repo 都要各自跑一次
`install.sh`（走廊 / PRUNED 狀態存在該 repo 的 `.slime/`）。

clone 到任何位置，對你的專案跑一次 `install.sh`（可重跑、會備份 `settings.json`）：

```bash
git clone <this-repo> ~/slime-coding
cd /path/to/your/project
~/slime-coding/install.sh .
```

它把 hook 接進 `.claude/settings.json`，並把 `slime-navigate` skill 與
`/slime-corridor`、`/slime-prune` 連進去。手動一步：把
`templates/CLAUDE.slime.md` 貼進你的 `CLAUDE.md`。需要 `python3` + `git`。

→ 機制、設定、結構：**[`docs/DESIGN.md`](docs/DESIGN.md)**；
理念與手動流程：**[`docs/CONCEPT.md`](docs/CONCEPT.md)**。

### 搭配 coding-guidelines（選用）

若同時使用
[coding-guidelines](https://github.com/shihchengwei-lab/coding-guidelines)
（兩條 prompt 紀律 + Stop 自查清單,user-level 配套），加 `--with-cg` 一次裝完：

```bash
~/slime-coding/install.sh /path/to/your/project --with-cg ~/coding-guidelines
```

它會把 cg 的三個 script 複製到 `~/.claude/scripts/`，並 merge cg 的 hook 進
`~/.claude/settings.json`（保留 backup、idempotent）。兩個 repo 維持獨立 ——
不加 flag 時 cg 仍可單獨使用,slime 也不依賴 cg。

### 驗證狀態——誠實版

這是**實驗性**工作流，不是已驗證的 framework，不用「proven / production-ready」。
目前已知（數據在 [`reports/`](reports/)、計畫在
[`docs/VALIDATION_PLAN.md`](docs/VALIDATION_PLAN.md)）：

- **機制層：已驗證。** 閘門在宣稱的 git 事實上會觸發、bootstrap 不死鎖、install
  idempotent——`tests/test.sh`（25 項）+ CI。
- **效果層：窄而可重現的訊號。** 小 Python/Node A·B 對照下，當 prompt 明示邀請
  推測性擴展（「之後還會加更多格式」），baseline 會替「只需要一種」的變體蓋
  registry（13/13），Slime 紀律擋掉（1/13），同行為下程式約砍半。**不給這個邀請
  就沒有差異。** 其他過度實作誘餌（重構、gold-plating）沒有重現。
- **閘門是 backstop，不是 multiplier。** 自動化、同模態的 B-vs-C 對照
  （[`reports/2026-06-21-bvc.md`](reports/2026-06-21-bvc.md)）顯示：在抽象軸上，
  hook 閘門相對 prompt-only 紀律沒有可測得的額外削減（N=3）——效果由 prose 扛，
  閘門負責接住 prose 無法保證的不守規案例（新依賴、虛構引用）。

## License

MIT — see [`LICENSE`](LICENSE). Changes in [`CHANGELOG.md`](CHANGELOG.md).
