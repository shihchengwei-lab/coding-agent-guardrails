# Slime Coding

[![CI](https://github.com/shihchengwei-lab/slime-coding/actions/workflows/ci.yml/badge.svg)](https://github.com/shihchengwei-lab/slime-coding/actions/workflows/ci.yml)

![Slime Coding — grow both frontiers, commit only the minimal corridor](assets/slime-coding.png)

*[English](#english) · [中文](#中文)*

## English

**Stop agentic AI from over-building.** Instead of generating code straight from
a prompt, Slime Coding makes the agent grow two frontiers — what the requirement
needs, and what the repo already offers — and only edit the **minimal corridor
where they meet**. Rejected designs are pruned and recorded so they don't come
back. It's wired into Claude Code as hooks, so the discipline is enforced, not
just requested.

### Why hooks

A line in `CLAUDE.md` ("don't over-engineer") is a **request** — the model can
skip it. A **hook** runs every time. Slime Coding puts the teeth only on
unambiguous git facts:

- **No edit without a corridor.** Define the minimal change in
  `.slime/corridor.md` first, or `Edit`/`Write` is denied.
- **A new dependency is blocked at Stop** until you keep-or-remove it.
- **Pruned paths persist** in `.slime/PRUNED.md` and are re-injected next
  session, so the loop can't revive a rejected design.
- **Scope creep is reported** (touched / new files, out-of-corridor edits) —
  shown, never falsely blocked.

### Quick start

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

### Status — experimental, honestly

Not a validated framework; no "proven / production-ready" claims. What's known
so far (data in [`reports/`](reports/), plan in
[`docs/VALIDATION_PLAN.md`](docs/VALIDATION_PLAN.md)):

- **Mechanism: verified.** Gates fire on the git facts they claim, bootstrap
  doesn't deadlock, install is idempotent — `tests/test.sh` (19 checks) + CI.
- **Effect: a narrow, reproducible signal.** In small Python/Node A·B runs, when
  a prompt invites speculative extensibility ("we'll add more formats later"),
  the baseline builds a registry for the one required variant (13/13) while the
  Slime discipline suppresses it (1/13) — roughly half the code at equal
  behavior. **With no such invitation, there's no difference.** Other
  over-implementation baits (refactoring, gold-plating) didn't reproduce.
- **The dependency gate is a backstop**, not an extra win on a compliant agent.

---

## 中文

**約束 agentic AI 的過度實作。** 不從 prompt 直接生成 code，而是先讓需求與現有
repo 各自長出 frontier，只在兩者交會的**最小走廊（corridor）**動手；沒 evidence
的路徑剪掉並記錄，下輪不再復活。整套綁到 Claude Code 的 hook 上——是**強制**，不是
請求。

### 為什麼用 hook

寫在 `CLAUDE.md` 的「不要過度實作」是**請求**，模型可以略過；**hook** 每次都跑。
Slime Coding 的牙齒只長在無歧義的 git 事實上：

- **沒走廊不准改。** 先把最小修改寫進 `.slime/corridor.md`，否則 `Edit`/`Write`
  被擋。
- **新增依賴在 Stop 被擋**，要你保留或移除才放行。
- **剪枝跨輪存活**：寫進 `.slime/PRUNED.md`，下個 session 自動注入，loop 復活不了
  已否決的設計。
- **scope creep 會回報**（touched / new files、走廊外修改）——顯示，但不誤擋。

### 快速開始

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

### 驗證狀態——誠實版

這是**實驗性**工作流，不是已驗證的 framework，不用「proven / production-ready」。
目前已知（數據在 [`reports/`](reports/)、計畫在
[`docs/VALIDATION_PLAN.md`](docs/VALIDATION_PLAN.md)）：

- **機制層：已驗證。** 閘門在宣稱的 git 事實上會觸發、bootstrap 不死鎖、install
  idempotent——`tests/test.sh`（19 項）+ CI。
- **效果層：窄而可重現的訊號。** 小 Python/Node A·B 對照下，當 prompt 明示邀請
  推測性擴展（「之後還會加更多格式」），baseline 會替「只需要一種」的變體蓋
  registry（13/13），Slime 紀律擋掉（1/13），同行為下程式約砍半。**不給這個邀請
  就沒有差異。** 其他過度實作誘餌（重構、gold-plating）沒有重現。
- **依賴閘門是 backstop**，對守規矩的 agent 不額外加分。

## License

MIT — see [`LICENSE`](LICENSE). Changes in [`CHANGELOG.md`](CHANGELOG.md).
