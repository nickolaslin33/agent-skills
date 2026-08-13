---
name: neutral-examples
description: 寫任何會離開這台機器的東西時，範例素材一律用虛構但一樣具體的名字，不要把手邊的真實專案名、家目錄路徑、email、GitHub 帳號、公司內部系統代號寫進去。用在撰寫 skill（SKILL.md、references/、evals/）、README、公開 repo 的文件、部落格、對外的技術報告、要貼到 issue 或聊天室給別人看的程式碼片段與終端機輸出。特別是被 skill-creator 觸發、或正在寫任何要 push 到公開 repo 的文件時，務必套用——那個情境最容易把真實資訊寫進去，因為 Agent 的 context 裡剛好有當前工作目錄、工作區裡其他專案的名字與這段對話提到的真實專案，需要舉例時它們是最現成的材料。觸發詞：「去識別化」「不要用我的專案當範例」「這要公開」「要 push 到公開 repo」「寫 skill」「寫 README」「整理成對外文件」「匿名化」「這段可以貼出去嗎」「幫我看有沒有夾帶個資」。反過來說，只在本機的筆記、私有 repo 的內部文件、commit 訊息、程式碼註解不適用——那些地方寫真實名稱才是對的。
---

# Neutral Examples — 中性範例

## 為什麼 Agent 會把真實資訊寫進去

Agent 寫文件時，context 裡有當前工作目錄、剛讀過的檔案路徑、工作區裡其他專案的
目錄名、git config 的身分，還有這段對話提到過的真實專案。需要舉例時，這些是最現成
的材料。

問題在於這些字串沒有標記來源。`orders-api` 跟使用者公司內部的服務代號，在 Agent
看來都只是字串。所以不能靠當下判斷，要照下面的規則替換，寫完再用腳本掃一次。

## 先判斷這份檔案會不會離開這台機器

只有會離開的才需要處理。判斷基準是「這份檔案最後會不會被使用者以外的人看到」：

| 要處理 | 不用處理 |
|---|---|
| SKILL.md、references/、evals/ | 本機的暫存筆記、scratchpad |
| 要 push 到公開 repo 的文件 | 私有 repo 的內部設計文件 |
| README、CONTRIBUTING | commit 訊息 |
| 部落格、對外簡報、技術報告 | 程式碼註解、變數命名 |
| 要貼到 issue／聊天室的程式碼與終端機輸出 | 只給自己看的除錯紀錄 |

右欄直接寫真實名稱，不要套用後面的替換規則。內部文件改用假名之後，同事讀的時候
對不上實際的程式碼，反而更難維護。

不確定的時候問一句：這份檔案會被 commit 到哪裡、給誰看？

## 核心原則：換成虛構但一樣具體的名字

比「漏了沒改」更常見的失敗是改過頭：把真實名稱換成 `<你的專案>` 這類佔位符。
識別資訊確實拿掉了，但範例同時失去用處。

| 原文 | 改壞了 | 改對了 |
|---|---|---|
| `cd ~/work/PhoenixTracker && pytest` | `cd 你的專案目錄並執行測試` | `cd ~/projects/orders-api && pytest` |
| 「AtlasBooking 用 Cloudflare Workers 部署」 | 「某些專案會用邊緣運算平台部署」 | 「`orders-api` 用 Cloudflare Workers 部署」 |
| SSH URL 帶真實帳號與 repo 名 | `<你的 repo URL>` | `git@github.com:octo-org/orders-api.git` |

右欄的名字是假的，但格式、長度、結構跟真實情況一樣，讀者可以直接複製來改。

**反面教材也要用虛構名字。** 表格左欄的 `PhoenixTracker`、`AtlasBooking` 就是虛構的。
壞範例一樣是範例，寫真名一樣會把名字帶出去。

替代素材從 `references/placeholder-vocabulary.md` 取，那裡有一組固定的虛構名稱
（`orders-api`、`alice@example.com`、`octo-org`、`192.0.2.0/24`）與完整清單。

網域跟 IP 一定要用 RFC 保留給文件的位址：`example.com`、`192.0.2.0/24`。
不要隨手打 `mycompany.com` 或 `1.2.3.4`，那些真的有人在用，讀者會連到不相干的地方。

## 哪些東西算識別資訊

