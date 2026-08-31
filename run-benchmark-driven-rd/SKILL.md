---
name: run-benchmark-driven-rd
description: 將高風險產品目標轉成可否證、benchmark-gated R&D。適用架構、效能、交付、資安、模型／Token、完整度；可分發專案／Skill 的迭代與收尾預設納入 GitHub 安全更新檢查、回滾及舊版淘汰。
---

# Run Benchmark-Driven R&D

用同 provenance 證據做決策並保留可重播學習。

## 核心 contract

1. Active private Skill trees 是唯一權威。開始用 `invocation_revision_gate.py capture` 凍結 R&D＋Cleanup revision，最終判斷前 `verify`；`UNSTABLE` 不混用，`STALE` 重讀並重跑受影響 gate。
2. 只在原始授權內修改；本機實作不暗含外部／破壞性 mutation。外部變更另需當輪授權、精確 target、preflight 與 post-readback；GitHub URL 不是執行授權。
3. 先寫 claim、baseline、threshold、decision rule，再用 task-shaped 正負控制校準 evaluator。Exit 0、元件／模型／短 prompt／工具綠燈不能替代品質、完成或 parity；缺同 provenance 證據保持 `unmeasured`／`NOT_CHECKED`。
4. Cleanup 是獨立 read-only provider；保留其 PASS／FAIL／REVIEW／NOT_CHECKED、child 與 revision evidence。R&D 可套 strict promotion policy，但不可把 provider 缺口改寫成 PASS。
5. Route receipt 列 intent、stage、artifact/risk、selected/omitted topics、hash、critical IDs、cost、fallback。未知／歧義／stale／超 budget 時 block 或 legacy fallback，不漏 critical rule。
6. Raw/private learning 留在目標 `.rd/`，預設零 prompt Tokens；shared rule 需 typed receipt、單一 owner、privacy、正負 fixture 與 reciprocal link。縮短 context 不刪記憶。
7. 可分發下游 Skill／software／game／installer／release 的已授權 implementation／promotion／completion 預設需要安全更新 capability；audit／source-only 不改檔，也不推導 publish、sign、persistence、delete 權限。

## 路由

| 任務 | 讀取 |
|---|---|
| 一般 experiment | `references/topics/core-experiment.md` |
| 架構／Cleanup baseline | `references/topics/architecture-and-evaluator.md` |
| context／Token／learning | `references/topics/context-and-learning.md` |
| capability／complete／external | `references/topics/completion-and-external.md` |
| updater 或可分發目標的 implementation／promotion／completion | `references/topics/secure-self-update.md`；依風險加 delivery/security，排除 audit／source-only |

Delivery、security、web、mobile、media、model、cross-system 讀對應既有 reference；大型 protocol／metrics／tooling／completion／external 只供 legacy／特殊 family。修改本 Skill 讀 `references/maintenance.md`。

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
