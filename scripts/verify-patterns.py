#!/usr/bin/env python3
# 🔁 역사반복 패턴 자동검증 폐루프 — macro-patterns.json의 각 패턴이 '실제로 맞았는지'를
# 기존 데이터(verification.json 실측 초과수익 + market-history 급락/유가 트리거)로 채점해
# hit·confidence를 자기갱신한다. 이게 진짜 자기학습: 잘 맞는 패턴은 신뢰도↑, 아니면↓.
# 각 패턴을 '검증 케이스의 부분집합'에 매핑하고, 그 부분집합의 실측 적중률을 신뢰도로 쓴다.
# 데이터로 검증 불가한 패턴은 seed값 유지(method=seed로 표기 — 투명성). 표준 라이브러리만.
import json, os, re
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
PAT = os.path.join(DATA, "macro-patterns.json")
VF = os.path.join(DATA, "verification.json")
MH = os.path.join(DATA, "market-history.json")
MIN_CASES = 3          # 이 미만이면 자동검증 불가(표본 부족) → seed 유지

WEAK = ("테마첫거론", "테마반복거론", "테마거론", "턴어라운드조짐")
CONCRETE = ("수주", "계약", "공급", "납품", "선정", "특허", "신제품", "양산", "캐파", "증설",
            "독점", "수주잔고", "국책과제", "인증", "발주", "낙찰")
WIN_THEMES = ("로봇", "휴머노이드", "감속", "액추", "구동", "설계", "팹리스", "ip", "칩스앤")


def load(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


def d3(c):
    for k in c.get("checks", []):
        if k.get("horizon") == "D+3":
            return k
    return (c.get("checks") or [None])[-1]


def sig_text(c):
    return " ".join(c.get("signals") or []) + " " + (c.get("theme") or "")


def has(c, kws):
    t = sig_text(c).lower()
    return any(k.lower() in t for k in kws)


def crash_days(mh):
    """market-history에서 코스피 일간 -4%↓ 급락일 목록."""
    s = (mh.get("series") or {}).get("코스피") or {}
    dates = sorted(s)
    out = []
    for i in range(1, len(dates)):
        p = s[dates[i - 1]]
        if p and (s[dates[i]] - p) / p * 100 <= -4:
            out.append(dates[i])
    return out


def near_crash(flag, crashes, win=4):
    """flagDate가 급락일 당일~win일 이내(급락 직후 포착)인가."""
    try:
        fd = datetime.strptime(flag, "%Y-%m-%d").date()
    except Exception:
        return False
    for cd in crashes:
        try:
            d = (fd - datetime.strptime(cd, "%Y-%m-%d").date()).days
            if 0 <= d <= win:
                return True
        except Exception:
            pass
    return False


# 패턴별 (매처, 방향) — FAVOR: 적중이 성공 / AVOID: 빗나감이 성공(회피 정당)
def build_matchers(crashes):
    return {
        "theme-first-only": (lambda c: has(c, WEAK) and not has(c, CONCRETE), "AVOID"),
        "insider-buy": (lambda c: has(c, ("자사주", "내부자", "경영진 매입", "경영진매수")), "FAVOR"),
        "structural-adoption": (lambda c: has(c, ("로봇", "휴머노이드", "감속", "액추", "구동"))
                                and has(c, ("채택", "전환", "양산", "납품", "선정", "수주")), "FAVOR"),
        "memory-peak-rotation": (lambda c: has(c, WIN_THEMES), "FAVOR"),
        "crash-v-rotation": (lambda c: near_crash(c.get("flagDate", ""), crashes)
                             and has(c, WIN_THEMES), "FAVOR"),
        "buried-contract-rebound": (lambda c: near_crash(c.get("flagDate", ""), crashes)
                                    and has(c, CONCRETE), "FAVOR"),
    }


def main():
    pats = load(PAT, None)
    vf = load(VF, {"cases": []})
    mh = load(MH, {})
    if not pats:
        print("[verify-pat] macro-patterns.json 없음 — skip"); return

    resolved = [c for c in vf.get("cases", [])
                if c.get("finalVerdict") in ("적중", "중립", "빗나감")]
    matchers = build_matchers(crash_days(mh))
    # 기준선: 전체 적중률 / 전체 빗나감률 (패턴 엣지 판정용)
    N = len(resolved) or 1
    base_hit = round(sum(1 for c in resolved if c.get("finalVerdict") == "적중") / N, 2)
    base_miss = round(sum(1 for c in resolved if c.get("finalVerdict") == "빗나감") / N, 2)

    updated = 0
    for p in pats.get("patterns", []):
        m = matchers.get(p.get("id"))
        if not m:
            p["method"] = "seed"       # 데이터 자동검증 불가(이벤트성) — seed 유지
            continue
        fn, direction = m
        subset = [c for c in resolved if _safe(fn, c)]
        n = len(subset)
        if n < MIN_CASES:
            p["method"] = "seed"; p["dataN"] = n
            continue
        if direction == "FAVOR":
            hit = sum(1 for c in subset if c.get("finalVerdict") == "적중")
            base = base_hit
        else:  # AVOID: 빗나감이면 회피가 옳았음 = 성공
            hit = sum(1 for c in subset if c.get("finalVerdict") == "빗나감")
            base = base_miss
        conf = round(hit / n, 2)
        edge = round(conf - base, 2)          # 기준선 대비 초과 = 진짜 예측력
        p["observed"] = n
        p["hit"] = hit
        p["confidence"] = conf
        p["baseRate"] = base
        p["edge"] = edge
        p["validated"] = edge >= 0.1          # 기준선 +10%p↑면 '검증된 엣지'
        p["direction"] = direction
        p["method"] = "auto"
        p["dataN"] = n
        p["lastVerified"] = datetime.now(KST).strftime("%Y-%m-%d")
        p["sampleCases"] = [c.get("name") for c in subset[:5]]
        updated += 1

    pats["updatedAt"] = datetime.now(KST).isoformat(timespec="seconds")
    json.dump(pats, open(PAT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    auto = [p for p in pats["patterns"] if p.get("method") == "auto"]
    print(f"[verify-pat] 자동검증 {updated}개 (검증 {len(resolved)}건 · 기준 적중{int(base_hit*100)}%/빗나감{int(base_miss*100)}%)")
    for p in sorted(auto, key=lambda x: -(x.get("edge") or -9)):
        mark = "✅검증된엣지" if p.get("validated") else "▫엣지없음"
        print(f"   {mark} {p['name'][:28]:28} n={p['observed']} 신뢰{int(p['confidence']*100)}% (기준{int(p['baseRate']*100)}% · 엣지{'+' if p['edge']>=0 else ''}{int(p['edge']*100)}%p)")


def _safe(fn, c):
    try:
        return bool(fn(c))
    except Exception:
        return False


if __name__ == "__main__":
    main()
