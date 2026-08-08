# claude-skill-code-cleanup

> 一個 [Claude Code](https://claude.com/claude-code) skill，自動掃 codebase / SKILL.md / prompt template，找出重複、命名不一致、可模組化區塊、過長檔案。

**作者**：**駱君昊 (Hao)** · MetaFantasy Co-Founder · AIGC 數位創作者
🔗 [Facebook](https://www.facebook.com/lo.jain.hao) · [Claude Code 台灣交流討論區（Line 社群）](https://line.me/ti/g2/DPTQR_XE6IYP8c5lBxsbRwsvEUsxI-70p1jWoA) · [姐妹 repo: social-post skill](https://github.com/Hao0321/claude-skill-social-post)

---

## 起源

寫大專案最後變一坨亂這件事，每個 dev 都遇過。我這套 social-post skill 兩週寫到 2,100 行，連 R 規則命名都散落兩種寫法（R5 vs 規則 5）。

這個 skill 就是來自動掃這種**慢性技術債**。

跑我自己 social-post repo 的真實 cleanup report：

```
=== Cleanup Report — social-post skill v0.7.1 ===

📊 2,100 行 / 11 個檔案

🎯 命名不一致（最嚴重）
- 「R[N]」（SKILL.md，13 種）vs「規則 [N]」（case_studies.md，10 種）
- 兩套同源系統互不引用 → 讀者需要心智 mapping

📈 重複內容散落
- 「鐵粉」 65 次 / 「Day 1」 70 次 / 「F6b」 56 次跨 4 檔
- 同樣的戰績數字（75K / 380 / 1,319）出現在 5+ 處

📦 過長檔案
- case_studies.md 604 行（接近 800 警告線）
- formulas.md 505 行
- SKILL.md 377 行（超出 200 建議線）

🔧 建議：v0.8 release 前 cleanup（總計 ~2.5 hr）
1. 統一 R[N] vs 規則 N 命名（30 min）
2. 抽 references/battle_records.md（45 min）
3. case_studies.md 拆檔（60 min）
```

→ 看完報告才知道**自己 skill 哪裡有債**。然後決定要不要還。

---

## v0.4：可執行掃描器 + 13 個維度

v0.4 起附**跨平台 Python 掃描器** [`cleanup_scan.py`](code-cleanup-helper/cleanup_scan.py)（不需 bash）——
機械掃 9 類、人工判 4 類，依 severity（CRITICAL → LOW）排序輸出：

```bash
python code-cleanup-helper/cleanup_scan.py <目標資料夾>    # 掃描（--json / --max-files 可選）
```

```bash
python code-cleanup-helper/cleanup_scan.py --selftest      # 20 項雙向自測
```

### 檔案層（v0.1–v0.3）

1. **重複內容**（DRY 違反）— 跨檔一字不差的行、同 keyword 散落 ✅機械
2. **命名不一致**（同 concept 多種寫法，`R5` vs `規則 5`）✅機械
3. **可抽 reusable 模組**（重複 ≥ 3 次 + 邏輯獨立）
4. **過長檔案 / 函數** ✅機械
5. **私公版 sync GAP**（適用 dual-repo skill）
6. **Release 一致性**（git tag / gh release / CHANGELOG / README 對齊）
7. **Cross-link 完整性**（markdown 連結指向不存在的檔案）✅機械
8. **版本標記漂移**（只認版本**宣告**，不認散文提及）✅機械
9. **開源/交接文件健檢**（主力定位顛倒 / 隱性依賴沒標需求 / 個資烤進 default，源自 video-autopilot-kit 開源實戰）

### ⭐ 語意層（v0.4 NEW — 檔案層全綠也抓得到的債）

10. **規則內容漂移** — 同一規則 ID 在不同檔案講不同話（版本號沒變、連結沒壞，D7/D8 全抓不到）✅機械
11. **孤島 / SoT 缺失** — 該互相引用卻零 cross-reference 的姊妹模組 ✅機械
12. **gate 自我認證** — 只有 self-test、沒有真 corpus 回歸的 gate（fixture 照規則寫，規則錯 fixture 一起錯）✅機械
13. **裁決無機械落地** — 決策台帳有規則但沒 gate 撐 ✅機械

詳見 [`code-cleanup-helper/SKILL.md`](code-cleanup-helper/SKILL.md)。

---

## 三階段工作流

```
Phase 1: 掃描（< 30 sec）
   ↓
Phase 2: 報告（< 1 KB 給人讀）
   ↓
[使用者確認]
   ↓
Phase 3: 重構建議（不自動改檔案）
```

**永遠先報告 + 等使用者確認，絕不自動修改**。

---

## 安裝

```bash
# 1. clone
git clone https://github.com/Hao0321/claude-skill-code-cleanup.git

# 2. 複製到你的 skill 路徑
# macOS / Linux:
cp -r claude-skill-code-cleanup/code-cleanup-helper ~/.claude/skills/

# Windows (PowerShell):
Copy-Item -Path "claude-skill-code-cleanup\code-cleanup-helper" -Destination "$env:USERPROFILE\.claude\skills\" -Recurse
```

---

## 用

Claude Code 跟它說：

```
掃一下我這個 codebase
```

或

```
我這 skill prompt 寫好亂，cleanup 一下
```

或

```
review 我的 code 看有沒有可以模組化的
```

skill 會跑三階段，輸出報告 + 重構建議。

---

## FAQ

**Q: 跟 linter / formatter 有什麼差？**
A: linter 看 syntax，cleanup-helper 看 **semantic 重複**（同 concept 不同字也算）。例：「viral 主因」「viral 必要條件」「能爆款的關鍵」 = 同 concept 三種寫法 → ESLint 看不到，cleanup-helper 抓到。

**Q: 會自動改我的 code 嗎？**
A: **絕對不會**。只報告 + 等你確認。Phase 3 給建議，你說 OK 才用 Edit / Write 工具改。

**Q: 適用什麼語言？**
A: 主要設計給 **prompt / SKILL.md / markdown / 文件**型 codebase。一般程式碼（py / ts / js）也可用 Phase 1-2，但 Phase 3 建議偏 prompt design。

**Q: 跟你 social-post skill 什麼關係？**
A: 姐妹 skill。social-post 幫你發內容，cleanup-helper 幫你的 skill 不變亂。可以用 cleanup-helper 來 maintain social-post 自己。

**Q: 商用可以嗎？**
A: MIT License，可改可商用，保留 LICENSE 檔即可。

---

## 限制

- 主要為**中文 / 英文混合 markdown prompt** 設計
- 一般 source code cleanup 建議搭配真正的 linter
- 掃描器只覆蓋 9/13 維度；D3 / D5 / D6 / D9 是判斷題，照 SKILL.md 人工跑
- **掃描綠 ≠ 專案健康** — D4 長度門檻是未校準經驗值，當提示不當判決

---

## 授權

[MIT License](LICENSE) — 隨便改、隨便用、商用也行。保留 LICENSE 檔即可。

---

## 致謝

這個 skill 是 **駱君昊 (Hao)** 在開發 social-post skill 過程中發現「自己的 skill 越寫越亂」後做出來的工具。

跑自己 skill 的 cleanup report 才發現連命名都有兩套（R5 vs 規則 5）。**用 skill 修 skill = meta loop**。

如果你用這個 skill 修了你自己的 skill，歡迎 tag 我的 FB：[@lo.jain.hao](https://www.facebook.com/lo.jain.hao)

想聊 AI 應用、skill 開發、社群經營，加 [Claude Code 台灣交流討論區](https://line.me/ti/g2/DPTQR_XE6IYP8c5lBxsbRwsvEUsxI-70p1jWoA) 🚀

---

**⭐ Star this repo if it helped you. 覺得有用請按星。**
