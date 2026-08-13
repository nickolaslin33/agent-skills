# 標準替代詞彙

寫對外文件時，範例素材一律從這裡取。固定用同一組名字的好處是前後對得起來：
讀者看到 `orders-api` 在不同段落出現，可以確定講的是同一個服務。如果每段各自編一個
名字，讀者會不確定它們之間有沒有關聯，得回頭比對。

## 網域與 IP：用標準保留的，不要自己編

RFC 2606 與 RFC 6761 把這些網域保留給文件使用，不會被任何人註冊，也不會有人誤連：

- `example.com`、`example.org`、`example.net`、`example.edu`
- `localhost`
- 保留 TLD：`.test`、`.invalid`、`.example`、`.localhost`

需要表示「內部服務」時用子網域：`api.internal.example.com`、`db.example.internal`。

IP 位址用 RFC 5737 保留的三段（IPv6 用 RFC 3849）：

| 用途 | 網段 |
|---|---|
| 文件範例 1 | `192.0.2.0/24` |
| 文件範例 2 | `198.51.100.0/24` |
| 文件範例 3 | `203.0.113.0/24` |
| IPv6 | `2001:db8::/32` |

**不要用 `1.2.3.4`、`8.8.8.8` 或隨手打的 IP**——那些是真的有人在用的位址。

## 專案與 repo 名稱

選有意義、看得出領域的名字，不要用 `my-project`、`foo`、`test-repo` 這種無資訊的字。
名字換成虛構的是為了不洩漏來源，不是為了讓範例變得空泛——`orders-api` 讓讀者知道
這是個處理訂單的後端服務，`foo` 什麼都沒說。

| 領域 | 可用的名字 |
|---|---|
| 後端服務 | `orders-api`、`billing-service`、`auth-gateway` |
| 資料處理 | `content-pipeline`、`etl-nightly`、`report-builder` |
| 前端 | `admin-console`、`storefront-web`、`metrics-dashboard` |
| CLI 工具 | `deploy-cli`、`log-tailer`、`schema-diff` |
| 函式庫 | `retry-utils`、`date-fmt`、`config-loader` |

GitHub 路徑用 `octo-org/orders-api`（`octocat` 與 `octo-org` 是 GitHub 官方文件慣用的
虛構帳號）。

## 人名、帳號、email

- 人名：`alice`、`bob`、`carol`（密碼學文獻的標準角色，讀者一看就知道是範例）
- 中文情境：`小美`、`阿哲`，或直接寫角色「營運人員」「值班工程師」
- email：`alice@example.com`、`dev@example.com`
- 團隊／組織：`平台組`、`Platform Team`、`octo-org`

## 路徑

| 情境 | 寫法 |
|---|---|
| 泛指專案根目錄 | `~/projects/orders-api` 或 `/path/to/orders-api` |
| repo 內相對路徑 | 直接寫相對路徑：`src/handlers/orders.ts` |
| 設定檔位置 | `~/.config/orders-cli/config.toml` |
| 暫存 | `/tmp/orders-export.csv` |

**絕對不要出現 `/Users/<你的名字>/` 或 `/home/<你的名字>/`。** 這是最常漏的一種，
因為貼終端機輸出時會整段帶進來。需要展示指令輸出時，把家目錄縮成 `~`。

## 資料庫與資料

- 資料表：`orders`、`users`、`line_items`、`audit_log`
- 欄位：`order_id`、`created_at`、`status`、`amount_cents`
- 連線字串：`postgres://app:***@db.example.com:5432/orders`
- 假資料：金額用整數（`1200`）、日期用 `2024-01-15` 這種明顯是範例的值

## 內部系統與專有名詞

公司內部的系統代號（引擎名、服務代號、專案代號）**不要用縮寫或改字母的方式處理**。
認得這個代號的人看到縮寫版本一樣認得出來，所以縮寫並沒有真的把來源藏起來。
要改成描述功能的通用說法：

| 別寫 | 改成 |
|---|---|
| 某內部遊戲引擎代號 | `the game engine`／`遊戲引擎框架` |
| 某內部帳務系統代號 | `LegacyBillingService`／`舊版帳務系統` |
| 某內部部署工具代號 | `the deploy tool`／`內部部署工具` |
| 公司 GitLab 群組名 | `octo-org` |

判斷方式：如果把這個詞貼到搜尋引擎，會不會指向你的公司或你的專案？會的話就要換。

## 版本、時間、數字

- 版本號：`1.2.0`、`v2.0.0-rc.1`
- 日期：`2024-01-15`（避免用今天的日期，那等於標記了你是哪一天在寫這份文件）
- 效能數字：用整齊的估計值（`約 200ms`、`每分鐘 1000 筆`），不要貼真實的監控數據——
  那會洩漏系統規模與流量

## 一份自洽的範例世界

需要跨多個段落舉例時，用同一組設定，讀者比較容易把前後對起來：

> `octo-org/orders-api` 是一個處理訂單的後端服務，部署在 `api.example.com`。
> 它讀 `orders` 資料表，由 `alice@example.com` 維護。本機開發時 clone 到
> `~/projects/orders-api`，設定檔放在 `~/.config/orders-cli/config.toml`。

需要第二個服務做對照時，加 `billing-service`；需要第三個時，加 `content-pipeline`。
