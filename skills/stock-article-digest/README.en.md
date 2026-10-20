# stock-article-digest

[中文](README.md)

Give an AI agent an article about Taiwan or US stocks, and it turns the article into a Markdown note with a fixed format. The source can be a news story, a blog post, a PTT Stock board thread, or an earnings-call write-up. You can pass a URL, a saved HTML file, or plain text.

Each note starts with YAML front matter that a program can read: the tickers mentioned, the sectors, and the tags. Because the format never changes, a single command can find every note that mentions a company after you have saved a few hundred of them:

```bash
grep -l 'TWO:3324' stock-notes/*.md
```

Most rules in this skill guard against one thing: the model making things up. An invented EPS figure or a misremembered ticker cannot be picked out once it sits among real data. So every ticker is checked against an official list, financial figures come only from the article, and any company the AI adds on its own is marked `補充` (added).

**Three things you might object to:**

- **It adds no analysis and no advice.** A note records only what the author said. Self-posed Q&A, further reading, and investment advice are left out, and the validator rejects them. The one exception: the supply-chain table may list companies the article did not mention, but they are marked `補充`.
- **Tags must come from a fixed vocabulary.** The list is in `references/tag-vocabulary.md` and currently holds 45 sectors and 185 tags. You can use a word that is not on the list, but it must also go into `new_tags` so you can decide later whether to adopt it. This is more work. In return, a search for `HBM` does not miss the notes that spelled it out as 高頻寬記憶體.
- **Ticker checks need a network connection.** The official lists download on first use and refresh once a day. Offline, the scripts reuse the old cache. With no cache at all, tickers cannot be checked, and the validator warns you.

The skill instructions and the notes are written in Traditional Chinese.

## Install

```bash
npx skills add nickolaslin33/agent-skills@stock-article-digest
```

Requires Python 3. The three scripts use only the standard library, so there is nothing else to install.

No setup is needed. The skill triggers when you share a stock article URL and ask for a summary (for example 整理這篇 or 這篇在講什麼). You can also type `/stock-article-digest`.

## Two modes

| Mode | How to trigger | Output |
|---|---|---|
| `digest` | Default | 3 to 5 key points; other sections kept short |
| `full` | Write 完整轉換 ("full conversion") in your message | Unlimited key points, plus a 逐段整理 section that keeps every argument, figure, and example in the article's order |

## What a note looks like

Every note has four fixed sections: 核心摘要 (key points), 產業鏈與概念股 (supply chain and related stocks), 財務數據 (financials), and 市場情緒與留言 (sentiment and comments). A section with nothing to report stays in the note with the line 本文未提及 ("not mentioned in the article"). That way a program can tell an empty section from a missing one.

The tickers below are real. The figures and events are made up:

```markdown
---
date: 2026-03-02
date_from: json-ld:datePublished
processed: 2026-03-03
title: "散熱族群法說會整理：液冷滲透率上修"
source: https://example.com/news/12345
mode: digest
tickers:
  - {code: "TW:3017", name: 奇鋐, origin: 原文, verified: listed, industry: 電腦及週邊設備業}
  - {code: "TWO:3324", name: 雙鴻, origin: 原文, verified: listed, industry: 其他電子業}
  - {code: "US:NVDA", name: 輝達, origin: 補充, verified: listed}
sectors: [散熱, AI伺服器]
tags: [液冷, 法說會]
new_tags: []
---

## 核心摘要

- 兩家散熱廠都上修今年液冷產品的營收占比，奇鋐 [TW:3017] 從兩成調到三成。

## 財務數據

| 公司 | 項目 | 數值 | 期間 | 原文依據 | 備註 |
| --- | --- | --- | --- | --- | --- |
| 雙鴻 [TWO:3324] | 毛利率 | 25.1% | 2025Q4 | 「第四季毛利率 25.1%」 | 季增 1.2 個百分點 |
```

Every row in the financials table quotes a short piece of the article as its source. If the article does not give a quarter or an EPS figure, the AI must not fill it in, even if it remembers the number.

