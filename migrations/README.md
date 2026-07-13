# 資料庫遷移

遷移由 `lightops-migrate up` 依版本順序執行並記錄於 `schema_migrations`。每個新遷移必須明確標示是否可逆；不可逆遷移需在 release notes 提醒人工確認，且不得由自動回滾嘗試反向執行。
