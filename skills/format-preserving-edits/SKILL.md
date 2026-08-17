---
name: format-preserving-edits
description: 改既有的設定檔或資料檔時，只動你要動的那幾行，其餘排版原封不動，讓 diff 只剩真正的異動。適用 JSON / YAML / TOML / INI / XML / .env / CSV。只要你正要在既有檔案裡新增一筆設定、刪掉一個 key、改一個參數、批次改多個 config、把大檔拆成小檔或搬設定，就用這個 skill——即使看起來只是改一行。特別是當你想呼叫 json.dump / yaml.dump / ConfigParser.write / xml pretty-print 或任何 parser round-trip 的時候：那些 API 會把整份檔案正規化，製造上千行假 diff，還會吃掉註解與鍵序，務必改用這裡的做法。觸發詞：「不要幫我排版」「維持原本的排版」「照原本的格式」「不要動格式」「diff 太亂」「只改該改的」「preserve formatting」「don't reformat」「keep the existing style」「minimal diff」，以及任何改設定檔 / 改 config / 加一筆資料的請求。
---

# Format-Preserving Edits

## 為什麼這件事重要

設定檔是人維護的，排版是維護者長年累積的閱讀習慣：哪些欄位對齊、區塊之間空幾行、
key 用什麼順序排，都是他們找東西的路標。

一旦你把檔案 `json.load()` 進來再 `json.dump()` 出去，等於用序列化器的品味覆寫了
維護者的品味。**語意可能一模一樣，但 diff 從「我改了 1 行」變成「我改了 5000 行」，
review 的人只能盲簽。** 而且 round-trip 經常無聲地改掉或刪掉內容：註解、鍵序、
非 ASCII 的寫法、`1.0` vs `1`、大整數精度、重複 key。

所以驗收標準有兩條，缺一不可：**語意對** ＋ **diff 形狀對**。

## 鐵則

> Parser 只准用來「讀」和「驗證」，不准用來「寫」。

看到自己要打這些，就停下來換做法：

| 別用 | 為什麼 |
|---|---|
| `json.dump` / `json.dumps` 寫回既有檔 | 重排全檔、`ensure_ascii` 改掉中文的寫法、數字的表示法可能變（`1.0` 寫成 `1`、`1e3` 寫成 `1000.0`） |
| `yaml.dump` / `yaml.safe_dump` | 吃掉全部註解、改引號、重排 key、把 `on/yes` 之類的值改型別 |
| `ConfigParser.write()` | 吃掉註解、小寫化 key、統一 `=` 兩側空白 |
| `ET.tostring` / `minidom.toprettyxml` | 重排縮排、改自閉合標籤寫法、動屬性順序 |
| `prettier` / `black` / `gofmt` 掃過整個檔 | 除非這個 repo 本來就有這個 formatter 在 CI 跑 |
| 「順手把這裡對齊一下」 | 對齊的改動會跟你真正的修改混在同一份 diff 裡，review 的人分不出哪幾行才是重點 |

例外：repo 本身就有 formatter（`.prettierrc`、pre-commit hook、CI 檢查），那就跟著它跑——
這時候「正規化」才是這個 repo 的慣例。動手前先確認：`ls .prettierrc* .editorconfig
.pre-commit-config.yaml` 或看 CI 設定。

## 流程

（以下 `$SKILL_DIR` 指本 skill 的安裝目錄，依你的環境代入實際路徑。）

### 1. 先量格式，不要用猜的

```bash
python3 "$SKILL_DIR"/scripts/sniff_format.py <檔案> [更多檔案...]
```

它會報告：BOM／換行字元／檔尾有沒有換行／縮排字元與階距（含**離群值另外列**）／
空行分段習慣／冒號與逗號後的空白／非 ASCII 是直接寫還是 `\uXXXX`／單行容器數量／
最外層 key 是不是排序過。

**離群值怎麼處理**：檔案是人維護的，一定有例外——多數縮排 4 格，某個區塊 2 格。

- 跟**多數**走，不要學離群值。
- 但如果你要改的內容就在離群區塊**裡面**，跟那個區塊的**局部**慣例走：
  局部一致比全域一致重要，讀的人是連著上下文一起看的。
- **不要順手修正離群值。** 那是另一個 commit 的事，混進來只會讓你的 diff 沒人看得懂。

### 2. 找一筆同類的既有條目當骨架

這是整套做法裡最有效的一招，勝過任何風格推論：要加一個商品，就去找一個已經在
檔案裡的商品；要加一個關卡，就複製一個既有的關卡。骨架、縮排、欄位順序、引號、
對齊全部自動正確，你只要改值。

```bash
S="$SKILL_DIR"/scripts
python3 $S/json_surgery.py keys f.json                      # 這層有哪些 key
python3 $S/json_surgery.py show f.json --key ItemAlpha      # 原文長什麼樣
python3 $S/json_surgery.py clone f.json --key ItemAlpha --to ItemBeta -i
```

`clone` 會原封不動複製那個區塊、只換 key 名，並照檔案原有的空行分段插在後面。
複製完再逐欄改值（用 Edit 工具就好）。

### 3. 動刀：改動量決定用什麼工具

