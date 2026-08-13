# Changelog

## Unreleased — Cleanup ↔ R&D integration

### Added

- 新增 `run-benchmark-driven-rd` sibling skill，與 Cleanup 組成 evaluator／orchestrator 雙層架構。
- 新增 machine contract adapter，驗證 Cleanup JSON schema、status/count、target/mode，並保存 evaluator/config SHA-256。
- 新增 baseline／promotion semantics：baseline 可保存既有 FAIL；promotion 阻擋 FAIL 與 required `NOT_CHECKED`。
- 新增 GitHub／外部系統 canonical-target、最終授權、mobile interaction 與 authoritative postcondition gate。

### Changed

- Cleanup 保持 read-only；原始請求已明確授權 R&D 實作時，不再因 audit 被調用而要求第二次確認。
- Release audit 明確限於本地 repository evidence；遠端發布目標與權限交由 R&D external-change gate。

### Fixed

- 檔案長度介於 warning 與 severe 時改為 `REVIEW`；只有超過 severe 才是 `FAIL`，與函式門檻及文件契約一致。
- Semantic D1 將每個 Python 檔必要的 `__future__` 與 argparse 宣告式樣板降為 LOW，並新增反向 fixture，避免把語法樣板誤判為跨模組重複責任。

### Validation

- Cleanup private/public self-test、Skill validation、sync audit 與 R&D adapter 正反 promotion fixtures 全數通過。
- 新增真 provider regression corpus：實際掃描 R&D skill、阻擋 dependency cycle，並驗證 benchmark provenance mismatch。

## v0.6.0 — 2026-08-13 (dependency calibration)

### Added

- 新增 bare sibling import resolution，支援以 `python scripts/tool.py` 直接執行的常見結構。
- 新增 `architecture.required_dependencies`；已知應存在的內部 edge 若不可觀測，明確回報 FAIL。
- 新增 sibling positive、missing required edge、real root module 與 stdlib negative controls。
- 新增 config-driven `sync_public.py`，公開輸出可 dry-run 並依 allowlist 同步。

### Changed

- Import resolution 先尊重真正 top-level／stdlib module，再做限定 package prefix 的 sibling fallback。
- Self-test 拆成小型責任函式，避免一支超長測試主函式本身形成熱點。
- PASS 數量不再被描述成「架構最優」；稀疏圖與已知缺邊先視為 measurement failure。
- 移除通用 cleanup skill 對作者私人 voice 的預設依賴。

### Validation

- 新 evaluator 已先自測，再 dogfood 掃描 Social Post 私版與公開版。

## v0.5.0 — 2026-08-11 (deterministic audit engine)

### Added

- 新增跨平台 `scripts/audit.py` 與可重用 `audit_core.py`。
- 新增 link、drift、sync 專用檢查器與 dependency-free self-test。
- 統一 PASS／FAIL／NOT_CHECKED，支援 human／JSON report 與 `--strict` CI mode。
- 新增 `audit.config.json` schema、privacy allowlist、自訂 fact assertions 與公開 example。
- Release audit 同時偵測「文件落後 tag」與「文件版本已前進但 tag 尚未建立」。
- Repo root audit 會遞迴檢查 nested `SKILL.md`、相鄰 `agents/openai.yaml` 與 nested references。
- Privacy 支援 literal `tokens` 與明確的 regex `patterns`；無效 regex 回報 FAIL，不再讓 audit crash。
- Markdown duplicate 掃描正確忽略 fenced code 的開、關標記。
- Sync 預設正規化 LF／CRLF 與 UTF-8 BOM；symlink 不會把 audit 範圍帶出目標根目錄。
- 無效 drift assertion regex 回報結構化 FAIL，不再中止整場 audit。
- 新增 Codex `agents/openai.yaml` metadata。

### Changed

- SKILL.md 改為 progressive disclosure，詳細規則下沉到 references。
- 保留 v0.4.1 `cleanup_scan.py` 作為 semantic deep scanner；新引擎不是替代品。
- Windows UTF-8 成為正式執行規格。
- README 同時說明 Codex 與 Claude Code 安裝方式。

## v0.4.1 — 2026-08-09 (外部 review 精準度修正)

v0.4 由外部 review（Claude session）在**沒見過的 repo** 上實測抓出 3 個問題，全數修正。
這版自己就是 D12 教條的案例：**selftest 全綠 ≠ 當工具跑不炸**。

### Fixed
- **cp950 crash**（CRITICAL）— selftest 全綠，真掃第一發就 `UnicodeEncodeError`：
  findings 含簡體字（如 `户`），Windows cp950 stdout 編不出來。
  修法：`__main__` 進場先 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`
- **D10 誤報 ×11** — `.py` 註解裡的規則**引用**（`# M115: ...`）被當成競爭定義。
  引用天生比定義短，重疊率必低 → 對比等於保證誤報。修法：**定義只住在 `.md`**，
  程式碼引用歸 D13 家族的「有沒有落地」問題
