#!/usr/bin/env python3
# 거시 컨텍스트 스냅샷 — market-history에서 오늘의 거시 상태를 정량화하고, 가격으로 판별 가능한
# '역사 반복 패턴'의 트리거가 켜졌는지 자동 감지한다. 에이전트가 macro-patterns.json과 이걸 함께
# 읽어 "오늘은 어느 과거 패턴과 닮았나"를 근거 숫자로 매칭한다. 표준 라이브러리만.
import json, os
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
MH = os.path.join(DATA, "market-history.json")
PAT = os.path.join(DATA, "macro-patterns.json")
OUT = os.path.join(DATA, "macro-context.json")


def series(s, name):
    d = s.get(name) or {}
    return [(k, d[k]) for k in sorted(d)] if isinstance(d, dict) else []


def pct(vals, n):
    if len(vals) >= n + 1 and vals[-(n + 1)][1]:
        return round((vals[-1][1] - vals[-(n + 1)][1]) / vals[-(n + 1)][1] * 100, 2)
    return None


def daily_changes(vals):
    out = []
    for i in range(1, len(vals)):
        p = vals[i - 1][1]
        if p:
            out.append((vals[i][0], round((vals[i][1] - p) / p * 100, 2)))
    return out


def main():
    if not os.path.exists(MH):
        print("[macro] market-history 없음 — skip"); return
    s = json.load(open(MH, encoding="utf-8")).get("series", {})

    def latest(name):
        v = series(s, name)
        return v[-1][1] if v else None

    kospi = series(s, "코스피")
    kosdaq = series(s, "코스닥")
    kospi_chg = daily_changes(kospi)

    snap = {
        "kospi": latest("코스피"), "kospi1d": pct(kospi, 1), "kospi5d": pct(kospi, 5),
        "kosdaq": latest("코스닥"), "kosdaq1d": pct(kosdaq, 1), "kosdaq5d": pct(kosdaq, 5),
        "vix": latest("VIX"), "fearGreed": latest("주식 공포·탐욕"),
        "usdkrw": latest("원/달러"), "wti": latest("WTI 유가") or latest("WTI"),
        "ust10y": latest("美 10년물"), "dxy": latest("달러인덱스(DXY)"),
    }
    wti = series(s, "WTI 유가") or series(s, "WTI")

    # 가격 기반 패턴 트리거 자동 감지
    recent_crash = [d for d, c in kospi_chg[-5:] if c <= -4]
    rebound = bool(recent_crash) and (snap["kospi1d"] or 0) > 1.5
    oil_spike = (pct(wti, 3) or 0) >= 5
    flags = {
        "급락_최근5일": bool(recent_crash),
        "급락일자": recent_crash,
        "V자반등_진행": rebound,
        "유가급등_3일5%↑": oil_spike,
        "위험회피_공포탐욕35이하": (snap["fearGreed"] is not None and snap["fearGreed"] <= 35),
        "저VIX_안도": (snap["vix"] is not None and snap["vix"] <= 16),
    }
    active_triggers = [k for k, v in flags.items() if v and not k.endswith("일자")]

    out = {
        "updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "asOf": (kospi[-1][0] if kospi else None),
        "snapshot": snap, "flags": flags, "activeTriggers": active_triggers,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[macro] 컨텍스트 산출 · 코스피 {snap['kospi']}({snap['kospi1d']}%) VIX {snap['vix']} F&G {snap['fearGreed']}"
          f" · 켜진 트리거 {active_triggers}")


if __name__ == "__main__":
    main()
