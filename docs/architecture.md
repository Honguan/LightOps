# LightOps 架構

LightOps 由四個邊界組成：FastAPI 管理 API、Vue 管理介面、`lightops` CLI，以及 root 擁有的特權 helper。API 與 CLI 不直接拼接 Shell；軟體資訊由 `manifests/*.yaml` 提供，專案建置步驟由 `deployment-templates/*.yaml` 提供。

資料預設寫入 SQLite。專案部署建立不可變 release 目錄，健康檢查成功後以原子方式切換 `current` symbolic link；回滾只切換連結。系統更新採相同模型，並保留最近三版。

背景排程每五分鐘評估磁碟告警，每日產生健康報告。通知狀態會持久化，以提供冷卻、合併與恢復通知。
