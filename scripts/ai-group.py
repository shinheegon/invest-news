#!/usr/bin/env python3
# AI 그룹 추적기 — 큐레이션된 data/ai-group.json(AI 필수 밸류체인 종목)에 현재가·등락·모멘텀을
# 붙이고, priceLog로 시세를 매 회차 누적(계속 지켜보기)한다. 티커 유효성도 네이버로 검증.
# 장기 비전 그룹(단기 검증과 별개)이라 D+3 채점은 안 하고, '현재 모멘텀'만 theme-scoreboard에서 표기.
# 결과: data/ai-group-live.json (사이트용). 표준 라이브러리만.
import json, os, re
from urllib.request import Request, urlopen
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
SRC = os.path.join(DATA, "ai-group.json")
SB = os.path.join(DATA, "theme-scoreboard.json")
MISS = os.path.join(DATA, "miss-analysis.json")
OUT = os.path.join(DATA, "ai-group-live.json")

# 카테고리 → theme-scoreboard 테마 매핑(모멘텀 표기용)
CAT2THEME = {
    "hbm": "반도체소재/장비", "pkg": "반도체소재/장비", "substrate": "반도체소재/장비",
    "design": "AI반도체설계(팹리스/IP)", "power": "AI전력/데이터센터",
    "cooling": "AI전력/데이터센터", "optics": "반도체소재/장비", "robot": "로봇/휴머노이드",
}


def get(url, enc="euc-kr"):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (news-briefing)"})
    return urlopen(req, timeout=12).read().decode(enc, "ignore")


def naver_basic(code):
    """현재가 + 정식종목명(티커 검증용)."""
    try:
        j = json.loads(get(f"https://m.stock.naver.com/api/stock/{code}/basic", "utf-8"))
        price = j.get("closePrice") or j.get("dealTrendInfos", [{}])[0].get("closePrice")
        price = int(str(price).replace(",", "")) if price else None
        return {"name": j.get("stockName"), "price": price,
                "changeRate": j.get("fluctuationsRatio")}
    except Exception:
        return {"name": None, "price": None, "changeRate": None}


def main():
    if not os.path.exists(SRC):
        print("[ai-group] ai-group.json 없음 — skip"); return
    src = json.load(open(SRC, encoding="utf-8"))
    sb = json.load(open(SB, encoding="utf-8")) if os.path.exists(SB) else {}
    win, lose = set(sb.get("winning", [])), set(sb.get("losing", []))
    miss = json.load(open(MISS, encoding="utf-8")) if os.path.exists(MISS) else {}
    theme_miss = (miss.get("learnedFilter") or {}).get("themeMissRate", {})
    macro = miss.get("macro", {})

    # 기존 priceLog 보존(누적)
    prev = {}
    if os.path.exists(OUT):
        for c in json.load(open(OUT, encoding="utf-8")).get("companies", []):
            prev[c.get("ticker")] = c.get("priceLog", [])

    today = datetime.now(KST).strftime("%Y-%m-%d")
    comps = []
    for c in src.get("companies", []):
        code = c.get("ticker")
        b = naver_basic(code) if code else {"name": None, "price": None, "changeRate": None}
        # 티커 검증(정식명이 큐레이션명과 어긋나면 표시)
        official = b.get("name")
        mismatch = bool(official and official.replace(" ", "") != c["name"].replace(" ", ""))
        # priceLog 누적
        plog = list(prev.get(code, []))
        if b.get("price") and not any(p.get("date") == today for p in plog):
            plog.append({"date": today, "price": b["price"]})
        first = plog[0]["price"] if plog else None
        last = plog[-1]["price"] if plog else b.get("price")
        since = round((last - first) / first * 100, 1) if first and last else None
        # 현재 모멘텀(검증 테마 스코어보드 + 빗나감률)
        theme = CAT2THEME.get(c.get("category"), "기타")
        mom = "승세" if theme in win else "열세" if theme in lose else "중립"
        tmr = theme_miss.get(theme)
        comps.append({**c, "official": official, "tickerMismatch": mismatch,
                      "price": b.get("price"), "changeRate": b.get("changeRate"),
                      "sinceAddedPct": since, "priceLog": plog,
                      "momentum": mom, "themeMissRate": tmr})

    out = {
        "updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "note": src.get("note"),
        "categories": src.get("categories", []),
        "macro": {"regime": macro.get("regime"), "guidance": macro.get("guidance")},
        "companies": comps,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    mism = [c["name"] for c in comps if c["tickerMismatch"]]
    print(f"[ai-group] {len(comps)}종목 갱신 · 시세 {sum(1 for c in comps if c['price'])}건"
          f" · 티커불일치 {len(mism)}{('='+str(mism)) if mism else ''} · 거시 {macro.get('regime')}")


if __name__ == "__main__":
    main()
