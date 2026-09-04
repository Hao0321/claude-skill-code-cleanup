---
name: run-benchmark-driven-rd
description: 將高風險產品目標轉成可否證、benchmark-gated R&D；可分發專案／Skill 的迭代與收尾預設納入 GitHub 安全更新、回滾及舊版淘汰。
---

# Run Benchmark-Driven R&D

## 核心 contract

1. Active private Skill 唯一權威。先 `invocation_revision_gate.py capture` 凍結雙 revision，決策前 `verify`；`UNSTABLE` 不混用，`STALE` 重讀重驗。
2. 修改不越原始授權；本機實作不暗含外部／破壞性 mutation。外部變更須當輪授權、精確 target、preflight、post-readback；GitHub URL 不授權執行。
3. 先寫 claim、baseline、threshold、decision rule，用 task-shaped 正負控制校準 evaluator。工具／元件綠燈不等於品質、完成或 parity；缺同 provenance 證據保持 `unmeasured`／`NOT_CHECKED`。
4. Cleanup 是獨立唯讀 provider；保留 PASS／FAIL／REVIEW／NOT_CHECKED、child、revision evidence；strict promotion 不可改寫缺口為 PASS。
5. Route receipt 列 intent、stage、artifact/risk、selected/omitted topics、hash、critical IDs、cost、fallback；未知／歧義／stale／超 budget 時 block 或 legacy fallback。
6. Raw/private learning 留在目標 `.rd/`，預設零 prompt Tokens；shared rule 需 typed receipt、單一 owner、privacy、正負 fixture 與 reciprocal link。縮短 context 不刪記憶。
7. 可分發目標的已授權 implementation／promotion／completion 預設需安全更新能力；audit／security-assessment／source-only 不推導 updater、publish、sign、persistence、delete 權限。
8. Security route 每個 target 必須規劃並驗完固定六控制；public／parity 再綁同專案 Cleanup、delivery、build 與 release artifact，sibling decoy 無效。
9. 階段完成、重試或交接前執行 `references/disk-hygiene.md`；在授權內清理可重建舊產物，不保留全部歷代副本。

## 路由

| 任務 | 讀取 |
|---|---|
| 一般 experiment | `references/topics/core-experiment.md` |
| 架構／Cleanup baseline | `references/topics/architecture-and-evaluator.md` |
| context／Token／learning | `references/topics/context-and-learning.md` |
| capability／complete／external | `references/topics/completion-and-external.md` |
| updater 或可分發目標的 implementation／promotion／completion | `references/topics/secure-self-update.md`；依風險自動加 delivery/security，排除 audit／source-only |

Delivery、security、web、mobile、media、model、cross-system 讀對應 reference；大型 contract 僅 legacy／特殊 family。修改本 Skill 讀 `references/maintenance.md`。

## 工作流

1. 解析絕對 repo、授權、contract、obligations、failures、`.rd/`；產生含 typed `updateObligation`／capability floor 的 route。
2. 定義 claim matrix／provenance；校準 evaluator，以 Cleanup＋native gate 凍結 baseline。
3. 做最小決定性實驗，保存 executable、stdout/stderr、exit、elapsed、input/environment hash、artifact、failure type。
4. 原子寫 typed project-local record；只有 promotion gate 通過才更新 shared topic/index，不把事故敘事 append 到 entrypoint。
5. 重跑相同 benchmark、負控制、delivered journey、obligations；最後修改後重驗 freshness/revision。
6. 分開報告 `measured stronger`、`likely but unmeasured`、`unchanged`、`regressed/open`，不以 PASS 數量冒充整體變強。

```powershell
python scripts/project_profile_gate.py --project <target> --contract <task-contract.json> --output <route.json> --quiet
```

Updater：side-by-side stage → digest/attestation → health → atomic switch → rollback → 淘汰 inactive 舊版；Skill 下次 invocation／restart 才切換。背景、自啟、破壞性 migration 分開 opt-in。
