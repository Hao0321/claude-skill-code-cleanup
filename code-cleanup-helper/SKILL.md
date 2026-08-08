---
name: code-cleanup-helper
description: 技術債掃描 + repo audit。v0.4 起附**可執行掃描器** `cleanup_scan.py`（跨平台 Python，不需 bash），機械掃 9 類、人工判 4 類，依 severity 排序。Mode A 掃 codebase / SKILL.md / prompt 找重複/命名/模組/過長；Mode B 跑 repo audit 檢查私公版 sync / release 一致性 / cross-link / 版本漂移 / 開源交接；Mode C（v0.4 新增）掃**語意層**技術債 — 規則內容漂移、孤島模組、gate 自我認證、裁決無機械落地。觸發詞：「清理 code」「找重複」「重構」「模組化」「review codebase」「掃 prompt」「我這 skill 寫好亂」「prompt 太長拆一下」「跑大專案怕亂」「audit 我的 repo」「check release 一致性」「私公版 diff」「版本對齊」「release ship 前盤點」「規則有沒有漂掉」「gate 可不可信」時觸發。
---

<!--
  code-cleanup-helper skill — Created by 駱君昊 (Hao)
  Repo: https://github.com/Hao0321/claude-skill-code-cleanup
  Companion skill to: https://github.com/Hao0321/claude-skill-social-post
  License: MIT — 保留此標註即可修改、使用、商用
-->

# code-cleanup-helper

## ⚡ 先跑掃描器，再讀本文

v0.4 把「機械查得出來的」全部變成可執行。**不要再手抄 bash snippet。**

```bash
python ~/.claude/skills/code-cleanup-helper/cleanup_scan.py <目標資料夾>
```

```bash
python ~/.claude/skills/code-cleanup-helper/cleanup_scan.py --selftest
```

- 純 Python，Windows / macOS / Linux 都能跑（v0.3 以前全是 bash，在 Windows 貼上去跑不動）
- 依 **severity 排序**輸出（CRITICAL → HIGH → MED → LOW），不是依維度編號 —— 「先修哪個」比「有幾類問題」重要
- `--json out.json` 出機器版；`--max-files N` 控規模

**掃描器只覆蓋 9/13 個維度。** 判斷題（D3 模組化 / D5 私公版 / D6 release / D9 交接健檢）仍要人工跑，見下文。

---

## 13 個維度

| # | 維度 | 機械? | 抓什麼 |
|---|---|---|---|
| **D1** | 重複內容 DRY | ✅ | 跨 ≥3 檔一字不差的行；同一父目錄內＝樣板家族，自動降級 |
| **D2** | 命名不一致 | ✅ | 兩套以上並存的 ID 體系（`R5` vs `規則 5` vs `Rule 5`） |
| D3 | 可抽模組 | ❌ | 重複 ≥3 次 + 邏輯獨立 + 跨檔可 reuse |
| **D4** | 過長檔案 / 函數 | ✅ | 見下方門檻表 |
| D5 | 私公版 sync GAP | ❌ | dual-repo diff；≤10 行且只有署名 block＝by-design |
| D6 | Release 一致性 | ❌ | git tag / gh release / CHANGELOG / README 對齊 |
| **D7** | Cross-link 完整性 | ✅ | markdown 連結指向不存在的檔案（**只掃 .md**） |
| **D8** | 版本標記漂移 | ✅ | 逐檔版本**宣告**對全庫最新值 |
| D9 | 開源 / 交接健檢 | ❌ | 主力定位顛倒 / 隱性依賴沒標 / 無 minimum-viable / 個資烤進 default |
| **D10** ⭐ | **規則內容漂移** | ✅ | 同一命名空間內，同一規則 ID 在不同檔案講不同話 |
| **D11** ⭐ | **孤島 / SoT 缺失** | ✅ | 該互相引用卻零 cross-reference 的姊妹模組 |
| **D12** ⭐ | **gate 自我認證** | ✅ | 只有 self-test、沒有真 corpus 回歸的 gate（M114） |
| **D13** ⭐ | **裁決無機械落地** | ✅ | 台帳有規則但沒 gate 撐 |

⭐ = v0.4 新增。**D1-D9 全是「檔案層」；D10-D13 是「語意層」** —— 後者是 2026-08-07 一場真實 session 踩出來的，v0.3 全部抓不到。

### D4 長度門檻

| 類型 | 警告 | 嚴重 |
|---|---|---|
| SKILL.md | > 200 行 | > 400 行 |
| CHANGELOG.md | > 400 行 | > 1200 行 |
| 其他 .md | > 400 行 | > 800 行 |
| .py / .ts / .js | > 500 行 | > 1000 行 |
| 單函數 | > 50 行 | > 100 行 |

> ⚠️ **門檻誠實聲明**：這組數字是 v0.1 沿用至今的**經驗值，未經校準**。
> 嚴謹做法是照 M114 拿真 repo 的行數分佈回歸。**在校準前，把它當提示不當判決。**

---

## ⭐ v0.4 新增的四個語意層維度（每一條都是真的踩過）

### D10 — 規則內容漂移

**踩法（2026-08-07）**：R21 由作者從「所有決定都要開圓桌」降級為「只有策略級才開」，
但下游三個 skill 仍寫舊版。
**版本號完全沒變**（D8 抓不到）、**連結沒壞**（D7 抓不到）—— 只有比對**規則內容**才看得出來。

**判定**：同一命名空間 + 同一規則 ID + 兩份定義的中文 bigram 重疊率 < 30% → CRITICAL。