- **D7 誤報 ×2** — `[hi](某段中文筆記)` 這種**偽連結記法**被當 CRITICAL 斷鏈。
  修法：target 要長得像路徑（含斜線或副檔名）才進判定

### Added
- selftest 17 → **20 項**：D7 偽連結反向案例、D10 程式碼引用反向案例、
  **cp950 子行程真 corpus 回歸**（把掃描器當子行程跑、fixture 塞簡體字、斷言 exit 0 ——
  以後這類「in-process 測不到的 I/O 層炸裂」不再漏）

**實測**（同一 repo，200 檔 / 39k 行）：CRITICAL **13 → 0**
（13 個裡 11+2 是上述兩類誤報；剩下 1 個真規則漂移是以對齊文案方式修掉，不是靠濾掉）。

## v0.4.0 — 2026-08-07 (可執行掃描器 + 語意層維度)

最大一次改版。從「一份給人抄的 bash checklist」變成「一支能跑的工具」。

### Added
- **`cleanup_scan.py` — 可執行掃描器**（純 Python，跨平台）
  - 機械掃 9 個維度，依 **severity 排序**（CRITICAL / HIGH / MED / LOW）輸出
  - `--selftest`（雙向自測）／`--json`／`--max-files`
  - v0.3 以前全是 bash snippet，作者本人是 Windows 用戶，貼上去跑不動
- **D10 規則內容漂移** — 同命名空間內同一規則 ID 在不同檔案講不同話
  - 起因：作者一條規則（R21）降級後，3 個 skill 仍寫舊版。版本號沒變、連結沒壞，D7/D8 全抓不到
- **D11 孤島 / SoT 缺失** — 該互相引用卻零 cross-reference 的姊妹模組
  - 起因：兩個描述同一件事兩半的 skill，grep 互提 0 次
- **D12 gate 自我認證** — 只有 self-test、沒有真 corpus 回歸的 gate
  - 起因：一支 voice gate self-test 35/35 綠，真樣本一掃 5/5 誤報
  - 附「corpus 是標準 vs corpus 是現況」的區分（量作者自評最弱的維度時不可對齊現況）
- **D13 裁決無機械落地** — 台帳有規則但沒 gate 撐
- **Dogfood 紀律章節** — 本 skill 自己必須先過自己那關
- **門檻誠實聲明** — D4 長度門檻是未校準的經驗值，標明「當提示不當判決」

### Changed
- D1 同一父目錄的重複自動降級為 LOW（樣板家族＝設計如此，不是技術債）
- D2 依副檔名分流：規則編號＝文件層（.md），命名風格＝程式層（.py/.ts/…）
- D7 只掃 `.md`（原本連 `.py` 原始碼裡的字串都當 markdown 連結）
- D8 只認**版本宣告**（`## v1.2.3` / `version:` / `__version__`），不認散文提及
- SKILL.md 380 → 約 250 行，細節下沉到 `cleanup_scan.py` docstring

### Fixed（全部由 dogfood 抓出，皆為「掃描器讀到自己的範例」同一形狀）
- D10 跨模組撞 ID 誤報 15 個 CRITICAL — 規則 ID 是**每個模組各自的命名空間**
- D10 中文未斷詞 — `\w+` 把整串中文當一個 token，兩句不同規則算出 50% 相似 → 改字元 bigram
- D10 吃到 changelog 與輪次標籤 — 改成只認**定義行**不認**談論行**
- D8 把數值常數（`0.30`、`1.0`）當版本號
- D8 把 docstring 裡舉例用的假版本號當成真版本（憑空造出 v9.0.0）
- D2 把掃描器自己的正則字面值當成「有人在用這種命名」

**實測**：作者的 skills repo（166 檔 / 45k 行）CRITICAL **15 → 0**、HIGH **119 → 30**；
自掃自己 CRITICAL 0 / HIGH 0。

## v0.3.1 — 2026-06-10

### Added — Dimension 9e: 個人化設定當預設（源自 M90）
- 掃「作者個資/品牌/個人路徑/個人 keyword map」被當 **default** 烤進 src 程式碼（非 example）
- 掃「函數 default 吃作者個人 map」→ 陌生採用者 match 不到 = 輸出對不上
- 掃「純 CJK keyword 無語言無關 fallback」→ 非中文採用者全 miss
- 真實起源：開源 video-autopilot-kit 的 b-roll matcher 預設吃作者的中文主題表，
  採用者回報「剪出來畫面對不上字幕」。判斷句：**預設行為要對「沒有我資料的陌生人」成立**。

## v0.3 — 2026-06-02

加入 **Dimension 9: 開源/交接文件健檢**（Mode B 第 5 個 dimension）。把專案開源/交接給陌生人前，抓「我熟到忘了講」的隱性洞。

### Added — Mode B Dimension 9: 開源/交接文件健檢

