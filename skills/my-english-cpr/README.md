# my-english-cpr — 救救破英文

回答完你的問題之後，順便指出你英文可以改進的地方。夾在中文裡的英文單字只檢查選詞，整句英文才做完整的文法、句型、選詞檢查。

**你可能會反對的三件事**：

- **只安裝 skill 不會每次生效。** 要每次都生效得在 `CLAUDE.md` 加一段，做法見下一節。這件事最容易被跳過，而跳過的後果是你以為裝好了、實際上大半時候不會觸發。
- **拼字失誤不糾。** 你打 `clinet`、`shouder` 都會被放過，只糾選錯詞（講「封包」用了 `message` 而不是 `packet`）。理由是手指打錯不是英文能力的問題。
- **沒有鼓勵語氣，沒有東西講就整段不出現。** 不會寫「這句很好」，也不會每次附一個新片語。固定佔一格的區塊會變成你每次跳過的東西。

## 兩種生效方式，只裝 skill 會漏

| 做法 | 行為 | 什麼時候會漏 |
|---|---|---|
| 只安裝 skill | **on-demand**：你打 `/my-english-cpr` 才一定生效。不打的話，Claude 讀 `description` 自己判斷要不要用 | 常漏。你的訊息看起來像單純的技術問題時，Claude 傾向直接回答、不去叫這個 skill |
| 安裝 skill ＋ `CLAUDE.md` 加一段 | **always-on**：每個 session 自動載入那段指示，Claude 每輪都會想到要檢查 | 幾乎不漏 |

要 always-on 的話，在 `CLAUDE.md` 加這段：

```markdown
## 英文糾錯

我的訊息裡出現英文單字或英文句子時，回答完我的問題之後，照
`skills/my-english-cpr/SKILL.md` 的規則在回覆最末做英文糾錯。我沒有要求也要做。
```

`CLAUDE.md` 只放這段觸發規則，完整的糾錯方法留在 `SKILL.md`。這樣「每次都生效」由 `CLAUDE.md` 保證，一百多行細節不必每輪都佔 context。

skill 被載入一次之後，內容會留在該 session 後續的每一輪，所以 always-on 的實際成本只有 `CLAUDE.md` 那三行，不是每輪重新載入整份 `SKILL.md`。

## 安裝

```bash
npx skills add nickolaslin33/agent-skills@my-english-cpr
```

## 哪些東西不糾

- 明顯的打字失誤：`clinet`、`shouder`。
- 刻意的簡略寫法：`pls`、`ty`、`btw`、省掉主詞的 `looks good`。那些在真實的技術溝通裡本來就通行。
- 你引用別人寫的英文：貼過來的錯誤訊息、文件片段、別人的訊息。
- 程式碼、指令、檔名、變數名、API 名稱裡的英文。
- 專有名詞與產品名。

單複數分情況：夾在中文裡的單字不糾，整句英文要糾（那屬於文法）。

## 英文錯誤讓 Claude 看不懂你要問什麼的時候

糾錯平常放回覆最末，但這種情況例外——等到最末就太晚了，Claude 會先照猜的答一輪。

那時候 Claude 會在回答之前先問你是哪個意思，並指出是哪個字造成兩種讀法。例如「Please check the log file in the folder I created」有兩種讀法：你建的是資料夾，還是那個 log 檔。問清楚之後才回答，糾錯照樣放最末。

## 設計來源與改掉的地方

規則的骨架參考 [tianmind-studio/english-coach](https://github.com/tianmind-studio/english-coach)（MIT），那份同樣採「先回答問題、糾錯當附帶」的結構，錯誤分類標籤也取自那裡。

改掉五處：不糾拼字與標點、沒有「每次教一個新東西」的段落、沒有鼓勵性語氣、糾錯上限從五條改成三條、以及最主要的差異——區分「夾在中文裡的單字」與「整句英文」。`english-coach` 假設使用者全程用英文練習對話，這份假設的是中文工作環境偶爾夾英文，前提不同會推出不同的規則。

完整的先例調查在 `docs/prior-art/my-english-cpr.md`，內容包含搜過的關鍵字、五組零結果、候選比較表與 license 判定。
