#!/usr/bin/env python3
# 🧭 거시 나침반 — 3대 축(금리·인플레이션·달러환율)의 현재 수준과 추세를 파악해 통합 신호를 낸다.
# 금리인하+인플레둔화+환율안정=위험선호(성장주 유리) / 반대=위험회피(방어). 위기 플레이북과 연결
# (완화=금리인하가 '위기→완화→회복' 패턴의 트리거). market-history의 파편화된 금리명은 병합한다.
# → data/macro-compass.json. 표준 라이브러리만.
import json, os
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
MH = os.path.join(DATA, "market-history.json")
OUT = os.path.join(DATA, "macro-compass.json")

# 같은 지표의 파편화된 이름들을 하나로 병합(날짜별 최신 우선)
ALIASES = {
    "ust10y": ["美 10년물"],
    "kr3y": ["국고채 3년물", "국고채 3년", "韓 국고채 3년물", "韓 국고채 3년"],
    "kr_base": ["한국 기준금리"],
    "us_base": ["美 기준금리", "미국 기준금리", "연준 기준금리"],
    "usdkrw": ["원/달러"],
    "dxy": ["달러인덱스(DXY)", "달러인덱스", "DXY"],
    "us_cpi": ["美 CPI", "미국 CPI", "美 소비자물가"],
    "kr_cpi": ["韓 CPI", "한국 CPI", "韓 소비자물가"],
}


def merged_series(series, keys):
    out = {}
    for k in keys:
        d = series.get(k)
        if isinstance(d, dict):
            out.update(d)      # 뒤 키가 우선(같은 날짜면 덮어씀)
    return [(d, out[d]) for d in sorted(out)] if out else []


def trend(vals, n=5):
    """최근 n관측 방향: (변화량, 라벨). 값 없으면 None."""
    if len(vals) < 2:
        return (None, None)
    recent = vals[-min(n, len(vals)):]
    delta = round(recent[-1][1] - recent[0][1], 3)
    lab = "상승" if delta > 0 else "하락" if delta < 0 else "횡보"
    return (delta, lab)


def main():
    if not os.path.exists(MH):
        print("[compass] market-history 없음 — skip"); return
    series = json.load(open(MH, encoding="utf-8")).get("series", {})
    S = {k: merged_series(series, ks) for k, ks in ALIASES.items()}

    def latest(k):
        return S[k][-1][1] if S[k] else None

    # ── 1) 금리 ──
    us10_d, us10_t = trend(S["ust10y"])
    kr3_d, kr3_t = trend(S["kr3y"])
    kr_base_d, kr_base_t = trend(S["kr_base"], n=8)
    rate_dir = us10_t or kr3_t
    rate_easing = (us10_d is not None and us10_d < -0.05) or (kr_base_d is not None and kr_base_d < 0)
    rate_tightening = (us10_d is not None and us10_d > 0.05) or (kr_base_d is not None and kr_base_d > 0)
    rates = {"ust10y": latest("ust10y"), "ust10yTrend": us10_t,
             "kr3y": latest("kr3y"), "kr3yTrend": kr3_t,
             "krBase": latest("kr_base"), "usBase": latest("us_base"),
             "phase": "인하(완화)" if rate_easing else "인상(긴축)" if rate_tightening else "동결·횡보"}

    # ── 2) 인플레이션 ──
    uc_d, uc_t = trend(S["us_cpi"], n=4)
    kc_d, kc_t = trend(S["kr_cpi"], n=4)
    inf_cooling = (uc_d is not None and uc_d < 0) or (kc_d is not None and kc_d < 0)
    inf_rising = (uc_d is not None and uc_d > 0) or (kc_d is not None and kc_d > 0)
    tracked = bool(S["us_cpi"] or S["kr_cpi"])
    inflation = {"usCpi": latest("us_cpi"), "usCpiTrend": uc_t,
                 "krCpi": latest("kr_cpi"), "krCpiTrend": kc_t,
                 "phase": ("둔화" if inf_cooling else "가속" if inf_rising else "정체") if tracked else "미기록",
                 "tracked": tracked}

    # ── 3) 달러환율 ──
    fx_d, fx_t = trend(S["usdkrw"])
    dxy_d, dxy_t = trend(S["dxy"])
    usdkrw = latest("usdkrw")
    won_weak = (fx_d is not None and fx_d > 3)     # 원화 약세(환율 상승)
    won_strong = (fx_d is not None and fx_d < -3)
    fx = {"usdkrw": usdkrw, "usdkrwTrend": fx_t, "dxy": latest("dxy"), "dxyTrend": dxy_t,
          "level": "고환율(1500+)" if (usdkrw and usdkrw >= 1500) else "안정권",
          "phase": "원화약세(위험회피)" if won_weak else "원화강세(위험선호)" if won_strong else "안정"}

    # ── 통합 신호 (위험선호 ↔ 위험회피) ──
    tilt = 0
    if rate_easing: tilt += 1
    if rate_tightening: tilt -= 1
    if inf_cooling: tilt += 1
    if inf_rising: tilt -= 1
    if won_strong: tilt += 1
    if won_weak: tilt -= 1
    regime = "위험선호" if tilt >= 1 else "위험회피" if tilt <= -1 else "중립"
    guide = {
        "위험선호": "금리·물가·환율이 우호 방향 → 성장주·소형주에 유리. 위기 후라면 '완화→회복' 패턴 진행 신호.",
        "위험회피": "긴축·물가가속·원화약세 → 방어(우량주·배당·현금) 우위. 성장주 비중 축소.",
        "중립": "혼조 — 신호 엇갈림. 승세테마×구체촉발재 선별 유지, 큰 베팅 자제.",
    }[regime]

    out = {
        "updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "note": "금리·인플레이션·달러환율 3대 축의 수준·추세와 통합 신호. 위기 플레이북(완화=금리인하 트리거)과 연결. 투자권유 아님.",
        "rates": rates, "inflation": inflation, "fx": fx,
        "signal": {"regime": regime, "tilt": tilt, "guidance": guide},
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[compass] 금리 {rates['phase']}({rates['ust10y']}) · 물가 {inflation['phase']} · 환율 {fx['usdkrw']}({fx['phase']}) → 통합 {regime}(tilt {tilt:+d})")


if __name__ == "__main__":
    main()
