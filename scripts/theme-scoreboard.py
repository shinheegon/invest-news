#!/usr/bin/env python3
# 테마 스코어보드 — 검증 결과(verification.json)를 테마별로 집계해 "시장이 어느 테마를
# 실제로 보상했는지(자금 로테이션)"를 산출한다. 발굴/선행 엔진이 이걸 읽어 승세 테마를
# 우대하고 지는 테마를 경계한다(자기학습 피드백). 표준 라이브러리만.
import json, os
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
VF = os.path.join(DATA, "verification.json")
OUT = os.path.join(DATA, "theme-scoreboard.json")

# 세부 테마명을 큰 카테고리로 정규화(키워드 우선순위 순).
CATS = [
    ("로봇/휴머노이드", ["휴머노이드", "로봇", "모션", "액추", "감속", "구동"]),
    ("AI반도체설계(팹리스/IP)", ["팹리스", "설계자산", "디자인", "설계", "ip", "칩스앤"]),
    ("우주/방산", ["우주", "위성", "방산", "로켓", "발사"]),
    ("반도체소재/장비", ["hbm", "소재", "도금", "장비", "소부장", "후공정", "본딩", "기판", "유리기판"]),
    ("AI전력/데이터센터", ["데이터센터", "전력", "변압", "냉각", "전선"]),
    ("신재생에너지", ["풍력", "태양", "신재생", "해상", "수소", "smr", "원전"]),
    ("이차전지", ["2차전지", "이차전지", "전지", "배터리"]),
    ("피지컬AI", ["피지컬ai", "피지컬"]),
    ("바이오/의료", ["바이오", "의료", "제약", "분리막"]),
]

def cat(theme):
    t = (theme or "").lower()
    for name, kws in CATS:
        if any(k in t for k in kws):
            return name
    return "기타"

def d3(c):
    for k in c.get("checks", []):
        if k.get("horizon") == "D+3":
            return k
    return (c.get("checks") or [None])[-1]

def main():
    if not os.path.exists(VF):
        print("[theme] verification.json 없음 — skip"); return
    cases = json.load(open(VF, encoding="utf-8")).get("cases", [])

    agg = {}
    for c in cases:
        fv = c.get("finalVerdict")
        if fv not in ("적중", "빗나감", "중립"):
            continue
        ch = d3(c) or {}
        chg = ch.get("excessPct")               # 초과수익(종목−지수) 우선
        if not isinstance(chg, (int, float)):
            chg = ch.get("changePct")
        k = cat(c.get("theme"))
        a = agg.setdefault(k, {"n": 0, "hit": 0, "miss": 0, "chgs": []})
        a["n"] += 1
        if fv == "적중": a["hit"] += 1
        if fv == "빗나감": a["miss"] += 1
        if isinstance(chg, (int, float)): a["chgs"].append(chg)

    themes = []
    for k, a in agg.items():
        avg = round(sum(a["chgs"]) / len(a["chgs"]), 1) if a["chgs"] else None
        mom = "상승" if (avg is not None and avg >= 3) else "하락" if (avg is not None and avg <= -3) else "중립"
        themes.append({"theme": k, "n": a["n"], "hit": a["hit"], "miss": a["miss"],
                       "hitRate": round(a["hit"] / a["n"] * 100, 1) if a["n"] else None,
                       "avgD3": avg, "momentum": mom})
    themes.sort(key=lambda x: (x["avgD3"] is None, -(x["avgD3"] or -999)))

    # "기타"(미분류 잡동사니)는 코헤런트한 테마 신호가 아니므로 승세/열세에서 제외.
    out = {"updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
           "themes": themes,
           "winning": [t["theme"] for t in themes if t["momentum"] == "상승" and t["theme"] != "기타"],
           "losing": [t["theme"] for t in themes if t["momentum"] == "하락" and t["theme"] != "기타"]}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[theme] {len(themes)}개 테마 · 승세 {out['winning']} · 열세 {out['losing']}")

if __name__ == "__main__":
    main()
