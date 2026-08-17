# 先例調查：發問時順便糾正英文（my-english-cpr）

調查日期：2026-08-17
調查者：Claude Code（gh-shoulders skill）

## 1. 需求摘要與調查範圍

要做的 skill：使用者用中文工作，句子裡偶爾夾英文單字、偶爾整句用英文發問。skill 在回答完問題之後，順便指出英文的問題，目的是長期把英文練起來。

抽出的通用成分有兩塊，開源世界的成熟度差很多：

1. **偵測錯誤**：哪裡錯、錯在哪一類。學術界稱為 GEC（Grammatical Error Correction），有完整的資料集、模型與評測工具。
2. **設計回饋**：糾錯要放在哪、講多少、同一個錯反覆出現時怎麼處理，才不會被讀者跳過。

第 1 塊有大量先例但全部在模型層，對這個 skill 沒有直接用處——判斷錯誤這件事語言模型本身就會。第 2 塊才是這個 skill 的實際內容，而**這一塊在 GitHub 上幾乎找不到先例**，只有 skills 生態裡有一個。

## 2. 搜尋紀錄

管道：`npx skills find`（skills 生態）＋ `gh` CLI repo/code 搜尋（GitHub 全站）。

| 關鍵字 | 管道 | 結果 |
|---|---|---|
| `english grammar` | skills | 5 命中 |
| `grammar correction` | skills | 5 命中（最高 2.2K installs） |
| `language learning` | skills | 5 命中 |
| `writing feedback` | skills | 5 命中（多數不相關） |
| `grammatical error correction` | repo | 10 命中，**全是學術研究** |
| `LLM grammar correction prompt english learner` | repo | **零結果** |
| `language learning while chatting correction assistant` | repo | **零結果** |
| `corrective feedback language learner` | repo | **零結果** |
| `awesome english learning resources` | repo | **零結果** |
| `"English Corrections" SKILL.md` | code | **零結果** |
| `correct my grammar while answering prompt` | code | **零結果** |

**五組零結果集中在同一件事上**：把「糾錯」當成對話的附帶產物、而不是一個專門的校閱任務。GitHub 上找不到這種設計。GEC 那條線雖然命中很多，但那些專案解的是「怎麼自動偵測錯誤」，在語言模型時代已經不是瓶頸。

社群行話的探測結果：學術界用 GEC，二語習得研究用 corrective feedback、recast、metalinguistic feedback。前者在 GitHub 上有大量程式碼，後者一個也沒有——那些概念留在論文裡，沒有人做成 prompt 或工具。

## 3. 候選比較表

