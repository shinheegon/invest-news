#!/usr/bin/env python3
# 빗나감 원인분석 엔진 (자기발전형) — 검증에서 '빗나감' 판정된 예측을 자동으로 원인 분류하고,
# 그 분포를 매 회차 누적(history)해 스스로 필터 규칙을 갱신한다. 거시경제(코스피·VIX·공포탐욕 +
# 케이스별 지수변동)를 국면 판정에 반영. 발굴/선행 엔진이 miss-analysis.json을 읽어 실수를 반복하지
# 않도록 필터링한다. 결정적·표준 라이브러리만.
#
# 원인 5분류(자동):
#   weak_signal    구체 촉발재 없이 '테마 거론'류 신호만 → 우리가 거른다(예방 가능)
#   theme_headwind 열세 테마(자금 이탈) 안에서 포착 → 테마 게이트로 거른다(예방 가능)
#   macro_riskoff  포착 기간 시장 자체가 급락(위험회피) → 거시 게이트(국면 회피)
#   late_entry     이미 급등한 뒤 뒤늦게 포착(후발) → 조기성 게이트
#   idiosyncratic  위 어디에도 안 걸리는 개별 악재 → 불가피 노이즈
import json, os, re
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
VF = os.path.join(DATA, "verification.json")
SB = os.path.join(DATA, "theme-scoreboard.json")
MH = os.path.join(DATA, "market-history.json")
OUT = os.path.join(DATA, "miss-analysis.json")

# theme-scoreboard.py와 동일 카테고리(동기화 유지)
CATS = [
    ("로봇/휴머노이드", ["휴머노이드", "로봇", "모션", "액추", "감속", "구동"]),
    ("AI반도체설계(팹리스/IP)", ["팹리스", "설계자산", "디자인", "설계", "ip", "칩스앤"]),
    ("우주/방산", ["우주", "위성", "방산", "로켓", "발사", "잠수함"]),
    ("반도체소재/장비", ["hbm", "소재", "도금", "장비", "소부장", "후공정", "본딩", "기판", "유리기판"]),
    ("AI전력/데이터센터", ["데이터센터", "전력", "변압", "냉각", "전선", "aidc"]),
    ("신재생에너지", ["풍력", "태양", "신재생", "해상", "수소", "smr", "원전"]),
    ("이차전지", ["2차전지", "이차전지", "전지", "배터리"]),
    ("바이오/의료", ["바이오", "의료", "제약", "분리막", "암치료"]),
]
CONCRETE = ["수주", "선정", "납품", "특허", "신제품", "공급계약", "증설", "캐파",
            "독점", "수주잔고", "인증", "양산", "발주", "계약", "낙찰", "내부자", "자사주"]
LATE = ["급등", "신고가", "상한가", "이미", "후발", "과열"]

CAUSE_LABEL = {
    "weak_signal": "신호 약함(구체 촉발재 없음)",
    "theme_headwind": "열세 테마(자금 이탈)",
    "macro_riskoff": "거시 위험회피(시장 동반 급락)",
    "late_entry": "후발 진입(이미 급등)",
    "idiosyncratic": "개별 악재(불가피)",
}
PREVENTABLE = {"weak_signal", "theme_headwind", "late_entry"}   # 필터로 예방 가능


def cat(theme, signals, name):
    blob = " ".join([theme or "", " ".join(signals or []), name or ""]).lower()
    for nm, kws in CATS:
        if any(k in blob for k in kws):
            return nm
    return "기타"


def d3(c):
    for k in c.get("checks", []):
        if k.get("horizon") == "D+3":
            return k
    return (c.get("checks") or [None])[-1]


