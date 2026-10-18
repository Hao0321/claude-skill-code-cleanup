---
name: code-cleanup-helper
description: Read-only code／architecture／repo／release／Skill audit；含 sync、資安、資產、Token、GitHub 更新／回滾／淘汰；R&D measurement provider。
---

# Code Cleanup Helper

## Contract

1. Active private Skill 是唯一權威。開始 `check_skill_revision.py capture`，最終 `verify`；`UNSTABLE` 不混用，`STALE` 重讀重驗。
2. Audit 唯讀。診斷先報告等授權；已授權實作直接取證；不自行外部／破壞性 mutation。
3. `FAIL`=已證明阻擋、`REVIEW`=人工判斷、`NOT_CHECKED`=量尺／環境／證據缺口、`PASS`=僅已執行維度；未量測不得包裝為 PASS。
4. 外部檢查保存 child executable identity、真實 launch、exit、success marker；父 shell exit 0 非通過證據。
5. 解析絕對目標；修後重跑，報告綁 revision／config／route 與 JSON 證據。
6. Cleanup 是獨立 provider；mode／config 非通過證據。修改、promotion、外部 mutation、完成歸 orchestrator。
7. 分類更新覆蓋（managed／check-only／safe-auto-update／manual-only／no-origin）；URL／檔案不證明或授權更新能力。
8. Security v2 每個 target 必須覆蓋六控制 planned/executed cells；零 finding、generic check 或自結不補缺格。
9. 收尾／大產物前查磁碟；依 `references/disk-hygiene.md` 列清理清單。

## 路由

歧義／缺失／超 budget 明示 legacy fallback，保留 critical rule。

| 任務 | 讀取 |
|---|---|
| duplicate／命名／架構／依賴／長函式 | `references/mode-a.md` |
| sync／release／link／drift／handoff | `references/mode-b.md` |
| config、例外、machine report、資產配對 | `references/config-and-report.md` |
| R&D baseline／promotion／freshness | `references/rd-integration.md` |
| capability／完整收尾 | `references/capability-obligations.md` |
| build／installer receipt | `references/build-receipt-audit.md` |
| 逆向分析／交付物暴露 | `references/topics/reverse-engineering-audit.md` |
| security／交易／帳號／payload | `references/security-and-release-hygiene.md` + `references/security-assessment-contract.md` |
| model／prompt／Token claim | `references/model-context-contract-audit.md` + `references/topics/context-routing-and-memory.md` |
| 一般跨系統 journey | `references/topics/cross-system-core.md` |
| 專業媒體／Timeline／成片 | `references/topics/media-workstation.md` |
| 3D／UV／Unreal | `references/topics/character-3d-audit.md` |
| 視覺／UI／材質品質 | `references/topics/visual-quality-audit.md` |
| desktop runtime／背景 job | `references/topics/desktop-runtime.md` |
| PR／權限 | `references/topics/community-pr-audit.md` |
| AI產品 | `references/topics/session-native-ai.md` |
| 外部 Skill／plugin | `references/topics/agent-workflow-audit.md` |
| GitHub updater／回滾／淘汰舊版 | `references/topics/secure-self-update.md`；helper／installer／簽章再加 security＋build |

跨類合併。Legacy：`references/cross-system-integration-audit.md`，記錄原因／成本；維護：`references/maintenance.md`。

## 執行

```powershell
python scripts/audit.py <target> --mode all --format json
```

CI／fail-fast 才加 `--strict`。普通 `REVIEW` 不阻擋；R&D 收尾須收斂 review、freshness、obligations。未解析 graph 保持 `NOT_CHECKED`。優先報 3–10 個 finding，其餘留 JSON。
