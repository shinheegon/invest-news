#!/usr/bin/env python3
# 유망 대기 선별기 — 아직 검증 안 끝난(대기) 예측 중에서 "학습된 승리 패턴"에 맞는 종목을
# 골라 순위를 매긴다. 규칙: [승세 테마] + [구체 촉발재(수주·선정·특허·납품…)]일수록 높은 점수.
# 이게 자기학습을 '앞으로' 써먹는 부분 — 검증으로 배운 걸 현재 후보 우선순위에 반영.
# 결정적·네트워크 없음(verification.json + theme-scoreboard.json만 읽음). 표준 라이브러리만.
import json, os
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
VF = os.path.join(DATA, "verification.json")
SB = os.path.join(DATA, "theme-scoreboard.json")
OUT = os.path.join(DATA, "watch-priority.json")

# theme-scoreboard.py와 동일한 카테고리 규칙(동기화 유지).
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
GOOD_SIG = ["수주", "선정", "납품", "특허", "신제품", "공급계약", "증설", "캐파", "독점", "수주잔고"]

def cat(theme):
    t = (theme or "").lower()
    for name, kws in CATS:
        if any(k in t for k in kws):
            return name
    return "기타"

def main():
    if not os.path.exists(VF):
        print("[watch] verification.json 없음 — skip"); return
    cases = json.load(open(VF, encoding="utf-8")).get("cases", [])
    sb = json.load(open(SB, encoding="utf-8")) if os.path.exists(SB) else {}
    win, lose = set(sb.get("winning", [])), set(sb.get("losing", []))

    ranked = []
    for c in cases:
        # 대기(검증 미완) + 오를 것으로 본 예측(후발경고 제외)만
        if c.get("status") == "verified" or c.get("type") == "warning":
            continue
        th = cat(c.get("theme"))
        sigs = c.get("signals", []) or []
        concrete = [s for s in sigs if any(g in s for g in GOOD_SIG)]
        score, why = 0, []
        if th in win:
            score += 3; why.append(f"승세테마({th})")
        elif th in lose:
            score -= 3; why.append(f"⚠️열세테마({th})")
        else:
            why.append(f"중립테마({th})")
        if concrete:
            score += 2; why.append("구체촉발재: " + " / ".join(concrete)[:40])
        elif sigs:
            why.append("신호약함(테마첫거론류)")
        # 반복 포착 가산(선행 신호가 여러 날 반복이면 강함)
        rep = c.get("count") or len([s for s in sigs if "반복" in s or "회" in s])
        if isinstance(rep, int) and rep >= 3:
            score += 1; why.append(f"반복{rep}")
        ranked.append({
            "name": c.get("name"), "type": c.get("type"), "theme": th,
            "flagDate": c.get("flagDate"), "score": score,
            "concrete": bool(concrete), "why": " · ".join(why),
        })
    ranked.sort(key=lambda x: (-x["score"], x["flagDate"] or ""))

    out = {
        "updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "note": "대기 예측을 학습패턴(승세테마+구체촉발재)으로 점수화. 투자권유 아님.",
        "top": [r for r in ranked if r["score"] >= 3][:15],
        "avoid": [r for r in ranked if r["score"] <= -3][:10],
        "all": ranked,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[watch] 대기 {len(ranked)}건 · 유망(≥3점) {len(out['top'])} · 회피(≤-3) {len(out['avoid'])}")

if __name__ == "__main__":
    main()
