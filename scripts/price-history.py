#!/usr/bin/env python3
# 발굴/선행 종목 주가 곡선 생성기 — verification.json의 각 케이스에 흩어진 가격 점
# (flagPrice@flagDate, priceLog[], checks[].price@date)을 종목별 시계열로 합쳐
# data/price-history.json 으로 저장한다(최초 등장~현재 주가 변동 그래프용). 표준 라이브러리만.
import json, os
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
VF = os.path.join(DATA, "verification.json")
OUT = os.path.join(DATA, "price-history.json")

def num(x):
    return x if isinstance(x, (int, float)) else None

def main():
    if not os.path.exists(VF):
        print("[price] verification.json 없음 — skip"); return
    try:
        cases = json.load(open(VF, encoding="utf-8")).get("cases", [])
    except Exception as e:
        print(f"[price] 읽기 실패: {e}"); return

    companies = {}
    for c in cases:
        name = c.get("name")
        if not name:
            continue
        series = {}
        # flag 시점
        fp, fd = num(c.get("flagPrice")), c.get("flagDate")
        if fp is not None and fd:
            series[fd] = fp
        # 매 회차 누적 로그
        for p in (c.get("priceLog") or []):
            d, pr = p.get("date"), num(p.get("price"))
            if d and pr is not None:
                series[d] = pr
        # 검증 체크(D+3/D+7)
        for ch in (c.get("checks") or []):
            d, pr = ch.get("date"), num(ch.get("price"))
            if d and pr is not None:
                series[d] = pr
        if len(series) < 1:
            continue
        dates = sorted(series)
        first = series[dates[0]]
        companies[name] = {
            "market": c.get("market", ""),
            "type": c.get("type", ""),
            "firstSeen": dates[0],
            "firstPrice": first,
            "lastPrice": series[dates[-1]],
            "changePct": round((series[dates[-1]] - first) / first * 100, 2) if first else None,
            "points": len(dates),
            "series": {d: series[d] for d in dates},
        }

    out = {"updatedAt": datetime.now(KST).isoformat(timespec="seconds"), "companies": companies}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    charted = sum(1 for v in companies.values() if v["points"] >= 2)
    print(f"[price] 주가 곡선 {len(companies)}종 (2점이상 {charted}종) 생성")

if __name__ == "__main__":
    main()
