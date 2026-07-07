#!/usr/bin/env python3
# 검증 소급 등록기 — discovery/leading 인덱스의 firstSeen을 근거로 과거(기본 6/21~) 발굴·선행
# 종목을 verification.json cases[]에 pending 등록한다. flagPrice는 null(브리핑이 과거가 소급 조회).
# 멱등: 이미 있는 종목(name)은 건너뛴다. 표준 라이브러리만.
#   사용: python3 seed-verification.py [SINCE=2026-06-21]
import json, os, sys
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
VF = os.path.join(DATA, "verification.json")
SINCE = sys.argv[1] if len(sys.argv) > 1 else "2026-06-21"

def load_idx(fname):
    try:
        return json.load(open(os.path.join(DATA, fname), encoding="utf-8")).get("companies", {})
    except Exception:
        return {}

def main():
    disc = load_idx("discovery-index.json")
    lead = load_idx("leading-index.json")

    if os.path.exists(VF):
        vf = json.load(open(VF, encoding="utf-8"))
    else:
        vf = {"updatedAt": None, "cases": [], "stats": {}}
    vf.setdefault("cases", [])
    existing = {c.get("name") for c in vf["cases"]}

    added = 0
    # leading 우선(예측 성격), 그다음 discovery
    for comps, typ in ((lead, "leading"), (disc, "discovery")):
        for name, v in comps.items():
            fs = (v.get("firstSeen") or "")[:10]
            if not fs or fs < SINCE:
                continue
            if name in existing:
                continue
            case = {
                "name": name, "type": typ, "market": v.get("market", ""),
                "flagDate": fs, "flagPrice": None,
                "signals": v.get("signals", []) if typ == "leading" else [],
                "theme": v.get("theme", ""),
                "priceLog": [], "checks": [], "status": "pending",
                "backfill": True,   # 소급 등록 표시(브리핑이 과거가 조회 대상임을 앎)
            }
            vf["cases"].append(case)
            existing.add(name)
            added += 1

    vf["updatedAt"] = datetime.now(KST).isoformat(timespec="seconds")
    json.dump(vf, open(VF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[seed] {SINCE} 이후 소급 등록 +{added}건 (총 {len(vf['cases'])}건)")

if __name__ == "__main__":
    main()
