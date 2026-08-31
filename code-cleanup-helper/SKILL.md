---
name: code-cleanup-helper
description: Read-only 跨平台 code／architecture／repo／release／Skill 審計器。用於清理前盤點、重複／依賴／分層／長責任、sync、release／資安、生成資產、Skill Token、GitHub 自動更新與舊版淘汰稽核；也是 R&D 的 measurement provider。
---

# Code Cleanup Helper

## 永遠適用的 contract

1. Active private Skill 目錄是唯一權威。讀取前 `check_skill_revision.py capture` 一致性雙掃描，最終 `verify`；`UNSTABLE` 不混用，`STALE` 重讀並重跑受影響 gate。
2. Audit 永遠 read-only。純診斷先報告再等授權；已授權的 R&D／實作只取證，不重複詢問。不得自行做外部或破壞性 mutation。
3. `FAIL`=已證明阻擋、`REVIEW`=人工判斷、`NOT_CHECKED`=量尺／環境／證據缺口、`PASS`=僅已執行維度；未量測不得包裝為 PASS。
4. 外部檢查要保存 child executable identity、真實啟動、child exit 與 success marker；父 shell exit 0 不代表通過。
5. 解析目標絕對路徑；修後重跑同 audit，報告綁定 revision、config、route 與 JSON evidence。
6. Cleanup 是獨立唯讀 provider；R&D 可選 mode／config，但選模組不等於通過。修改、promotion、外部 mutation 與完成宣告歸 orchestrator。
7. 每次 audit 都分類下游 target 的更新覆蓋（managed／check-only／safe-auto-update／manual-only／no-origin）；不由 URL／檔案存在升格，也不讓 Cleanup／R&D 自行更新。

## Progressive-disclosure 路由

只讀本次適用列；不確定、缺失或 budget overflow 時使用明示的 legacy fallback，不可靜默漏掉 critical rule。

| 任務 | 讀取 |
|---|---|
| duplicate／命名／架構／依賴／長函式 | `references/mode-a.md` |
| sync／release／link／drift／handoff | `references/mode-b.md` |
| config、例外、machine report、資產配對 | `references/config-and-report.md` |
| R&D baseline／promotion／freshness | `references/rd-integration.md` |
| capability／完整收尾 | `references/capability-obligations.md` |
| build／installer receipt | `references/build-receipt-audit.md` |
| security／secret／extracted payload | `references/security-and-release-hygiene.md` |
| model／prompt／Token claim | `references/model-context-contract-audit.md` + `references/topics/context-routing-and-memory.md` |
| 一般跨系統 journey | `references/topics/cross-system-core.md` |
| 專業媒體／Timeline／成片 | `references/topics/media-workstation.md` |
| desktop runtime／背景 job | `references/topics/desktop-runtime.md` |
| Codex／Claude／MCP 產品流程 | `references/topics/session-native-ai.md` |
| GitHub updater／回滾／淘汰舊版 | `references/topics/secure-self-update.md`；helper／installer／簽章再加 security＋build |

跨類任務合併必要列；歧義時載入完整 legacy `references/cross-system-integration-audit.md` 並記錄原因／成本。修改本 Skill 讀 `references/maintenance.md`。

## 執行與報告

```powershell
python scripts/audit.py <target> --mode all --format json
```

僅 CI／fail-fast 加 `--strict`。普通 `REVIEW` 不阻擋；完整收尾由 R&D 收斂 review、freshness、obligations。未解析的非 Python graph 保持 `NOT_CHECKED`。輸出 3–10 個最高優先 finding，完整清單留 JSON；GitHub URL 不授權下載執行。
