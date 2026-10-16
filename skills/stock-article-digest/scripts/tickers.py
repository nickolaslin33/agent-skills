#!/usr/bin/env python3
"""用官方清單把公司名稱或代號查成標準代號。

資料來源（皆免 API key）：
  上市  TWSE OpenAPI  t187ap03_L
  上櫃  TPEx OpenAPI  mopsfin_t187ap03_O
  美股  SEC           company_tickers.json

清單快取在 $STOCK_DIGEST_CACHE（預設 ~/.cache/stock-article-digest/），
超過一天自動重抓；抓不到就沿用舊快取並在 warnings 註明。

用法：
  tickers.py lookup 台積電 奇鋐 NVDA 3324
  tickers.py update
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SOURCES = {
    "TW": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
    "TWO": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
    "US": "https://www.sec.gov/files/company_tickers.json",
}
# SEC 要求 User-Agent 帶聯絡方式，沒帶會回 403
USER_AGENT = "stock-article-digest/1.0 (personal research; contact@example.com)"
MAX_AGE = 24 * 3600

# TWSE / TPEx 共用的產業別代碼
INDUSTRY = {
    "01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維",
    "05": "電機機械", "06": "電器電纜", "08": "玻璃陶瓷", "09": "造紙工業",
    "10": "鋼鐵工業", "11": "橡膠工業", "12": "汽車工業", "14": "建材營造業",
    "15": "航運業", "16": "觀光餐旅", "17": "金融保險業", "18": "貿易百貨業",
    "19": "綜合", "20": "其他業", "21": "化學工業", "22": "生技醫療業",
    "23": "油電燃氣業", "24": "半導體業", "25": "電腦及週邊設備業",
    "26": "光電業", "27": "通信網路業", "28": "電子零組件業",
    "29": "電子通路業", "30": "資訊服務業", "31": "其他電子業",
    "32": "文化創意業", "33": "農業科技業", "34": "電子商務",
    "35": "綠能環保", "36": "數位雲端", "37": "運動休閒", "38": "居家生活",
    "91": "存託憑證",
}


def cache_dir() -> Path:
    d = os.environ.get("STOCK_DIGEST_CACHE")
    return Path(d) if d else Path.home() / ".cache" / "stock-article-digest"


def fetch_bytes(url: str, user_agent: str = USER_AGENT) -> bytes:
    """先用 urllib；憑證驗證失敗時退回 curl。

    有些 Python 安裝沒接上系統憑證庫（或網路上有 HTTPS 代理），
    curl 走系統憑證庫通常抓得到。不關掉憑證驗證。
    """
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" not in str(e):
            raise
        out = subprocess.run(["curl", "-sSfL", "-m", "30", "-A", user_agent, url],
                             capture_output=True, check=True)
        return out.stdout


def fetch(url: str):
    return json.loads(fetch_bytes(url))


def normalize(market: str, raw) -> list:
    rows = []
    if market == "TW":
        for r in raw:
            rows.append({
                "code": r["公司代號"].strip(),
                "short": r["公司簡稱"].strip(),
                "name": r["公司名稱"].strip(),
                "industry": INDUSTRY.get(r["產業別"].strip(), r["產業別"].strip()),
            })
    elif market == "TWO":
        for r in raw:
            rows.append({
                "code": r["SecuritiesCompanyCode"].strip(),
                "short": r["CompanyAbbreviation"].strip(),
                "name": r["CompanyName"].strip(),
                "industry": INDUSTRY.get(r["SecuritiesIndustryCode"].strip(),
                                         r["SecuritiesIndustryCode"].strip()),
            })
    else:  # US
        for r in raw.values():
            rows.append({
                "code": r["ticker"].upper(),
                "short": r["ticker"].upper(),
                "name": r["title"],
                "industry": None,  # SEC 清單沒有產業別
            })
    return rows


def load(force: bool = False) -> tuple[dict, list]:
    """回傳 ({market: rows}, warnings)。"""
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    data, warnings = {}, []
    for market, url in SOURCES.items():
        path = d / f"{market}.json"
        stale = not path.exists() or time.time() - path.stat().st_mtime > MAX_AGE
        if force or stale:
            try:
                rows = normalize(market, fetch(url))
                path.write_text(json.dumps(rows, ensure_ascii=False))
            except Exception as e:  # 網路失敗就退回舊快取
                if not path.exists():
                    warnings.append(f"{market} 清單抓取失敗且沒有快取：{e}")
                    data[market] = []
                    continue
                warnings.append(f"{market} 清單抓取失敗，沿用舊快取：{e}")
        data[market] = json.loads(path.read_text())
    return data, warnings


def lookup(query: str, data: dict) -> list:
    """回傳所有可能的對應。精確符合（代號或簡稱）優先，沒有才退到全名包含。"""
    q = query.strip()
    qu = q.upper()
    exact, partial = [], []
    for market, rows in data.items():
        for r in rows:
            hit = {"ticker": f"{market}:{r['code']}", "market": market, **r}
            if qu == r["code"].upper() or q == r["short"]:
                exact.append(hit)
            elif len(q) >= 2 and (q in r["name"] or (market == "US" and qu in r["name"].upper())):
                partial.append(hit)
    return exact or partial[:10]


def main(argv: list) -> int:
    if not argv or argv[0] not in ("lookup", "update"):
        print(__doc__, file=sys.stderr)
        return 2
    if argv[0] == "update":
        data, warnings = load(force=True)
        print(json.dumps({"counts": {m: len(r) for m, r in data.items()},
                          "warnings": warnings}, ensure_ascii=False, indent=2))
        return 0
    data, warnings = load()
    results = {q: lookup(q, data) for q in argv[1:]}
    print(json.dumps({"results": results, "warnings": warnings},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
