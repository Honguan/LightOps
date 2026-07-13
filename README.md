# LightOps

LightOps 是面向個人開發者、小型團隊與單台或少量 Linux 伺服器的輕量管理平台。它以 FastAPI、SQLite、Vue 3 與 systemd 提供監控、服務／Docker 管理、備份、軟體中心、專案部署、回滾、告警及每日健康報告。

## 支援環境

- Ubuntu／Debian 主流版本
- amd64／arm64
- 原生 systemd（不依賴 Docker）

## 安裝

```bash
curl -fsSL https://raw.githubusercontent.com/Honguan/LightOps/master/install.sh | sudo bash
sudo lightops reset-password
```

較安全的下載後執行方式：

```bash
curl -fsSL https://raw.githubusercontent.com/Honguan/LightOps/master/install.sh -o install.sh
sudo bash install.sh
```

安裝器會驗證 release SHA-256、建立 `lightops` 系統帳號、資料與日誌目錄、systemd 服務及受白名單限制的 root helper。Web 服務監聽 `9080`；正式環境建議設定 `LIGHTOPS_IP_ALLOWLIST`，並以具 TLS 的 Nginx 或 Caddy 反向代理存取。

## 常用指令

```bash
lightops status
sudo lightops update --channel stable
sudo lightops rollback
lightops app list
lightops app install nginx docker git curl
lightops stack install lemp
lightops project create "My Site" my-site static https://example.com/site.git /srv/my-site
lightops project deploy my-site
lightops project rollback my-site
lightops backup website /var/www/html
lightops doctor
```

## 目錄

| 用途 | 路徑 |
| --- | --- |
| 程式版本 | `/opt/lightops/releases` |
| 目前版本 | `/opt/lightops/current` |
| 設定 | `/etc/lightops` |
| 資料 | `/var/lib/lightops` |
| 日誌 | `/var/log/lightops` |
| 備份 | `/var/backups/lightops` |

## 本機開發

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest

cd frontend
npm install
npm run build

LIGHTOPS_AUTH_DISABLED=true LIGHTOPS_SCHEDULER_DISABLED=true uvicorn lightops.api:app --reload
```

## 安全模型

- API 預設需要具到期時間的 Bearer Session；密碼以 scrypt 雜湊。
- 支援 TOTP，登入具 IP 速率限制，所有修改操作寫入審計日誌。
- Web 程序以 `lightops` 帳號執行；套件、systemd 與 Docker 操作只能透過 root 擁有的白名單 helper。
- 所有系統命令以參數陣列執行，不接受前端任意 Shell。
- 更新檔必須通過 SHA-256 驗證，失敗健康檢查會自動切回原版本。
- `.env`、Token 與密碼不由管理 API 回傳。

## 測試

```bash
pytest
bash -n install.sh installer/*.sh
cd frontend && npm run typecheck && npm run build
```