| 情境 | 工具 |
|---|---|
| 改幾個值、加一小段 | **Edit 工具**，直接貼上符合原格式的文字 |
| 需要括號配對才找得到範圍、或同一個 key 在多處出現 | `json_surgery.py`（`--scope` 限定路徑） |
| 同樣的改動要套到 N 個檔 | 寫一支一次性 script **呼叫 `json_surgery` 的函式**，或迴圈跑 CLI |
| YAML / TOML / INI / XML | 見 `references/formats.md`（多半仍是 Edit 工具或行級 script） |

`json_surgery.py` 提供的操作（預設印到 stdout，`-i` 才寫檔；會在寫檔前驗證 JSON 合法）：

```bash
keys    列出某層的 key 與行號          --scope a.b
show    印出某個 key 的原文區塊
range   印出行號範圍（配合 Read/Edit 用）
clone   複製既有區塊成新 key           --key SRC --to DST [--after ANCHOR]
insert  插入區塊                       --after KEY | --before KEY  --block-file f
append  插到該層最後                   --scope a.b --block-file f
replace 換掉整個 key 區塊              --key K --block-file f
remove  刪掉某個 key                   --key K --scope a.b
set     只換 value 原文                --key K --value '"5999"'
```

逗號、尾逗號、區塊間空行、縮排對齊都由工具處理——這幾件事是手工最容易出錯、
而且錯了會讓 JSON 直接壞掉的地方。

**刪除的連鎖效應**：刪掉一筆資料時，順手檢查同一份檔案裡有沒有「因此變成空殼」的
父層（例如某分類底下的項目全刪光了，那個分類 key 也該刪）。這是語意問題，工具不會提醒你。

### 4. 驗收：兩條都要過

```bash
python3 "$SKILL_DIR"/scripts/verify_edit.py <檔案>            # 跟 git HEAD 比
python3 "$SKILL_DIR"/scripts/verify_edit.py old.json new.json
```

它會報 **diff 形狀**（純新增 / 純刪除 / 有增有刪）、**重排噪音**（被刪的行與被加的行
去掉空白後一模一樣 → 那就是重排）、**檔案層級變化**（BOM、換行字元、檔尾換行）、
以及**語意差異**（逐一列出新增 / 刪除 / 改值的路徑）。有重排噪音就 exit 1。

預期的形狀：

- 只新增內容 → `+N / -0`
- 只刪除內容 → `+0 / -N`
- 改值 → `+n / -n`，且 n 等於你改的欄位數
- **出現大量成對增刪 = 你重排了**：`git checkout -- <file>` 從頭來過，別想著補救

回報給使用者時，附上 `git diff --numstat` 的數字。那是最誠實的證據。

## 常見陷阱

- **逗號**：刪掉最後一個成員 → 前一個成員的逗號變成非法尾逗號；插到最後一個成員後面
  → 要幫它補逗號。`json_surgery` 兩種都處理了，手改就得自己顧。
- **檔尾換行**：很多設定檔**沒有**結尾換行（`sniff_format` 會告訴你）。擅自補上就是
  一行假 diff。
- **BOM / CRLF**：Windows 產生的設定檔常見。用 `io.open(..., newline="")` 讀寫，
  不要讓 Python 幫你轉換。
- **非 ASCII**：`ensure_ascii=True` 會把「中」寫成 `\u4e2d`，`ensure_ascii=False` 會把
  `\u4e2d` 寫回「中」。檔案原本用哪一種寫法，換成另一種就是全檔改動。照 `sniff_format`
  報的多數寫法手寫。
  （這份說明本身踩過這個坑：早期版本寫入時 escape 被解讀掉，變成「把中文變成中文」
  這種看不懂的句子。要在文件裡寫這種序列，寫入前後都要驗一次。）
- **重複 key**：JSON 允許、`json.loads` 只留最後一個。round-trip 會靜靜刪掉前面的。
  `json_surgery` 遇到同層重複 key 會直接報錯要你手動處理。
- **數字寫法**：`1.0`、`1e3`、`0.10`、20 位以上的整數——文字層級不動就不會壞。
- **註解**：JSONC / YAML / INI 的註解 round-trip 一定會不見。這是「不要用 parser 寫」
  最硬的理由。
- **對齊**：檔案如果有 `"Type"    : "Weapon"` 這種補空白對齊冒號的寫法，
  新加的 key 也要對齊（`sniff_format` 會標 `⚠ 對齊`）；如果新 key 比現有最長的還長，
  整段對齊要不要重排是**語意決定**，先問使用者。

## 新建檔案的情形

沒有原始排版可保留，但仍然不要憑空發明：**找同目錄的兄弟檔當範本**，
用 `sniff_format.py` 量它，照它寫。同一批新檔彼此之間也要一致。

## 這套做法也適用於

程式碼、Markdown、`.gitignore`、Dockerfile、Makefile……只要那份檔案不是由
formatter 管的，原則都一樣：**只動你要動的那幾行**。

## 參考

- `scripts/sniff_format.py` — 量排版慣例
- `scripts/json_surgery.py` — JSON 文字層級增刪改（可當模組 import）
- `scripts/verify_edit.py` — 驗收語意 + diff 形狀
- `references/formats.md` — YAML / TOML / INI / XML / .env / CSV / properties 的個別做法
