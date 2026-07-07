#!/usr/bin/env python3
# 자체 검증 통계 재계산기 — 브리핑(에이전트)이 채운 verification.json의 cases[]를 읽어
# 적중률·평균 변동률 통계를 결정적으로 다시 계산한다(수치 신뢰성 보장). 표준 라이브러리만.
import json, os
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
FILE = os.path.join(DATA, "verification.json")
KST = timezone(timedelta(hours=9))

def d3(case):
    """대표 체크(D+3 우선, 없으면 마지막 체크) 반환."""
    checks = case.get("checks") or []
    if not checks:
        return None
    for c in checks:
        if c.get("horizon") == "D+3":
            return c
    return checks[-1]

def final_verdict(case):
    c = d3(case)
    return c.get("verdict") if c else None

def main():
    if not os.path.exists(FILE):
        print("[verify] verification.json 없음 — skip")
        return
    try:
        v = json.load(open(FILE, encoding="utf-8"))
    except Exception as e:
        print(f"[verify] 읽기 실패: {e}"); return
    cases = v.get("cases", [])

    def block(subset):
        verified = [c for c in subset if (c.get("status") == "verified" or d3(c))]
        vs = [final_verdict(c) for c in verified]
        vs = [x for x in vs if x]
        hit = sum(1 for x in vs if x == "적중")
        miss = sum(1 for x in vs if x == "빗나감")
        neu = sum(1 for x in vs if x == "중립")
        chgs = [d3(c)["changePct"] for c in verified
                if d3(c) and isinstance(d3(c).get("changePct"), (int, float))]
        n = len(vs)
        return {
            "verified": n, "hit": hit, "neutral": neu, "miss": miss,
            "hitRate": round(hit / n * 100, 1) if n else None,
            "avgD3ChangePct": round(sum(chgs) / len(chgs), 2) if chgs else None,
        }

    stats = block(cases)
    stats["pending"] = sum(1 for c in cases if c.get("status") != "verified" and not d3(c))
    stats["total"] = len(cases)
    stats["byType"] = {
        "leading": block([c for c in cases if c.get("type") == "leading"]),
        "discovery": block([c for c in cases if c.get("type") == "discovery"]),
    }
    # 각 케이스에 finalVerdict 표기(사이트 표시용)
    for c in cases:
        fv = final_verdict(c)
        if fv:
            c["finalVerdict"] = fv

    v["stats"] = stats
    v["updatedAt"] = datetime.now(KST).isoformat(timespec="seconds")
    json.dump(v, open(FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    hr = stats["hitRate"]
    print(f"[verify] 검증 {stats['verified']}건 · 적중률 {hr if hr is not None else '—'}% "
          f"· 평균 D+3 {stats['avgD3ChangePct']}% · 대기 {stats['pending']}건")

if __name__ == "__main__":
    main()