| 專案 | 安裝數 / stars | License | 定位 |
|---|---|---|---|
| **[tianmind-studio/english-coach](https://github.com/tianmind-studio/english-coach)** | 77 installs / ★14 | **MIT** | **對話中順便教英文，結構與本需求高度重疊** |
| [phuryn/pm-skills@grammar-check](https://github.com/phuryn/pm-skills) | 2.2K installs / ★25338 | MIT | 吃 `$OBJECTIVE` 與 `$TEXT` 參數的專門校閱工具，on-demand |
| [jackjin1997/clawforge@language-learning](https://github.com/jackjin1997/clawforge) | 544 installs / ★12 | **無** | 完整語言家教，支援上百種語言、有課程規劃 |
| [membranedev/application-skills@grammarly](https://github.com/membranedev/application-skills) | 92 installs / ★257 | **無** | 模仿 Grammarly 的校閱 |
| [wentorai/research-plugins@academic-writing-refiner](https://github.com/wentorai/research-plugins) | 58 installs | — | 學術寫作潤飾 |
| [dowonkang/agents@english-proofreading](https://github.com/dowonkang/agents) | 54 installs / ★0 | **無** | 校對 |
| [williacj/claude-skills@grammar](https://github.com/williacj/claude-skills) | 38 installs / ★3 | **無** | 文法 |
| [grammarly/gector](https://github.com/grammarly/gector) | ★972 | Apache-2.0 | GECToR 論文實作（模型層，非回饋設計） |

安裝數最高的 `grammar-check`（2.2K）不是同一類東西——它要你把文字跟目標交給它校閱，屬於「校閱工具」；本需求要的是「工作時的背景糾錯」。這正是 gh-shoulders 那條「star 數只用來排序，不用來排除」在起作用的地方：最貼合的是 77 installs、14 stars 的那個。

## 4. 深讀解析：tianmind-studio/english-coach

唯一值得深讀的一份。它的開場句就把定位講清楚了：

> Every response has two jobs: **answer the question** and **teach English**.
> Answer the user's question naturally. **Do your actual job first — the English coaching is a bonus, not the main event.**

**結構分三部分**：Part 1 正常回答、Part 2 糾錯（用 `---` 隔開、標題 `English Corrections:`）、Part 3 每次教一個新東西。

**糾錯格式**：

```
~~original text~~ → **corrected text**
**[Category]** Brief explanation
```

**錯誤分五類當標籤**，這張表很好用：

| Tag | 意思 |
|---|---|
| Spelling | 拼錯或用錯字 |
| Grammar | 結構、時態、一致性 |
| Word Choice | 講得通但不自然 |
| Punctuation | 空格、大小寫、標點 |
| Expression | 給一個母語者的說法 |

**跟本需求一致的規則**（可以直接借）：

- `One line per mistake. No lectures.`
- `Max 5 corrections per response. If more exist, fix the most important ones and note "a few minor issues omitted."`
- `When the same mistake repeats across messages, flag it as a recurring pattern so the user pays extra attention.` — 同一個錯反覆出現時要加強提醒，跟本需求的決定完全一致，而且是獨立想到的。
- Difficulty Adaptation：使用者基本錯誤變少之後，重心從拼字文法移到自然度與語感。

**跟本需求衝突的五處**（要改掉）：

1. **它糾拼字與標點**（`dose → does`、`i → I`）。本需求明確不糾拼字失誤與單複數——夾雜單字時使用者是在打中文，那些是打字失誤，不是英文能力的問題。
2. **它有 Part 3「每次教一個新東西」**。本需求沒有這一項；每次硬塞一個片語或文法 tip 會讓那段比答案還長。
3. **它的語氣是鼓勵型**（`Celebrate progress`、`No errors — nice work!`）。使用者其他 style 明確禁止慶祝與空話，沒問題就整段不出現。
4. **它沒有區分「夾雜單字」與「整句英文」**。因為它假設使用者全程用英文練習對話，而本需求的實際情境是中文工作、偶爾夾英文。這是最根本的前提差異，也是本需求最重要的那條規則的來源。
5. **它是 on-demand**（description 寫 `Invoke when the user wants to practice English`）。本需求要的是每次都生效。

## 5. 借用判定

| 項目 | 來源 | License | 判定 |
|---|---|---|---|
| 三段式結構（先答問題、再糾錯） | english-coach | MIT | **僅參考思路**，本需求只要兩段 |
| 五類錯誤標籤 | english-coach | MIT | **可移植**，註明出處；本需求要刪掉 Spelling 與 Punctuation |
| `原文 → 改寫` 加分類標籤的格式 | english-coach | MIT | **可移植**，註明出處 |
| 「一行一個錯、不要說教」 | english-coach | MIT | **僅參考思路** |
| 糾錯數量上限加「其餘省略」的註記 | english-coach | MIT | **僅參考思路**，本需求上限是 3 不是 5 |
| 重複出現時標記為 recurring pattern | english-coach | MIT | **僅參考思路**，兩邊獨立得出同一結論 |
| 難度隨程度調整 | english-coach | MIT | **僅參考思路** |
| GEC 模型與資料集 | grammarly/gector 等 | Apache-2.0 / CC-BY / GPL | **不使用**，那是模型層，語言模型本身就做得到 |
| 其他五個 skills 生態的候選 | 多數**無 LICENSE** | 視同保留所有權利 | **只參考思路**，實際上定位不同、沒有可借的東西 |

## 6. 建議方向與理由

**以 english-coach 的結構為骨架，改掉五處，不要從零設計。** 它已經解決了兩個非顯而易見的問題：糾錯要放在回答之後（不能搶正事的位置），以及重複出現的錯要加強而不是淡化。這兩點本需求各自也想到了，先例確認了方向。

**真正要自己設計的只有一塊：夾雜單字與整句英文的兩層規則。** english-coach 沒有這個概念，因為它假設使用者在練習對話。本需求的情境是中文工作環境，這帶出兩條先例裡沒有的規則：

- 夾在中文裡的英文單字只檢查**選詞**（講「封包」用了 `message` 而不是 `packet`），拼字失誤與單複數放過。
- 整句英文才做完整檢查。

**兩處要比先例更嚴**：

- 沒有錯誤時什麼都不寫，不要「No errors — nice work!」。固定佔一格的東西會退化成每次跳過的噪音。
- 不做 Part 3「每次教一個新東西」。糾錯本身已經是學習材料，額外塞入的內容會讓這一段長到被略過。

**一處要處理先例沒碰到的邊界情況**：英文錯誤造成語意不明時（例如 `which way` 分不出指方法還是方向），不能等到最末才糾——那時要在回答之前先問清楚，因為錯誤已經影響到正事。

## 7. 未查證事項與侷限

- **沒有實測 english-coach**。結論來自讀它的 SKILL.md，沒有安裝跑過。它的 Part 3 到底會不會讓回覆變得太長，只是推論。
- **只深讀一個候選**。其餘五個 skills 生態的候選只看了 skills.sh 頁面的摘要，沒有讀原始碼。判斷它們「定位不同」的依據是描述與參數設計，可能漏掉細節。
- **二語習得的研究文獻沒查**。corrective feedback 有數十年的實證研究（哪種糾錯方式讓學習者真的記住），那些結論留在論文裡、GitHub 上搜不到。這次沒有去查學術文獻，所以「重複出現時加強提醒」這類設計目前只有兩份 prompt 的共識當依據，沒有研究支撐。
- **GEC 那條線刻意沒有深入**。判斷是語言模型本身的偵測能力已經足夠，不需要外接模型。這個判斷沒有實測驗證。
- **五組零結果可能是關鍵字不夠**。「順便糾錯」這個概念如果社群有另一個說法（類似 GEC 對應學術界、ADHD 對應注意力那樣的行話），我可能沒找到。
