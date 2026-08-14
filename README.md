# agent-skills

跨 agent 可攜的個人 Agent Skills（[Agent Skills 開放標準](https://agentskills.io) SKILL.md 格式）。

## Skills

| Skill | 用途 |
|---|---|
| [github-prior-art](skills/github-prior-art/SKILL.md) | 規劃新功能或架構前，先到 GitHub 做開源先例調查，產出調查報告再進入規劃 |
| [format-preserving-edits](skills/format-preserving-edits/SKILL.md) | 修改既有設定檔/資料檔時保留原排版，用文字層級外科手術讓 diff 只剩真正的異動 |
| [reentry](skills/reentry/README.md) | 請 AI agent 做完一批工作後，收工留下足以重建當時狀況的紀錄，回來時照固定順序讀回來；處理的是尚未補足的理解，不只是忘記 |
| [clear-technical-chinese](skills/clear-technical-chinese/SKILL.md) | 用讀者第一次看就懂的繁體中文寫作，並清掉「不是 A，而是 B」這類看起來在給洞見、實際沒給內容的句型；改別人的草稿時另有一條：事實、數字與但書不准動 |
| [neutral-examples](skills/neutral-examples/SKILL.md) | 寫對外文件時範例改用虛構但一樣具體的素材，附掃描腳本揪出夾帶的真實專案名、路徑與帳號 |
| [eli-adhd-5](skills/eli-adhd-5/SKILL.md) | 寫東西給沒空看的工程師。回報工作時開頭三行講做了什麼、還能不能跑、可能會被反對的決定；寫 README／設計文件／PR 描述時換成這是什麼、現在能不能信、可能會被反對的設計決定。只有指名才觸發 |

`eli-adhd-5` 用了 `disable-model-invocation` 這個 Claude Code 擴充欄位來關掉自動觸發。標準相容的 runtime 會忽略它，在別的 agent 上它會變成可自動觸發，靠 `description` 勸退。要上傳到 claude.ai 或用 Skills API 打包時，先手動移掉那一行。其餘 skill 都只用標準欄位。

## 安裝

```bash
# 互動式選擇要安裝的 skill 與 agent
npx skills add nickolaslin33/agent-skills

# 或指定單一 skill
npx skills add nickolaslin33/agent-skills@github-prior-art
npx skills add nickolaslin33/agent-skills@format-preserving-edits
npx skills add nickolaslin33/agent-skills@reentry
npx skills add nickolaslin33/agent-skills@clear-technical-chinese
npx skills add nickolaslin33/agent-skills@neutral-examples
npx skills add nickolaslin33/agent-skills@eli-adhd-5

# 更新
npx skills update
```

## License

MIT