`date` is the article's publication date. The processing date goes in `processed`. When no publication date can be found, `date` is `unknown`; it is never filled with today's date, because then old articles could not be told apart from new ones.

## How tickers are checked

| Market | Format | Checked against |
|---|---|---|
| TWSE (listed) | `TW:2330` | TWSE OpenAPI |
| TPEx (OTC) | `TWO:3324` | TPEx OpenAPI |
| TPEx emerging stocks | `TWE:3097` | TPEx OpenAPI |
| US | `US:NVDA` | SEC `company_tickers.json` |
| Japan, Korea, Hong Kong | `JP:8035`, `KR:005930`, `HK:0700` | No official list; format only |

Each company also carries a `verified` value that says how far the ticker can be trusted:

| `verified` | Meaning |
|---|---|
| `listed` | Found in the official list, and the short name matches |
| `delisted` | No longer listed; the ticker is the one it used before delisting |
| `not-found` | Not found; the code is `?`, as in `TW:?`. Unlisted companies use this too |
| `format-only` | The market has no official list, or it is a Taiwan ETF; only the format is checked |

TWSE and TPEx are the easiest to mix up. 雙鴻 trades on TPEx as `TWO:3324`; write `TW:3324` and the validator tells you the market is wrong. Official short names often use 臺 instead of 台 (臺慶科), and lookups accept either.

Companies delisted from TWSE can be checked against an official list. TPEx publishes no list of delisted companies, so the validator asks you to confirm those tickers yourself.

## Saving and validation

Notes are saved to `$STOCK_DIGEST_DIR`, or to `stock-notes/` under the current working directory if it is not set. File names follow `<date>-<first 30 or so characters of the title>.md`.

After saving, the AI runs `validate.py`. It checks that:

- every front matter field is present and correctly written
- every ticker is in the official list, with a matching short name and industry
- every `[market:code]` in the body appears in `tickers`, and every company in `tickers` appears in the body
- every tag is in the vocabulary, or else listed in `new_tags`
- every row of the financials table quotes its source
- no forbidden section, such as further reading, is present

The AI fixes errors until the note passes. It passes warnings on to you in its reply, for example tickers it could not find or new tags.

## Running the scripts yourself

```bash
# Look up tickers; pass several names or codes at once
python3 scripts/tickers.py lookup 台積電 雙鴻 NVDA 3324

# Re-download the official lists now
python3 scripts/tickers.py update

# Extract a web page to JSON
python3 scripts/extract.py https://example.com/news/12345
python3 scripts/extract.py saved-page.html

# Validate a note; exits 0 on success, 1 on errors
python3 scripts/validate.py stock-notes/2026-03-02-散熱族群法說會整理.md
```

| Environment variable | Purpose | Default |
|---|---|---|
| `STOCK_DIGEST_DIR` | Folder for saved notes | `./stock-notes/` |
| `STOCK_DIGEST_CACHE` | Cache for the official lists | `~/.cache/stock-article-digest/` |

Some Python installs are not wired to the system certificate store, so HTTPS verification fails. The scripts then download with `curl` instead. They never turn certificate verification off.

## Limitations

- **The US list has English names only.** Look up 美光 as `Micron` or `MU`. The AI does this on its own; keep it in mind when you run lookups by hand.
- **Comments are often missing.** Many sites load comments after the page loads, so fetching the URL does not get them. If you want comments, expand them in your browser, save the page source, and give that file to the AI.
- **Pages behind a login cannot be fetched.** Log in in your browser and save the page source instead.
- **Only five markets get tickers: Taiwan, US, Japan, Korea, Hong Kong.** Companies listed elsewhere (China A-shares, Europe) get no ticker; the body gives the company name and where it is listed.
- **Official industry codes are coarse.** 奇鋐 makes thermal parts, but its official industry is 電腦及週邊設備業 (computers and peripherals). So `industry` only catches gross errors, such as tagging a food company as a thermal stock.

## Full rules

`SKILL.md` holds the full workflow for the AI, including how to write each field, what to do when a ticker cannot be found, and the file naming rules.
