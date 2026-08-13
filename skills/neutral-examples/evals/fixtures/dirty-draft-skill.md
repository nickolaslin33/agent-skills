---
name: deploy-checklist
description: 部署前的檢查清單。每次要把服務推上正式環境前使用。
---

# Deploy Checklist

## 為什麼

我們在 PhoenixTracker 上線那次漏掉了 migration，資料庫回不去，花了四小時修。
這份清單就是那次之後訂的。

## 步驟

### 1. 確認分支狀態

```bash
cd /Users/dwilson/work/PhoenixTracker
git fetch origin && git status
```

### 2. 跑完整測試

```bash
cd /Users/dwilson/work/PhoenixTracker && pytest -v
```

AtlasBooking 那邊的測試要另外跑，因為它用不同的 test runner。

### 3. 檢查 migration

連到 staging 資料庫確認：

```bash
psql -h db-staging.northwind-corp.com.tw -U deploy -d phoenix_prod -c "\dt"
```

### 4. 通知

部署前在群組通知，或直接寄給 dwilson@northwind-corp.com.tw。
內部的 SkyBridge 排程系統會在部署後自動跑一次健康檢查，
如果 SkyBridge 回報失敗，就照 AtlasBooking 的 rollback 流程處理。

### 5. 部署

```bash
ssh deploy@10.42.7.15
sudo systemctl restart phoenix-tracker
```
