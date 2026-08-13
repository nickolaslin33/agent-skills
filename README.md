# agent-skills

跨 agent 可攜的個人 Agent Skills（[Agent Skills 開放標準](https://agentskills.io) SKILL.md 格式）。

## Skills

| Skill | 用途 |
|---|---|
| [github-prior-art](skills/github-prior-art/SKILL.md) | 規劃新功能或架構前，先到 GitHub 做開源先例調查，產出調查報告再進入規劃 |
| [format-preserving-edits](skills/format-preserving-edits/SKILL.md) | 修改既有設定檔/資料檔時保留原排版，用文字層級外科手術讓 diff 只剩真正的異動 |
| [reentry](skills/reentry/README.md) | 請 AI agent 做完一批工作後，收工留下足以重建當時狀況的紀錄，回來時照固定順序讀回來；處理的是尚未補足的理解，不只是忘記 |
| [clear-technical-chinese](skills/clear-technical-chinese/SKILL.md) | 用讀者第一次看就懂的繁體中文寫作；技術文件模式求完整可執行，日常回覆模式求簡潔直接 |
| [neutral-examples](skills/neutral-examples/SKILL.md) | 寫對外文件時範例改用虛構但一樣具體的素材，附掃描腳本揪出夾帶的真實專案名、路徑與帳號 |

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

# 更新
npx skills update
```

## License

MIT
