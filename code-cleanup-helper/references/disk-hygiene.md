# 開發階段磁碟收尾（唯讀 provider）

每輪 build／render／大型測試前、階段成功或失敗後、重試與交接前都檢查；長跑在安全檢查點再查。先量測系統暫存槽與工作槽（Windows 常分 C、D，但須解析實際位置），不得只看 repository 大小。空間不足先處理，不另開大量副本。

## 提供給執行者的清單

逐個候選記錄絕對實體路徑、生成者／用途、檔案數與 logical bytes、最後使用證據、活躍程序／工作、保留或淘汰理由、重建方法。目錄年齡、名稱帶 temp／old／failed 或程序清單沒命中，都不能單獨證明安全。

- 保護原始碼、未提交變更、使用者原始素材／專案／成片、記憶、金鑰、正常 app profile、共用依賴、執行中工作、目前 candidate 與最後可用 rollback。
- 優先提議已退出工作的編譯中間檔、可重建 cache、過期解包／stage 副本、已被替代的測試轉碼與孤立 profile。唯一失敗重現、未結案 bug 的必要實物或待交付內容須保留。
- 「保留證據」是保留命令、版本／hash、輸入身分、結果與必要 fixture，不是永久保留每一份完整 target／trial／影片複本。移除實物後在新帳本引用原 receipt SHA、標記 retired；不改 immutable receipt，也不宣稱已刪產物仍可直接重播。
- 列下一輪峰值空間估計與磁碟餘裕；threshold 由專案設定，未知就明示，不能編造。跨槽搬移必先檢查目的槽；同槽改名或送資源回收筒不等於釋放空間。

Cleanup 只盤點，不執行刪除。交由已獲適用授權的 orchestrator 核對精確 allowlist；不確定歸 REVIEW。普通 source audit 不會自動量測磁碟，缺此證據保留 NOT_CHECKED。

## 清理後驗收

執行者回填每個 target 的成功／略過／失敗、可恢復性、刪前後磁碟 free bytes、保護項目未變與有效建置／專案檢查。logical bytes 與實際空間增量分開報告；硬連結、壓縮與同期建置會使兩者不同。不得全清回收筒、Downloads、Temp、磁碟／工作區根目錄；不得藉清理取消別人的工作。