def classify(c, losing):
    """빗나감 케이스의 1차 원인 + 태그(다중) 반환."""
    sigs = c.get("signals", []) or []
    ch = d3(c) or {}
    idxpct = ch.get("indexPct")
    theme = cat(c.get("theme"), sigs, c.get("name"))
    concrete = any(any(k in s for k in CONCRETE) for s in sigs)
    late = any(any(k in s for k in LATE) for s in sigs)
    tags = []
    if not concrete:
        tags.append("weak_signal")
    if theme in losing:
        tags.append("theme_headwind")
    if isinstance(idxpct, (int, float)) and idxpct <= -3:
        tags.append("macro_riskoff")
    if late:
        tags.append("late_entry")
    # 1차 원인 우선순위: 예방가능한 것 먼저(행동으로 이어지게), 그다음 거시, 마지막 개별
    for pri in ("weak_signal", "theme_headwind", "late_entry", "macro_riskoff"):
        if pri in tags:
            return pri, tags, theme
    return "idiosyncratic", tags, theme


def macro_regime():
    """market-history로 현재 거시 국면 판정."""
    if not os.path.exists(MH):
        return {"regime": "unknown", "guidance": "거시 데이터 없음"}
    s = json.load(open(MH, encoding="utf-8")).get("series", {})

    def series(name):
        d = s.get(name) or {}
        return [d[k] for k in sorted(d)] if isinstance(d, dict) else []

    def pct5(name):
        v = series(name)
        if len(v) >= 6 and v[-6]:
            return round((v[-1] - v[-6]) / v[-6] * 100, 2)
        return None

    kospi5 = pct5("코스피")
    kosdaq5 = pct5("코스닥")
    fg = (series("주식 공포·탐욕") or [None])[-1]
    vix = (series("VIX") or [None])[-1]
    # 국면 규칙
    risk_off = ((kospi5 is not None and kospi5 <= -2) or (fg is not None and fg <= 35)
                or (vix is not None and vix >= 22))
    risk_on = ((kospi5 is not None and kospi5 >= 2) and (fg is None or fg >= 55)
               and (vix is None or vix <= 17))
    regime = "위험회피" if risk_off else "위험선호" if risk_on else "중립"
    guide = {
        "위험회피": "소형주 언더퍼폼 국면 — 포착 수를 줄이고 승세테마×구체촉발재만 최고확신으로. 열세테마·약신호 전면 배제.",
        "위험선호": "순환매 유리 — 승세테마 우선하되 신선한 조기 종목까지 폭 확대 가능.",
        "중립": "선별 유지 — 승세테마+구체촉발재 우선, 약신호·열세테마 경계.",
    }[regime]
    return {"regime": regime, "kospi5d": kospi5, "kosdaq5d": kosdaq5,
            "fearGreed": fg, "vix": vix, "guidance": guide,
            "asOf": datetime.now(KST).strftime("%Y-%m-%d")}


