#!/usr/bin/env python3
# 📊 모의 포트폴리오 추적기 — data/mock-portfolio.json(시드: 진입 스냅샷)의 보유종목을 네이버로
# 현재가 갱신하고, 종목·버킷·전체 수익률 + 코스피 대비 초과수익을 계산한다. 우리 발굴데이터가
# 실제 돈으로 맞는지(성장버킷)를 우량주·배당ETF와 함께 추적. → data/mock-portfolio-live.json
# 실전 매매는 별도(💼 매매일지/portfolio.py). 표준 라이브러리만.
import json, os, re
from urllib.request import Request, urlopen
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
SRC = os.path.join(DATA, "mock-portfolio.json")
OUT = os.path.join(DATA, "mock-portfolio-live.json")


def get(url, enc="euc-kr"):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (news-briefing)"})
    return urlopen(req, timeout=12).read().decode(enc, "ignore")


def cur_price(code):
    try:
        j = json.loads(get(f"https://m.stock.naver.com/api/stock/{code}/basic", "utf-8"))
        p = j.get("closePrice")
        return int(str(p).replace(",", "")) if p else None
    except Exception:
        return None


def kospi_close_on(date):
    """코스피 지수 종가(해당일 이하 최근). 벤치마크용."""
    try:
        out = {}
        for p in range(1, 6):
            h = get(f"https://finance.naver.com/sise/sise_index_day.naver?code=KOSPI&page={p}")
            for d, c in re.findall(r'<td class="date">([\d.]+)</td>\s*<td class="number_1">([\d,]+\.\d+)</td>', h):
                out[d.replace(".", "-")] = float(c.replace(",", ""))
        cand = [d for d in out if d <= date]
        latest = [d for d in out]
        return (out[max(cand)] if cand else None, out[max(latest)] if latest else None)
    except Exception:
        return (None, None)


def main():
    if not os.path.exists(SRC):
        print("[mock] mock-portfolio.json 없음 — skip"); return
    src = json.load(open(SRC, encoding="utf-8"))
    cap = src.get("capital", 0)
    start = src.get("startDate")

    holds = []
    bucket_agg = {}
    invested = cost_total = value_total = 0
    for h in src.get("holdings", []):
        price = cur_price(h["ticker"]) or h["entryPrice"]
        cost = h["entryPrice"] * h["shares"]
        val = price * h["shares"]
        ret = round((price - h["entryPrice"]) / h["entryPrice"] * 100, 2) if h["entryPrice"] else 0
        pnl = val - cost
        row = {**h, "price": price, "cost": cost, "value": val, "returnPct": ret, "pnl": pnl}
        holds.append(row)
        b = bucket_agg.setdefault(h["bucket"], {"cost": 0, "value": 0})
        b["cost"] += cost; b["value"] += val
        invested += cost; cost_total += cost; value_total += val

    for b, a in bucket_agg.items():
        a["returnPct"] = round((a["value"] - a["cost"]) / a["cost"] * 100, 2) if a["cost"] else 0
        a["pnl"] = a["value"] - a["cost"]

    cash = cap - invested
    total_now = value_total + cash
    total_ret = round((total_now - cap) / cap * 100, 2) if cap else 0

    # 코스피 벤치마크(같은 기간)
    k_start, k_now = kospi_close_on(start)
    kospi_ret = round((k_now - k_start) / k_start * 100, 2) if (k_start and k_now) else None
    excess = round(total_ret - kospi_ret, 2) if kospi_ret is not None else None

    out = {
        "updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "note": src.get("note"), "capital": cap, "startDate": start,
        "profile": src.get("profile"), "buckets": src.get("buckets"),
        "holdings": holds, "bucketAgg": bucket_agg,
        "invested": invested, "cash": cash, "valueNow": value_total,
        "totalNow": total_now, "totalReturnPct": total_ret, "totalPnl": total_now - cap,
        "kospiReturnPct": kospi_ret, "excessPct": excess,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[mock] 평가 {total_now:,.0f}원 (원금 {cap:,}) 수익률 {total_ret:+.2f}%"
          + (f" · 코스피 {kospi_ret:+.2f}% · 초과 {excess:+.2f}%p" if kospi_ret is not None else ""))
    for b, a in bucket_agg.items():
        print(f"   {b}: {a['returnPct']:+.2f}% ({a['pnl']:+,.0f}원)")


if __name__ == "__main__":
    main()
