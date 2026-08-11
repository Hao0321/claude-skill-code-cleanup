---
name: code-cleanup-helper
description: 以跨平台、read-only 審計器掃描 codebase、prompt、SKILL.md 與 repository，找重複內容、命名／永久 ID 漂移、可抽模組、過長檔案、私公版 sync、release 文件、broken links、版本／事實矛盾、skill metadata、隱私外洩與語意規則漂移。使用者說「清理 code」「找重複」「重構」「掃 prompt」「skill 太長」「audit repo」「私公版 diff」「版本對齊」「release 前盤點」「check links」「規則漂移」時使用。
---

# Code Cleanup Helper

先用可重複執行的 Python 審計器收集證據，再由 agent 判讀語意；不以臨時 Bash、關鍵字數量或主觀印象直接裁決。

## 硬規則

- Audit 永遠 read-only。
- 永遠先報告，再等使用者明確確認修復範圍。
- 未能執行的維度標 `NOT_CHECKED`，不包裝成通過。
- 不改 `.git/`、測試／CI、license、package metadata，除非使用者明確放進修復範圍。
- 不 commit、push、force reset 或 publish release。

## 路由

| 使用者意圖 | Mode | 必讀／工具 |
|---|---|---|
| 重複、命名、模組、檔案太長 | A | `references/mode-a.md`＋`scripts/audit.py --mode a` |
| sync、release、link、drift、handoff | B | `references/mode-b.md`＋`scripts/audit.py --mode b` |
| 規則內容漂移、孤島、gate 自我認證 | Semantic | `cleanup_scan.py` |
| 完整健檢 | A+B+Semantic | 以上全部 |
| 設定例外／機器報告 | 任一 | `references/config-and-report.md` |

## 兩層掃描器

1. `scripts/audit.py`：deterministic repo audit，輸出 PASS／FAIL／NOT_CHECKED，支援 config、JSON 與 strict mode。
2. `cleanup_scan.py`：保留 v0.4.1 的深層掃描，涵蓋規則內容漂移、SoT 孤島、gate 自我認證與裁決未落地。

兩者互補。Deterministic audit 適合 CI 與可重現證據；semantic scanner 適合找「檔案都沒壞，但規則已經分叉」的問題。

## 標準流程

1. 解析目標絕對路徑；確認存在，不猜 repo。
2. 依路由執行一或兩個掃描器。Windows 先設 `PYTHONUTF8=1`。
3. 讀 JSON 證據或人類摘要；需要語意判斷時再讀相關檔案。
4. 回報 FAIL、NOT_CHECKED、影響與最小修復順序。
5. 停下等待確認；使用者回「全做／執行／做」後，才在已報告範圍內修改。
6. 修完重跑相同 audit；不能只靠肉眼宣稱完成。

```powershell
$env:PYTHONUTF8='1'
python scripts/audit.py <target> --mode all
python scripts/audit.py <target> --mode all --format json
python cleanup_scan.py <target>
```

只有 CI 或使用者要求 fail-fast 時加 `--strict`。預設 exit 0 只代表 audit 成功跑完。

## 專用檢查器

```powershell
python scripts/check_links.py <target>
python scripts/check_drift.py <target>
python scripts/check_sync.py <target>
python scripts/self_test.py
python cleanup_scan.py --selftest
```

## 報告格式

用短表格輸出：

| 狀態 | 維度 | 發現 | 證據 | 建議 |
|---|---|---|---|---|

只列最高優先的 3–10 筆；完整清單留在 JSON。結尾給單一 next action，例如「回『修 P0』後我才修改」。

## 判讀邊界

- Exact duplicate、broken link、ID range、sync diff 可由 script 判定。
- Semantic duplicate、架構是否值得抽象、公開文件是否講清楚，必須讀上下文判斷。
- 平台、API、法律等時效事實不靠本地 regex 宣稱正確；需要時另查權威來源。
- D4 長度門檻是可覆寫的經驗警告，不是品質判決。

## 維護

- 新 deterministic 檢查先加到 `scripts/audit_core.py`，再補 `scripts/self_test.py`。
- 新 semantic 檢查需同時補 `cleanup_scan.py --selftest` 的正反案例。
- 專案特有事實放目標 repo 的 `audit.config.json`，不要 hardcode 到通用引擎。
- `agents/openai.yaml` 改動後重新跑 skill validation。