| 類別 | 例子 |
|---|---|
| 家目錄路徑 | `/Users/<名字>/`、`/home/<名字>/`、`C:\Users\<名字>\` |
| 個人帳號 | GitHub handle、email、git config 的 user.name |
| 專案代號 | 使用者自己的 repo 名、工作區裡其他專案的名字 |
| 公司內部系統 | 引擎代號、服務代號、內部工具名、GitLab 群組名 |
| 公司網域 | 內部網址、公司 email 網域 |
| 環境細節 | 真實 IP、內網主機名、資料庫連線字串、真實的監控數據 |

**公司內部代號不要用縮寫或改字母的方式處理。** 認得這個代號的人（同業、離職同事、
合作廠商）看到縮寫版本一樣認得出來，所以縮寫並沒有真的把資訊藏起來。要改成描述
功能的通用說法：某個內部帳務系統 →「舊版帳務系統」或 `LegacyBillingService`。

判斷方式：把這個詞貼到搜尋引擎，會不會指向使用者的公司或專案？會的話就要換。

## 寫完用腳本掃一次

這支腳本補的就是「Agent 分不出來」這個缺口。它從四個地方蒐集識別資訊：git config 的
local 與 global 身分、git remote、家目錄名，以及**工作區裡其他專案的目錄名**，
再拿這份清單比對檔案內容。

一般的 secret scanner 找的是 API key 那種有固定形狀的字串，抓不到專案代號。

```bash
python3 "$SKILL_DIR"/scripts/scan_identifiers.py <檔案> [更多檔案...]

# 只想看它從環境偵測到哪些識別資訊
python3 "$SKILL_DIR"/scripts/scan_identifiers.py --list-only
```

（`$SKILL_DIR` 指本 skill 的安裝目錄，依實際安裝位置代入。）

輸出長這樣：

```
skills/some-skill/evals/evals.json — 2 處命中（HIGH 2）
  HIGH   :8    「PhoenixTracker」 ← 工作區裡的其他專案
  HIGH   :16   「AtlasBooking」 ← 工作區裡的其他專案
```

有 HIGH 命中時離開碼是 1，可以用在 pre-commit hook 裡當作擋下 commit 的條件。

**兩個等級要分開看：**

- `HIGH` — 家目錄路徑、email、使用者名稱、工作區裡其他專案的名字。這些幾乎都該換掉。
- `REVIEW` — repo 自己的名字、remote 的帳號。**這些常常是合理的**，例如安裝說明裡的
  `npx skills add octo-org/orders-api` 本來就該寫真名，不然使用者裝不起來。要人看一眼再決定。

看命中原因決定要不要採信。寫「工作區裡的其他專案」「git email」的是從環境問出來的，
可信度高。寫「家目錄路徑」「email 位址」的是泛用規則，抓得廣但分不出真假。

最常見的誤報是刻意做髒的測試 fixture，它會被家目錄與 email 那兩條泛用規則掃到。
確認裡面的名字是虛構的即可，不用改。

## 不要過度清理

清過頭比沒清乾淨更難發現。沒清乾淨掃描腳本會報出來，清過頭不會，要等讀者照著做
卻做不出來才知道。以下這些不要動：

- **安裝指令裡的 repo 路徑保留真實值。** 使用者要照著它安裝，換掉就裝不起來。
- **公開套件與技術名稱保留。** `Cloudflare Workers`、`pytest`、`Redis`、`FastAPI`
  本來就是公開資訊，換掉不會多保護什麼，只會讓讀者看不懂在講哪個工具。
- **這份 repo 自己的名字保留。** 它出現在自己的 README 與安裝說明裡是必要的。
- **技術決策的理由保留。**「因為要跑在 Cloudflare Workers 上所以不能用 Node API」
  講的是技術限制，不會透露使用者是誰、在哪工作。

要換的只有「指向某個特定的人、某台特定機器、某個非公開組織」的那些字。

## 收尾檢查

寫完對外文件後：

1. 跑一次 `scan_identifiers.py`，確認沒有 HIGH 命中。
2. 看一遍 REVIEW 命中，確認每一筆留下來都有理由。
3. 檢查範例是否仍然具體，有沒有在清理過程中變成 `<你的專案>` 這類佔位符。
4. 如果文件裡有多個範例，確認它們用的是同一組虛構名稱，前後對得起來。