- **9a 主力工具定位顛倒** — 主力工具被講成「選用/optional」、次要工具被列「必需」→ 採用者拿錯工具當主力
- **9b 隱性外部依賴沒標需求** — 核心功能背後的依賴（Computer Use / API key / 特定 app / 系統權限）沒寫進需求 → 採用者跑不起來
- **9c onboarding 無 minimum-viable** — 問卷要全填才給價值，缺「必答 vs 選填」分層或「丟給 AI 訪談你」低門檻路徑
- **9d broken folder ref** — 文件引用不存在的資料夾（承 Dimension 7 + 全域 grep 收尾紀律）

判斷句：「拿掉這個依賴，核心功能還能跑嗎？」不能 → 必標需求。「零基礎陌生人能 5 分鐘跑起來、知道先用哪條路嗎？」不能 → onboarding 沒過。

### Real origin — 自己開源 video-autopilot-kit 時踩到的

開源一套 CapCut 影片自動化 kit 後，採用者回報 3 個洞：
- 需求清單把次要的 ffmpeg 列「必需」、主力 CapCut 列「選用」→ 主次顛倒
- 全篇沒提核心依賴 **Computer Use**（CapCut 沒 API，自動化全靠它操作 GUI）→ 採用者跑不動
- 6 區問卷要全填才能開始 → 採用者嫌久

→ 這 3 個洞固化成 Dimension 9 的自動掃描。**self-demo loop** 再現。

## v0.2 — 2026-05-13

加入 **Mode B Repo Audit**（4 個新 dimension），跑 release ship 前最後 sanity check。

### Added — Mode B: Repo Audit

**Dimension 5: 私公版 sync GAP** — 適用 dual-repo skill（私人版 + 開源版）
- 自動跑 `diff -q` 比對哪些檔案 desync
- 區分 by-design diff（author signature） vs 真實 sync gap

**Dimension 6: Release 一致性** — git tag / gh release / CHANGELOG / README 對齊
- 抓「有 tag 但沒 release」「有 release 但沒 tag」
- 抓 CHANGELOG 缺最新版 entry
- 抓 README 缺最新版提及

**Dimension 7: Cross-link 完整性**
- 內部 .md ref 是否 broken
- Cross-repo URL 是否還活著

**Dimension 8: 版本標記漂移**
- 多檔案 version mention 不一致
- 例：README 提 v0.7.2 但 latest tag 是 v0.7.3 → 推 release 沒更 README

### Changed — Mode A 重新分組

原 v0.1 的 4 個 dimension 維持不變，但歸進「Mode A: Codebase Cleanup」，方便跟 Mode B 區隔。

### Real demo — 自己 audit 姐妹 repo 抓到的

跑 social-post v0.7.3 audit：
- Dimension 5: ✅ 私公版同步 OK（除了 author signature by-design）
- Dimension 6: ⚠️ CHANGELOG 缺 v0.7.3 entry（剛 release 但 doc 沒更）
- Dimension 7: ✅ 13 個外部 link 全 live
- Dimension 8: ⚠️ README + SKILL.md 都缺 v0.7.3 提及

→ cleanup-helper v0.2 立刻抓到自己姐妹 repo 的 doc drift。**self-demo loop**。

### Added — 觸發詞庫擴充

新增 audit 相關觸發詞：
- 「audit 我的 repo」
- 「check release 一致性」
- 「私公版 diff」
- 「版本對齊」
- 「release ship 前盤點」

## v0.1 — 2026-05-13

初版發布。

### Added

- **三階段工作流**：掃描（Phase 1） → 報告（Phase 2） → 建議（Phase 3）
- **4 個檢查 dimension**：
  1. 重複內容（DRY 違反）
  2. 命名不一致
  3. 可模組化區塊
  4. 過長檔案 / 函數
- **真實 case study**：用本 skill 掃描姐妹 repo `social-post skill v0.7.1`，產出 2,100 行 / 11 檔的完整 cleanup report
- **安全閘**：永遠先報告 + 等使用者確認，絕不自動修改檔案
- **觸發詞庫**：「清理 code」「找重複」「重構」「模組化」「review codebase」「掃 prompt」「我這 skill 寫好亂」「prompt 太長拆一下」

### Designed for

- prompt / SKILL.md / markdown 型 codebase（主要設計目標）
- 一般程式碼（py / ts / js）的 Phase 1-2 也可用

### 起源故事

開發 `social-post skill` 兩週累積到 2,100 行後發現：
- 「R[N]」（SKILL.md）vs「規則 [N]」（case_studies.md）= **同源系統兩套命名**
- 「鐵粉」65 次 / 「Day 1」70 次 / 「F6b」56 次散落 = 慢性 DRY 債
- case_studies.md 604 行 / formulas.md 505 行 = 接近 800 警告線

這些是 ESLint 看不到的 **semantic 技術債**。寫個 skill 自動掃才不會變一坨亂。
