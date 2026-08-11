# Mode A：Cleanup audit

用於 codebase、prompt、SKILL.md 與 reference 的結構清理。先掃描、只報告；取得使用者確認後才修改。

## 四個維度

1. **重複內容**：找跨檔案相同長段落。相同邏輯不同措辭仍需人工判讀，不把 keyword 高頻直接當 bug。
2. **命名一致性**：檢查 R／F／Case 等永久 ID、重複 heading、同概念多種名稱。
3. **可抽模組**：以重複段落、共用 schema、重複 CLI 流程為候選；沒有第三次使用就不要硬抽象。
4. **檔案長度**：預設警告線如下，可由 `audit.config.json` 覆寫。

| 類型 | 警告 | 嚴重 |
|---|---:|---:|
| SKILL.md | 200 | 400 |
| references/*.md | 400 | 800 |
| .py／.js／.ts | 500 | 1,000 |

## 執行

```powershell
$env:PYTHONUTF8='1'
python scripts/audit.py <target> --mode a
```

需要完整證據時改用 `--format json`。只有 CI／明確要求 exit code 時才加 `--strict`。

## 判讀

- `PASS`：有執行且通過。
- `FAIL`：有可定位的問題，不代表可以自動修改。
- `NOT_CHECKED`：缺少 repo、設定或外部能力；不得寫成通過。
- 重複偵測只抓 exact normalized paragraph；semantic duplicate 仍由 agent 讀上下文判斷。
