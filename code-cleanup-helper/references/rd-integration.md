# R&D integration contract

把 Cleanup 當成 deterministic、read-only evaluator；把 `run-benchmark-driven-rd` 當成唯一決策、修改與 promotion orchestrator。不要複製 Cleanup detector 到 R&D。

## Provider invocation

每個 baseline 或 promotion 都先執行 evaluator self-test，再輸出一份 JSON：

```powershell
$env:PYTHONUTF8='1'
python scripts/self_test.py
python scripts/audit.py <target> --mode architecture --format json
```

依任務選擇 `architecture`、`a`、`b` 或 `all`。不要在 baseline 加 `--strict`；既有 FAIL 是待比較的證據，不是 evaluator 啟動失敗。

## Machine contract

接受報告前驗證：

- stdout 恰好是一份可解析 JSON，沒有前後雜訊；
- `schema_version` 是 consumer 明確支援的版本；
- 必備欄位為 `target`、`mode`、`config`、`summary`、`inventory`、`architecture`、`findings`；
- finding status 只能是 `PASS`、`FAIL`、`REVIEW`、`NOT_CHECKED`；
- `summary` 的四種狀態數量與 `findings` 完全相等；
- target 與 mode 等於本次 frozen invocation；
- evaluator hash 涵蓋 `audit.py`、`audit_core.py`、`self_test.py`；使用設定檔時另存 config hash。

任何一項不成立都分類為 `measurement` failure，停止產品變更並先修 evaluator。

## Phase semantics

- **Baseline**：有效報告即可保存；現有 `FAIL` 不阻止建立 baseline。
- **Promotion**：任何 `FAIL` 阻擋 promotion。
- **REVIEW**：保持可見但不自動阻擋；由 orchestrator 做語意判斷。
- **NOT_CHECKED**：永遠標記 `unmeasured`；若屬本次 required dimension，阻擋 promotion。

用相同 evaluator hash、config hash、mode 與 target 比較 before／after。若量尺改變，先重跑 baseline，不可直接比較舊新分數。

將完整 contract envelope 保存到 `.rd/benchmarks/`；在 `.rd/DECISIONS.md` 記錄 promotion，在 `.rd/FAILURES.md` 記錄量尺缺陷。

## Authorization boundary

Cleanup 不取得修改權，也不執行修復。若使用者只要求 audit／分析，orchestrator 必須停在報告。若原始請求已明確要求實作、重構或修復，該請求可供 R&D 在既定範圍內繼續，不需要因 Cleanup 被調用而要求第二次確認。

本契約只涵蓋本地證據。外部 create、publish、rename、archive、delete、transfer、permission change、登入與授權都必須另走 R&D external-change gate。
