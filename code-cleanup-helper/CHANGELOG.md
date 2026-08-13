# Changelog — code-cleanup-helper

## v0.6.0 — 2026-08-13 (dependency calibration)

- Bare sibling imports、real root imports 與 stdlib imports 分流解析。
- `required_dependencies` 讓已知應存在的 edge 成為可執行 gate。
- 新增正／負依賴 fixtures、拆分 self-test 與 public sync helper。
- 稀疏空圖不再被當成架構最優；已知缺邊先列 measurement failure。

## v0.4.1 — 2026-08-13 (package import resolution calibration)

- Fixed a false cycle where unresolved standard-library imports inside a package were collapsed to that package's `__init__.py` module.
- Sibling fallback now succeeds only when the candidate resolves to an actual module below the current package.
- Added a regression fixture covering a facade/submodule package whose implementation imports `json`, `datetime` and `pathlib`.

## v0.4.0 — 2026-08-11 (executable audit engine)

- 新增跨平台 `scripts/audit.py` 與可重用 `audit_core.py`
- 新增 link、drift、sync 專用檢查器與 dependency-free self-test
- 統一 PASS／FAIL／NOT_CHECKED，支援 human／JSON report
- 新增 `audit.config.json` schema、privacy allowlist 與自訂 fact assertions
- SKILL.md 改為 progressive disclosure，詳細規則移到 references
- Windows UTF-8 成為正式執行規格

## v0.3.1 — 2026-05-19 (hao-voice canonical path)

Per ADR-002（第二場 panel Q3 共識）。

### Changed
- `SKILL.md` hao-voice path 改首選 `~/.claude/skills/hao-voice/hao-voice.md`（canonical）+ fallback 舊 30day-launch path
- 「Phase P4 future」字眼移除 — P4 已 ship

### Companion skill 同步
- 30day-launch v0.6.2 + genius-advisor v0.7.2

---

## v0.3 — 2026-05-19 (hao-voice integration)

P1 of phased B→C omni-genius arch（per 30day-launch repo ADR-001）。

### Added
- `SKILL.md` 新「🔑 Session 啟動」段 — 偵測 `D:/圓桌會議/repo-30day-launch/30day-launch/references/for-me/hao-voice.md` 並 load

### 行為改變
- Audit report output 自動套用 hao-voice：表格化、anti-pattern 避免、結構偏好、結尾必有 next action
- 衝突仲裁：R-rules / safety > hao-voice > generic default

### Companion skill 同步
- 30day-launch v0.6.1 + genius-advisor v0.7.1

### Future (Phase P4)
- hao-voice 預計 refactor 到 user-level skill (`~/.claude/skills/hao-voice/`)

---

## v0.2 — earlier (Mode B Repo Audit)

新增 Mode B — Repo Audit（4 dimensions: 私公版 sync / release 一致性 / cross-link / 版本標記漂移）。

## v0.1 — base (Mode A Codebase Cleanup)

Mode A — Codebase Cleanup（4 dimensions: DRY / 命名 / 模組 / 過長）。
