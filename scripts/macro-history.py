#!/usr/bin/env python3
# 📜 역사 위기 플레이북 — 굵직한 거시위기(IMF·닷컴·2008·코로나·전쟁 등)를 패턴별로 집계해
# '이 큰 흐름이 역사적으로 몇 번 중 몇 번 반복됐나(확률)' + 평균 낙폭·회복기간을 수치화한다.
# 그리고 오늘 거시상황(macro-context)이 어느 역사패턴과 닮았는지 표시. 표준 라이브러리만.
import json, os
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
SRC = os.path.join(DATA, "macro-history.json")
CTX = os.path.join(DATA, "macro-context.json")
OUT = os.path.join(DATA, "macro-history-agg.json")

LABELS = {
    "crisis_easing_recovery": "위기 → 완화정책(현금살포) → 회복",
    "bubble_burst": "버블 붕괴 → 장기 조정",
    "inflation_tightening": "인플레 → 긴축 → 성장주 조정",
    "war_geopolitics": "전쟁·지정학 → 에너지·방산↑·위험자산 단기↓",
}


def load(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


def avg(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 1) if xs else None


def main():
    src = load(SRC, None)
    if not src:
        print("[hist] macro-history.json 없음 — skip"); return
    events = src.get("events", [])

    agg = {}
    for e in events:
        pt = e.get("patternType", "기타")
        a = agg.setdefault(pt, {"events": [], "dd": [], "rec": [], "fav": set(), "hurt": set()})
        a["events"].append({"year": e.get("year"), "name": e.get("name"),
                            "drawdownPct": e.get("drawdownPct"), "recoveryMonths": e.get("recoveryMonths")})
        a["dd"].append(e.get("drawdownPct"))
        a["rec"].append(e.get("recoveryMonths"))
        a["fav"].update(e.get("favored", []))
        a["hurt"].update(e.get("hurt", []))

    patterns = []
    for pt, a in agg.items():
        recs = [r for r in a["rec"] if isinstance(r, (int, float))]
        recovered = len(recs)                       # 회복이 기록된 사례 수
        n = len(a["events"])
        patterns.append({
            "type": pt, "label": LABELS.get(pt, pt), "n": n,
            "recoveredCount": recovered,
            "repeatProbPct": round(recovered / n * 100) if n else None,   # 몇 번 중 회복 반복(확률)
            "avgDrawdownPct": avg(a["dd"]),
            "drawdownRange": [min(x for x in a["dd"] if x is not None), max(x for x in a["dd"] if x is not None)] if any(a["dd"]) else None,
            "avgRecoveryMonths": avg(recs),
            "recoveryRange": [min(recs), max(recs)] if recs else None,
            "favored": sorted(a["fav"]), "hurt": sorted(a["hurt"]),
            "examples": sorted(a["events"], key=lambda x: x["year"]),
        })
    patterns.sort(key=lambda x: -x["n"])

    # 오늘 거시상황이 어느 역사패턴과 닮았나(macro-context 플래그 기반)
    ctx = load(CTX, {})
    flags = ctx.get("flags", {})
    active = ctx.get("activeTriggers", [])
    current = []
    if flags.get("유가급등_3일5%↑") or any("유가" in t for t in active):
        current.append("war_geopolitics")
    if flags.get("급락_최근5일") or flags.get("위험회피_공포탐욕35이하"):
        current.append("crisis_easing_recovery")   # 급락국면=위기패턴 참조(완화 나오면 회복 기대)

    out = {
        "updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "note": src.get("note"),
        "patterns": patterns,
        "currentMatch": current,
        "asOf": ctx.get("asOf"),
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[hist] 역사패턴 {len(patterns)}종 집계 · 오늘 닮은 패턴: {current or '뚜렷치 않음'}")
    for p in patterns:
        print(f"   {p['label']}: {p['n']}건 반복확률 {p['repeatProbPct']}% · 평균낙폭 {p['avgDrawdownPct']}% · 회복 {p['recoveryRange']}개월")


if __name__ == "__main__":
    main()
