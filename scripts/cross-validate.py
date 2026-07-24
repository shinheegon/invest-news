#!/usr/bin/env python3
# 🎯 교차검증(convergence) 엔진 — 여러 독립 신호가 '동시에' 가리키는 종목일수록 실측 적중률이
# 급등한다(단일 18% → 승세테마+반복 57%). 각 후보의 신호 수렴도(convergence)를 점수화하고,
# 그 방법이 실제로 통하는지 tier별 적중률로 자기검증한다(검증 확실한 방법으로 데이터 추적).
# 신호 축(모두 실측 엣지 기반): 반복포착 · 승세테마 · 구체촉발재 · 틈새레이더(원본 반복) /
# 회피축: 약신호단독 · 열세테마.  표준 라이브러리만.
import json, os
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
VF = os.path.join(DATA, "verification.json")
NICHE = os.path.join(DATA, "niche-radar.json")
SB = os.path.join(DATA, "theme-scoreboard.json")
DISC = os.path.join(DATA, "discovery-index.json")
LEAD = os.path.join(DATA, "leading-index.json")
OUT = os.path.join(DATA, "cross-signal.json")

CONCRETE = ("수주", "계약", "공급", "납품", "선정", "특허", "신제품", "양산", "캐파", "증설",
            "독점", "수주잔고", "국책과제", "인증", "발주", "낙찰", "자사주", "내부자")
WEAK = ("테마첫거론", "테마반복거론", "테마거론", "턴어라운드조짐")
WIN = ("로봇", "휴머노이드", "감속", "액추", "구동", "설계", "팹리스", "ip", "칩스앤")
LOSE = ("반도체소재", "소부장", "장비", "도금", "기판", "바이오", "의료", "제약",
        "신재생", "풍력", "태양", "전력", "데이터센터")

# 실측 엣지 기반 가중치(+양성/−회피)
W = {"repeat": 3, "winTheme": 2, "concrete": 2, "niche": 2, "weak": -2, "loseTheme": -3}


