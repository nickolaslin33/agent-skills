---
name: code-reading-page
description: 要把程式碼放進 HTML 網頁或 HTML 文件給人閱讀時，用 Shiki（VS Code 用的同一套語法高亮引擎）把程式碼排成跟編輯器一樣好讀的樣子：依語法上色、關鍵字與函式名加粗、註解與參數用斜體、有行號、字級可調、亮暗主題跟系統設定切換，附複製按鈕。可以輸出完整頁面，也可以輸出片段嵌進既有頁面。只要產出的 HTML 裡會出現程式碼，就用這個 skill，不要手寫 <pre><code> 或自己拼 highlight.js，即使使用者沒說「語法高亮」。觸發情境：把程式碼排成網頁、程式碼好讀一點、做一頁 code review／教學／技術文件、HTML 裡要放程式碼範例、syntax highlight、語法高亮、code block 樣式、像編輯器一樣顯示程式碼。在終端機顯示程式碼、產生程式碼截圖、寫給 GitHub 渲染的 Markdown（GitHub 本身會上色）不適用。
---

# Code Reading Page — 好讀的程式碼頁面

## 這個 skill 做什麼

`scripts/render.mjs` 讀入一或多個程式碼檔，輸出一份 HTML。每個檔案排成一個區塊，區塊上方有檔名、語言、行數與「複製」按鈕。

程式碼的外觀分四個面向處理：

| 面向 | 做法 |
|---|---|
| 顏色 | Shiki 依語法上色。亮色預設 `github-light`，暗色預設 `one-dark-pro`，跟著系統的亮暗設定切換 |
| 大小 | 預設 15px，完整頁面上方有滑桿可在 12–22px 之間調整，瀏覽器會記住上次的設定 |
| 粗細 | 關鍵字（`def`、`return`、`const`、`async`）、函式名、類別名、型別名用粗體 |
| 斜體 | 註解、docstring、參數、`self`／`this`、裝飾器用斜體；`True`、`None`、`null` 這類語言常數用粗斜體 |

粗體與斜體的用意是讓不同角色的程式碼在字形上也能分開，不只靠顏色。色覺辨識較弱的讀者、黑白列印、或兩種顏色剛好很接近的時候，讀者仍然能分辨哪些是關鍵字、哪些是註解。

字型用 JetBrains Mono，它有獨立設計的斜體字形，斜體讀起來不會像把正體硬拉斜。字型從 Google Fonts 載入；離線時會依序改用 SF Mono、Menlo、Consolas。

## 第一次使用：安裝 Shiki

腳本依賴 `shiki`，版本鎖在 `scripts/package.json`。第一次使用前，在 `scripts/` 目錄執行一次安裝（需要 Node 18 以上）：

```bash
cd "$SKILL_DIR/scripts" && npm install
```

（`$SKILL_DIR` 指本 skill 的安裝目錄，依實際安裝位置代入。）

沒安裝就執行時，腳本會印出「找不到 shiki」並以離開碼 2 結束。

## 用法

```bash
node "$SKILL_DIR/scripts/render.mjs" src/room_service.py src/retry.ts -o review.html --title "重試機制 code review"
```

| 參數 | 說明 | 預設 |
|---|---|---|
| `<檔案...>` | 一或多個程式碼檔，依順序排成區塊 | 必填 |
| `-o` | 輸出檔路徑 | `code.html` |
| `--title` | 頁面標題，顯示在 `<title>` 與頁首 | `程式碼` |
| `--lang` | 指定語言，套用到全部輸入檔。檔案沒有副檔名、或副檔名對應錯語言時使用 | 依副檔名判斷 |
| `--light` / `--dark` | 亮色與暗色主題，可用任何 Shiki 內建主題名稱 | `github-light` / `one-dark-pro` |
| `--fragment` | 只輸出片段，給要嵌進既有頁面的情況，見下一節 | 關閉 |