**三個必要的精確化**（都是 dogfood 打臉打出來的，改規則前先讀）：
1. **規則 ID 是每個模組各自的命名空間** —— `R1` 在 A skill 和 B skill 是兩條不同的規則，不是漂移
2. **只認定義行不認談論行** —— 「R21 降級同步到其他 skill」是待辦，不是規則定義
3. **中文要用字元 bigram 斷詞** —— 用 `\w+` 會把整串中文當一個 token，兩句完全不同的規則算出 50% 相似

### D11 — 孤島 / SoT 缺失

**踩法**：作者的 voice skill（他是誰／怎麼取捨）與 style skill（他怎麼講話）是同一件事的兩半，
grep 互相提及 **0 次** —— 「分身」實際上是兩個半身。**連結沒壞，但該連的沒連。**

**判定**：某模組有 ≥2 檔案，卻完全不提任何姊妹模組 → MED（可能是刻意獨立，需人確認）。

### D12 — gate 自我認證（M114）

**踩法**：`voice_gate.py` self-test **35/35 全綠**，拿 36 篇真腳本一掃 → **5/5 誤報**。
原因：**fixture 是照著規則寫的，規則錯在哪，fixture 就一起錯在哪** —— 等於被稽核方自己蓋章。

**判定**：找到 `*gate*.py` / `*check*.py` 有 self-test 但同目錄沒有 corpus / calibrate / regression 夥伴 → HIGH。

**修法**：每個 gate 都要兩層驗證 ——
- **正向對照**：真實產出，**誤殺率必須 0**（誤殺會讓人不再信任 gate，比漏抓貴）
- **反向對照**：明顯的壞東西，**必須全數抓到**（只有正向會養出「永不觸發」的假 gate）

> ⚠️ **corpus 的角色會因量測對象而不同**，這點極易搞錯：
> 量**語感**時，作者的成品＝**標準**（他對自己的語感滿意）。
> 量**他自評最弱的維度**時，作者的成品＝**現況，不是標準** ——
> 把門檻調到「現有作品剛好通過」＝認證他想修的問題。這種維度要做的是 **baseline 追蹤**，不是 pass/fail。

### D13 — 裁決無機械落地

原則來自裁決台帳的檔頭：「**只寫在文件裡＝會忘**」。

**判定**：ledger 類檔案有 ⬜ / 待建 / TODO 的裁決列 → MED。
**注意**：判斷題（品味／取捨／幽默）本來就不可機械化 —— 這種要**標明「本質不可機械化」**，不是空著。

---

## 人工維度速查（掃描器不覆蓋）

**D3 可抽模組**：重複 header block / 常數定義 / 同格式檢查表 / 共用 glyph。

**D5 私公版 sync**：diff ≤10 行且只有署名 block ＝ by-design；> 10 行 ＝ 真 desync。

**D6 Release 一致性**：有 tag 沒 release ／ CHANGELOG 缺最新版 ／ README 沒提最新版。

**D9 開源交接健檢**（五個隱形雷）：
1. **主力工具被標成「選用」** → 別人會拿次要工具當主力
2. **隱性依賴沒進需求**（Computer Use / API key / 系統權限）→ 採用者跑不起來還不知為何
3. **onboarding 沒有 ★必答 vs ⭕選填 分層** → 填完才給價值＝棄坑
4. **引用不存在的資料夾**（`docs/` 之類）
5. ⭐ **個資／品牌烤進 default 邏輯**（作者 keyword map／個人路徑／語言鎖死）→ 採用者 match 不到＝輸出對不上

判斷句：「**拿掉這個依賴，核心功能還能跑嗎？**」不能 → 必標需求。
「**零基礎的人能 5 分鐘跑起來嗎？**」不能 → onboarding 沒過。

---

## 三階段工作流

| Phase | 做什麼 | 產出 |
|---|---|---|
| 1 掃描 | 跑 `cleanup_scan.py` + 人工補 D3/D5/D6/D9 | findings |
| 2 報告 | 依 severity 排序，< 1 KB 給人讀 | 優先序清單 |
| 3 建議 | **不直接改** —— 出 refactor proposal，使用者確認後才動 | proposal |

## 🐕 Dogfood 紀律（v0.4 新增，本 skill 自己必須遵守）

一支叫別人查技術債的工具，**自己必須先過自己那關**：

```bash
python cleanup_scan.py --selftest && python cleanup_scan.py ~/.claude/skills/code-cleanup-helper
```

v0.4 開發時，self-test 綠之後拿真 repo 一掃，抓到 **5 個自己的 bug**：
跨模組 ID 撞號誤報 15 個 CRITICAL ／ 掃 `.py` 原始碼當 markdown 連結 ／
把數值常數當版本號 ／ **把自己 docstring 裡舉例用的假版本號當成真版本** ／ 把自己的正則字面值當成命名體系。

→ 全部是同一個形狀：**掃描器讀到自己的範例**。修完 CRITICAL 15 → 0、HIGH 119 → 30。
→ 這就是 D12 講的事，套在自己身上。**改動任何規則後，self-test 和真 repo 掃描兩個都要重跑。**

## 不要做

自動改檔 ／ 刪任何內容 ／ push ／ 改 CI・package.json・license ／ 動 `.git/` ／
`git push --force` ／ `git reset --hard` ／ 自動 publish release。
**永遠先報告 + 等使用者確認。**

## License

MIT — 保留此標註即可修改 / 使用 / 商用。

## Author

駱君昊 (Hao) · MetaFantasy Co-Founder

Repo: https://github.com/Hao0321/claude-skill-code-cleanup
Companion: https://github.com/Hao0321/claude-skill-social-post