def main():
    if not os.path.exists(VF):
        print("[miss] verification.json 없음 — skip"); return
    cases = json.load(open(VF, encoding="utf-8")).get("cases", [])
    losing = set(json.load(open(SB, encoding="utf-8")).get("losing", [])) if os.path.exists(SB) else set()

    resolved = [c for c in cases if c.get("finalVerdict") in ("적중", "중립", "빗나감")
                and c.get("type") in ("leading", "discovery")]
    misses = [c for c in resolved if c.get("finalVerdict") == "빗나감"]

    # 원인 집계
    agg = {}
    theme_stat, sig_stat = {}, {}
    for c in resolved:
        theme = cat(c.get("theme"), c.get("signals"), c.get("name"))
        concrete = any(any(k in s for k in CONCRETE) for s in (c.get("signals") or []))
        skey = "concrete" if concrete else "weak"
        t = theme_stat.setdefault(theme, {"n": 0, "miss": 0})
        sg = sig_stat.setdefault(skey, {"n": 0, "miss": 0})
        t["n"] += 1; sg["n"] += 1
        if c.get("finalVerdict") == "빗나감":
            t["miss"] += 1; sg["miss"] += 1
    for c in misses:
        cause, tags, theme = classify(c, losing)
        ch = d3(c) or {}
        a = agg.setdefault(cause, {"n": 0, "excess": [], "ex": []})
        a["n"] += 1
        if isinstance(ch.get("excessPct"), (int, float)):
            a["excess"].append(ch["excessPct"])
        a["ex"].append({"name": c.get("name"), "flagDate": c.get("flagDate"),
                        "excessPct": ch.get("excessPct"), "theme": theme,
                        "tags": tags})

    total_m = len(misses)
    by_cause = []
    for cause, a in sorted(agg.items(), key=lambda x: -x[1]["n"]):
        ex = sorted(a["ex"], key=lambda e: (e["excessPct"] if isinstance(e["excessPct"], (int, float)) else 0))[:3]
        by_cause.append({
            "cause": cause, "label": CAUSE_LABEL[cause], "n": a["n"],
            "share": round(a["n"] / total_m * 100, 1) if total_m else 0,
            "avgExcess": round(sum(a["excess"]) / len(a["excess"]), 2) if a["excess"] else None,
            "preventable": cause in PREVENTABLE, "examples": ex,
        })
    preventable_n = sum(x["n"] for x in by_cause if x["preventable"])

    # 학습된 필터: 테마별·신호별 빗나감률
    theme_missrate = {k: round(v["miss"] / v["n"] * 100, 1)
                      for k, v in theme_stat.items() if v["n"] >= 3}
    sig_missrate = {k: round(v["miss"] / v["n"] * 100, 1)
                    for k, v in sig_stat.items() if v["n"] >= 1}
    # 규칙 파생(빗나감률 높은 것 → 강한 회피)
    rules = []
    for k, r in sorted(theme_missrate.items(), key=lambda x: -x[1]):
        if r >= 60:
            rules.append(f"'{k}' 테마는 빗나감률 {r}% — 강한 회피(구체촉발재+승세 아니면 제외).")
    if sig_missrate.get("weak", 0) > sig_missrate.get("concrete", 100):
        rules.append(f"구체 촉발재 없는 '테마 거론'류는 빗나감률 {sig_missrate.get('weak')}%"
                     f"(구체재료 {sig_missrate.get('concrete','?')}%) — 약신호 단독 등재 금지.")

    macro = macro_regime()

    # 자기발전: history 누적 + 직전 대비 변화
    prev = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    hist = prev.get("history", [])
    today = datetime.now(KST).strftime("%Y-%m-%d")
    miss_rate = round(total_m / len(resolved) * 100, 1) if resolved else None
    shares = {x["cause"]: x["share"] for x in by_cause}
    snap = {"date": today, "resolved": len(resolved), "missRate": miss_rate, "causeShares": shares}
    hist = [h for h in hist if h.get("date") != today] + [snap]
    hist = hist[-60:]
    develop = ""
    if len(hist) >= 2:
        p = hist[-2]
        top_now = by_cause[0]["cause"] if by_cause else None
        dr = (miss_rate or 0) - (p.get("missRate") or 0)
        develop = (f"직전({p['date']}) 대비 빗나감률 {p.get('missRate')}%→{miss_rate}% "
                   f"({'+' if dr >= 0 else ''}{round(dr,1)}p). "
                   f"최다 원인=‘{CAUSE_LABEL.get(top_now, top_now)}’. 필터에 반영됨.")

    out = {
        "updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "note": "빗나감 자동 원인분류 + 자기발전 필터. 투자권유 아님.",
        "summary": {"resolved": len(resolved), "miss": total_m, "missRate": miss_rate,
                    "preventable": preventable_n,
                    "preventableShare": round(preventable_n / total_m * 100, 1) if total_m else 0},
        "byCause": by_cause,
        "learnedFilter": {"themeMissRate": theme_missrate, "signalMissRate": sig_missrate, "rules": rules},
        "macro": macro,
        "history": hist,
        "develop": develop,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[miss] 빗나감 {total_m}건 분류 · 예방가능 {preventable_n}건"
          f"({out['summary']['preventableShare']}%) · 거시={macro['regime']} · 규칙 {len(rules)}개")
    for x in by_cause:
        print(f"   {x['label']}: {x['n']}건({x['share']}%) 평균초과 {x['avgExcess']}")


if __name__ == "__main__":
    main()