def load(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


def base_name(name):
    import re
    return re.sub(r"\(.*?\)", "", name or "").strip()


def sig_features(c):
    """flag 시점 신호만(케이스 저장 signals·theme) — 검증(retrospective)에 사용. 무오염."""
    t = (" ".join(c.get("signals") or []) + " " + (c.get("theme") or "")).lower()
    return {
        "repeat": ("반복" in t) or ("회" in t and "회피" not in t),
        "winTheme": any(k in t for k in WIN),
        "concrete": any(k in t for k in CONCRETE),
        "weak": any(k in t for k in WEAK) and not any(k in t for k in CONCRETE),
        "loseTheme": any(k in t for k in LOSE),
    }


def current_features(c, niche_names, disc_cnt, lead_cnt):
    """전방 후보용: flag 신호 + 오늘의 독립 신호(틈새레이더·현재 누적카운트) 추가."""
    f = sig_features(c)
    cnt = max(disc_cnt.get(c.get("name"), 0), lead_cnt.get(c.get("name"), 0), c.get("count", 0) or 0)
    if cnt >= 3:
        f["repeat"] = True
    f["niche"] = base_name(c.get("name")) in niche_names   # 원본 코퍼스 독립 반복
    return f, cnt


def score(f):
    return sum(W.get(k, 0) for k, v in f.items() if v)


def signal_list(f):
    lab = {"repeat": "반복포착", "winTheme": "승세테마", "concrete": "구체촉발재",
           "niche": "틈새레이더", "weak": "⚠️약신호", "loseTheme": "⚠️열세테마"}
    return [lab[k] for k, v in f.items() if v]


def main():
    vf = load(VF, {"cases": []})
    cases = vf.get("cases", [])
    niche = load(NICHE, {"companies": []})
    niche_names = {base_name(x.get("name")) for x in niche.get("companies", [])}
    disc_cnt = {n: v.get("count", 0) for n, v in load(DISC, {}).get("companies", {}).items()}
    lead_cnt = {n: v.get("count", 0) for n, v in load(LEAD, {}).get("companies", {}).items()}

    resolved = [c for c in cases if c.get("finalVerdict") in ("적중", "중립", "빗나감")
                and c.get("type") in ("leading", "discovery")]
    pending = [c for c in cases if c.get("status") != "verified"
               and c.get("type") in ("leading", "discovery")]

    # ── 검증: convergence tier별 실측 적중률 (방법 자체가 통하는지) ──
    # flag 시점 신호만 사용(무오염). high=여러 양성신호 수렴.
    def tier(s):
        return "high" if s >= 5 else "mid" if s >= 3 else "low"
    buckets = {"high": [], "mid": [], "low": []}
    for c in resolved:
        buckets[tier(score(sig_features(c)))].append(c)
    tier_stats = {}
    for k, arr in buckets.items():
        n = len(arr)
        h = sum(1 for c in arr if c.get("finalVerdict") == "적중")
        tier_stats[k] = {"n": n, "hit": h, "hitRate": round(h / n * 100, 1) if n else None}
    N = len(resolved)
    base = round(sum(1 for c in resolved if c.get("finalVerdict") == "적중") / N * 100, 1) if N else None

    # ── 전향 stamp: 대기 예측에 flag시점 convergence를 '한 번' 새겨 verification에 저장 ──
    # (이후 그 케이스가 만기검증되면, 우리가 미리 찍은 수렴점수가 실제로 맞았는지 추적 가능 = 완전 폐루프)
    today = datetime.now(KST).strftime("%Y-%m-%d")
    stamped = 0
    for c in cases:
        if c.get("status") == "verified" or c.get("type") not in ("leading", "discovery"):
            continue
        if "convScore" in c:            # 이미 새김(flag시점 기록 보존) — 재계산 금지
            continue
        # ⚠️ 전향성 보장: 결과(D+3)가 아직 안 난 케이스만 stamp(이미 판정났으면 예측 아님)
        if any(k.get("horizon") == "D+3" for k in (c.get("checks") or [])):
            continue
        f, cnt = current_features(c, niche_names, disc_cnt, lead_cnt)
        c["convScore"] = score(f)
        c["convTier"] = tier(c["convScore"])
        c["convSignals"] = signal_list(f)
        c["convStampedAt"] = today
        stamped += 1
    if stamped:
        json.dump(vf, open(VF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ── 검증(전향적): '미리 새긴' convScore를 가진 채 만기검증된 케이스만 → 진짜 예측 성적 ──
    prosp = {"high": [], "mid": [], "low": []}
    for c in resolved:
        if "convScore" in c:            # stamp된 뒤 resolve = 전향적 추적 대상
            prosp[tier(c["convScore"])].append(c)
    tier_prospective = {}
    for k, arr in prosp.items():
        n = len(arr); h = sum(1 for c in arr if c.get("finalVerdict") == "적중")
        tier_prospective[k] = {"n": n, "hit": h, "hitRate": round(h / n * 100, 1) if n else None}
    prosp_total = sum(v["n"] for v in tier_prospective.values())

    # ── 전방: 오늘 대기 후보를 convergence로 랭킹 (이름 중복 제거) ──
    best = {}
    for c in pending:
        f, cnt = current_features(c, niche_names, disc_cnt, lead_cnt)
        s = score(f)
        row = {"name": c.get("name"), "type": c.get("type"), "theme": c.get("theme"),
               "score": s, "count": cnt, "signals": signal_list(f),
               "convergence": sum(1 for k, v in f.items() if v and W.get(k, 0) > 0)}
        prev = best.get(c.get("name"))
        if not prev or s > prev["score"]:
            best[c.get("name")] = row
    cands = sorted(best.values(), key=lambda x: (-x["score"], -x["count"]))

    out = {
        "updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "note": "여러 독립 신호가 동시에 가리키는(수렴) 종목일수록 실측 적중률↑. tierStats=과거전수(회귀), tierProspective=미리 찍은 예측만(전향). 투자권유 아님.",
        "baseHitRate": base, "tierStats": tier_stats,
        "tierProspective": tier_prospective, "prospectiveTotal": prosp_total,
        "weights": W,
        "topCandidates": cands[:20],
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[cross] 회귀 tier(기준 {base}%): "
          + " · ".join(f"{k}={v['hitRate']}%(n={v['n']})" for k, v in tier_stats.items()))
    print(f"[cross] 전향 stamp {stamped}건 새김 · 전향검증 {prosp_total}건"
          + (f" (high={tier_prospective['high']['hitRate']}% n={tier_prospective['high']['n']})" if prosp_total else " (아직 만기 전 — 며칠 뒤부터 채워짐)"))
    print(f"[cross] 오늘 대기 후보 {len(cands)}개 · 최고 convergence:")
    for c in cands[:6]:
        print(f"   [{c['score']:+d}] {c['name'][:18]:18} {'/'.join(c['signals'])}")


if __name__ == "__main__":
    main()
