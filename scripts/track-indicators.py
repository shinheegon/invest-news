#!/usr/bin/env python3
# 투자지표 히스토리 누적기 — 브리핑이 만든 market-indicators.json(현재값)을
# 날짜별 시계열 market-history.json에 upsert 한다. 추세 그래프의 원천.
# 결정적(숫자 파싱)으로 처리 — LLM 불필요. 표준 라이브러리만.
import json, os, re
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
SRC = os.path.join(DATA, "market-indicators.json")
HIST = os.path.join(DATA, "market-history.json")

def num(s):
    """'8,726.60' -> 8726.6, '약 4.5%' -> 4.5, '$80.x' -> 80.0 (첫 실수 추출)"""
    if s is None:
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", str(s).replace(",", ""))
    return float(m.group()) if m else None

def main():
    if not os.path.exists(SRC):
        print("[track] market-indicators.json 없음 — skip")
        return
    cur = json.load(open(SRC, encoding="utf-8"))
    date = os.environ.get("BRIEFING_DATE") or datetime.now(KST).strftime("%Y-%m-%d")

    hist = {"updatedAt": None, "series": {}}
    if os.path.exists(HIST):
        try:
            hist = json.load(open(HIST, encoding="utf-8"))
        except Exception:
            pass
    series = hist.setdefault("series", {})

    def put(name, value):
        if value is None:
            return
        series.setdefault(name, {})[date] = value  # 같은 날 재실행 시 최신값으로 덮어씀

    # 주식 공포·탐욕
    sf = cur.get("stock_fng") or {}
    put("주식 공포·탐욕", num(sf.get("value")))
    # 증시·매크로 지표(값의 숫자만 시계열로)
    for idx in cur.get("indices", []):
        nm = idx.get("name")
        if nm:
            put(nm, num(idx.get("value")))

    hist["updatedAt"] = datetime.now(KST).isoformat(timespec="seconds")
    with open(HIST, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)

    days = max((len(v) for v in series.values()), default=0)
    print(f"[track] {date} 지표 {len(series)}종 누적 (최장 {days}일 시계열)")

if __name__ == "__main__":
    main()
