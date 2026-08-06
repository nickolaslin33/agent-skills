# agent-skills

跨 agent 可攜的個人 Agent Skills（[Agent Skills 開放標準](https://agentskills.io) SKILL.md 格式）。

## Skills

| Skill | 用途 |
|---|---|
| [github-prior-art](skills/github-prior-art/SKILL.md) | 規劃新功能或架構前，先到 GitHub 做開源先例調查，產出調查報告再進入規劃 |
| [format-preserving-edits](skills/format-preserving-edits/SKILL.md) | 修改既有設定檔/資料檔時保留原排版，用文字層級外科手術讓 diff 只剩真正的異動 |

## 安裝

```bash
# 互動式選擇要安裝到哪些 agent
npx skills add nickolaslin33/agent-skills@github-prior-art

# 更新
npx skills update
```

## License

MIT
