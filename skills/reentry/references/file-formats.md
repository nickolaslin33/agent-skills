# 檔案格式

四種產物，每個專案一份，住在 `$REENTRY_ROOT/<專案名>/`（預設 `~/reentry`）。

寫任何一個之前先看這裡。格式是固定的，不要即興發揮——使用者自己隨手指定的線索格式，在文獻裡是所有線索類型中效果最差的一檔。

| 檔案 | 生命週期 | 誰寫 |
|---|---|---|
| `handoff.md` | 每次收工覆蓋 | 人寫，agent 如實記錄 |
| `artifacts.md` | 每次收工覆蓋 | 腳本產原始事實，agent 補功能描述 |
| `debt.md` | 累積 | agent 在第四階段升級 |
| `decisions/*.md` | 累積 | 收工時有值得留的決定才寫 |

---

## `handoff.md`

```markdown
---
project: orders-api
updated: 2026-08-12T23:14:05+08:00
warning: 這批產出你基本沒吸收，四項裡三項跟事實對不上。
---

## 我叫它做什麼，做到哪裡
叫它把第一階段的骨架跟 core 原語做完（clock / ids / config），
還有分層的 import-linter contract。做完了，test_layering 綠的。

## 下一步
第二階段（三個設定載入點：settings / tuning / limits），先做 settings——
把 `.env.example` 的欄位對應成 Settings 類別，寫完跑 `pytest tests/config/`

## 關鍵詞
import-linter contract, core 原語, setup.cfg, Settings

## 不確定的地方
tuning 跟 limits 要不要走同一個載入路徑，第二階段沒寫死

## 我當初記錯的
- 我寫 contract 放在 pyproject.toml，實際在 setup.cfg（import-linter 只讀 setup.cfg/.ini）
- 我說 core 只有 clock 跟 ids，實際還有 config 跟 errors
```

**`updated`** 是時間的權威來源，腳本優先讀它，讀不到才退回檔案 mtime。這很重要——mtime 撐不過複製與 clone，而這個目錄是要進 git 的。

**`warning`** 只在大面積對不上時才出現，其餘情況整個 key 省略或設 `false`。它是一次性的，下次收工覆蓋掉。

**`## 我當初記錯的`** 是存證**，不會出現在回來時的輸出裡**。那些糾正在收工當下已經處理過一輪；回來時該讀的是篩選過的 `debt.md`。

四個內容區塊都是人在第一階段憑記憶寫的。如實記錄，不要潤稿、不要補完、不要換成更精確的說法——他的用詞是他自己的檢索線索。

**唯一的例外是代號。**「`T-3`」「`那個 bug`」「`上次那個問題`」這種只有當下解得開的簡寫要展開成「`T-3`（把訂單重試邏輯抽成獨立的 `retry-utils` 模組）」。這不算潤稿——代號是指標不是線索，三週後它要求你先有脈絡才看得懂，而脈絡正是那時候沒有的東西。看到代號就問使用者展開是什麼，不要自己猜。

---

## `debt.md`

```markdown
# 理解債 — orders-api

- [ ] 為什麼分層契約要帶 allow_indirect_imports = True？
      commit: a3f9c21
      added: 2026-08-12
- [x] 為什麼 domain 層連 store 都不能 import？
      commit: 8b2e104
      added: 2026-08-01
```

**只放機制性的記錯。**「為什麼非這樣不可」講錯了才進；檔名、行數、測試數字記錯不進，那是記憶問題不是理解問題。

**條目是問題，答案不寫**。寫上答案會讓使用者讀一遍就產生「我懂了」的感覺，而那正是這整套要對付的東西。答案留在 `commit` 指的那份 diff 裡。

**`commit` 必須是 SHA，不能是檔案路徑**。`artifacts.md` 每次收工被覆蓋，只有 git 歷史撈得回來。

還完了把 `- [ ]` 改成 `- [x]`，**不要刪除**——已還的紀錄本身是資料。

---

## `artifacts.md`

```markdown
---
project: orders-api
generated: 2026-08-11T22:43:02+08:00
---

## 改了什麼
建了套件骨架與分層目錄，新增 core 的三個原語（時鐘、ID 產生、設定載入）
與錯誤型別，並把分層契約寫成會失敗的測試。動到 setup.cfg——契約只能放那裡。

## 驗證
pytest 11 passed
make lint 全綠（ruff / mypy / import-linter）

## 明細
setup.cfg                        +41 −0
src/orders_api/core/clock.py     +31 −0（新增）
src/orders_api/core/errors.py    +26 −0（新增）
tests/test_layering.py           新增
```

**三節分工不同，不要混：**

| 節 | 誰寫 | 內容 |
|---|---|---|
| `## 改了什麼` | **agent**，看著 diff 寫 | **功能層**——那些檔案是幹嘛的 |
| `## 驗證` | 腳本抓得到就腳本，抓不到 agent 填 | 測試結果、lint 狀態 |
| `## 明細` | `scripts/reentry_artifacts.py` | 原始事實：路徑、增減行數 |

**`## 改了什麼` 是功能層，不是檔案層**。寫「改了 2 個金流流程檔、1 個商品設定檔，新增測試驗證實作」，不要寫「改了 3 個檔（+82 −4）」。

理由是使用者的角色：他**沒有寫這些程式，是他指揮 agent 寫的**。他的記憶痕跡在「我要它做什麼」上，不在檔案路徑上。檔案數量對他不是線索，是一串他從來沒編碼進腦子的資訊。

如果某次改動碰到專案的核心檔案，在這一節特別標出來——「動到了 `store/db.py` 的連線角色」比「改了 5 個檔」有用得多。

**`## 明細` 保留原始事實不是給人讀的**，是讓 `## 改了什麼` 那句有東西可查證。agent 寫功能描述時必須從明細推，不能憑印象編。

**寫值，不寫「完成」**。`## 驗證` 不要出現「已完成」「測試通過」這類詞——回「checked」不需要真的看過。寫「11 passed」、「2 failed，紅的是 test_layering 那兩個」。

回來時印 `## 改了什麼` 跟 `## 驗證`，**不印 `## 明細`**。

---

## `decisions/<日期>-<標題>.md`

```markdown
---
project: orders-api
date: 2026-08-12
promoted: false
---

## 決定
分層契約寫進 setup.cfg，不放 pyproject.toml。

## 排除了什麼
放 pyproject.toml——import-linter 只讀 setup.cfg 跟 .ini，放那裡契約不會生效，
而且失敗方式很安靜：測試會過，但它什麼都沒檢查。

## 後續 todo
- 之後 import-linter 若支援 pyproject 再考慮搬回來

## 技術債
（無）
```

`## 後續 todo` 與 `## 技術債` 是升級判準的機械代理——有其中之一，就代表接手的人需要知道，值得升級進專案自己的 repo。兩個都空的話多半只對本人有意義，留在第一層就好。

`promoted` 記是否已升級。升級是**抄不是搬**，原始版留著。

---

## 空白模板

`assets/templates/` 底下有這四種的空白版本，第一次替某個專案建資料夾時可以直接複製過去。