語言依副檔名判斷：`.py` → `python`、`.ts` → `typescript`、`.sh` → `bash`，其餘副檔名如果剛好是 Shiki 支援的語言名稱（例如 `.go`、`.java`、`.sql`）也會直接使用。都對不上時以純文字顯示，不上色，但仍有行號與字型設定。

程式碼來源不是檔案時（例如對話中的一段程式碼），先寫進暫存檔再執行腳本。暫存檔的檔名會顯示在區塊標題上，所以要取一個讀者看得懂的名字，例如 `retry.ts`，不要用 `tmp1.txt`。

## 兩種輸出

**完整頁面（預設）**：一份可以直接開啟的 HTML，包含頁首標題、字級滑桿、亮暗切換按鈕，以及一行說明粗體與斜體各代表什麼。使用者要「一頁程式碼」或要分享給別人看時用這個。

**片段（`--fragment`）**：只有 `<style>`、程式碼區塊與複製按鈕用的 `<script>`，沒有 `<html>`、頁首與字級滑桿。要把程式碼插進已經存在的 HTML 文件（技術文件、報告、教學頁）時用這個，把輸出內容貼到要放程式碼的位置。

片段使用時要注意四件事：

- 樣式的 class 都以 `cv-` 開頭，Shiki 產生的 `.shiki` 與 `.line` 也只在 `.cv-block` 底下套用行號與字級，避免影響原頁面的其他元素。
- 亮暗主題讀 `<html>` 的 `data-theme` 屬性（`light` 或 `dark`）。原頁面沒有設定這個屬性時，跟著系統設定走。原頁面如果用別的方式切換主題，要在切換時同步設定 `document.documentElement.dataset.theme`。
- 字級由 CSS 變數 `--cv-size` 控制，原頁面可以自行覆寫。
- 片段開頭有一行載入 JetBrains Mono 的 `<link>`，原頁面已經載入字型時可以刪掉。

## 調整粗體與斜體的規則

規則寫在 `render.mjs` 的 `STYLE_RULES`。每條規則是一組 TextMate scope 加上字形：

```js
{ scope: ['comment', 'string.quoted.docstring'], fontStyle: 'italic' },
```

`fontStyle` 可以是 `bold`、`italic`、`underline`，或用空白組合（`bold italic`）。規則只改字形，顏色沿用主題原本的設定。

要知道某段程式碼屬於哪個 scope，在 `scripts/` 目錄執行：

```bash
node -e "import('shiki').then(async s => { const t = await s.codeToTokens('async def run(self): pass', { lang: 'python', theme: 'github-light', includeExplanation: true }); for (const tok of t.tokens.flat()) console.log(JSON.stringify(tok.content), tok.explanation.flatMap(e => e.scopes.map(x => x.scopeName)).pop()) })"
```

輸出的每一行是一個 token 與它最內層的 scope，把要調整的 scope 加進 `STYLE_RULES` 即可。

加粗規則刻意排除了運算子（`=`、`+`、`<`、`:`）。運算子在程式碼裡出現的次數很多，全部加粗之後，真正需要被注意的關鍵字反而不突出。

## 做完之後檢查

產生 HTML 之後，在瀏覽器開啟並確認：

1. 亮色與暗色各看一次。完整頁面用右上角的按鈕切換；片段在瀏覽器開發者工具把 `<html>` 的 `data-theme` 改成 `dark`。
2. 關鍵字與函式名是粗體、註解是斜體。如果全部都是正體，通常是字型沒載入，或主題名稱拼錯（拼錯時腳本會直接報錯並列出可用主題）。
3. 長行會出現水平捲軸，不會撐破版面。
4. 按「複製」得到的內容不含行號。

## 範例

`examples/` 有一個 Python 檔與一個 TypeScript 檔，涵蓋類別、裝飾器、async、docstring、泛型與樣板字串，可以用來確認規則調整後的效果：

```bash
node "$SKILL_DIR/scripts/render.mjs" "$SKILL_DIR"/examples/* -o demo.html --title "排版示範"
```
