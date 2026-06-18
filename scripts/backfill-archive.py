#!/usr/bin/env python3
# 과거 브리핑(briefings/*.md)에 흩어진 '종목 + 출처 링크'를 긁어
# 기사 아카이브(data/article-archive.json)에 소급 병합한다.
# - 같은 줄에 종목 토큰 1개 + [출처](url)가 함께 있으면 그 종목의 기사로 본다.
# - 날짜는 파일명(YYYY-MM-DD-AM|PM)에서, 언론사는 URL 도메인에서 추정.
# - 링크 기준 중복 제거. collect-news.py와 같은 article-archive.json을 공유한다.
import json, os, re, glob

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
ARCHIVE_PATH = os.path.join(DATA, "article-archive.json")

# 종목 토큰: 한글/영문 이름 + (6자리코드 | 영문티커)
COMPANY = re.compile(r"([가-힣A-Za-z0-9·&]+\((?:\d{6}|[A-Z]{1,6})\))")
SOURCE = re.compile(r"\[출처\]\((https?://[^)\s]+)\)")
FILEDATE = re.compile(r"(\d{4}-\d{2}-\d{2})-(AM|PM)\.md$")

DOMAIN_PUB = [
    ("hankyung.com", "한국경제"), ("asiae.co.kr", "아시아경제"),
    ("yna.co.kr", "연합뉴스"), ("edaily.co.kr", "이데일리"),
    ("fnnews.com", "파이낸셜뉴스"), ("mt.co.kr", "머니투데이"),
    ("cnbc.com", "CNBC"), ("marketwatch.com", "MarketWatch"),
    ("dowjones.io", "MarketWatch"), ("economist.co.kr", "이코노미스트"),
    ("investing.com", "Investing"), ("tradingeconomics.com", "TradingEconomics"),
    ("sedaily.com", "서울경제"), ("mk.co.kr", "매일경제"),
    ("chosun.com", "조선비즈"), ("etnews.com", "전자신문"),
    ("thelec.kr", "디일렉"), ("reuters.com", "Reuters"),
    ("bloomberg.com", "Bloomberg"),
]

def publisher(url):
    for dom, name in DOMAIN_PUB:
        if dom in url:
            return name
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else "기타"

def clean_title(line):
    t = line.strip().strip("|").strip()
    t = re.sub(r"\[출처\]\([^)]+\)", "", t)        # 출처 링크 제거
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)  # 기타 링크는 표시텍스트만
    t = t.replace("**", "").replace("`", "")
    t = re.sub(r"\s*\|\s*", " · ", t)               # 표 칸 구분 → ·
    t = re.sub(r"\s+", " ", t).strip(" ·")
    return t[:90] if t else ""

def main():
    try:
        with open(ARCHIVE_PATH, encoding="utf-8") as f:
            archive = json.load(f)
    except Exception:
        archive = {"companies": {}}
    archive.setdefault("companies", {})

    # 유효 종목명 집합(인덱스에 있는 종목만 받아들여 오탐 방지)
    known = set()
    for idx in ("discovery-index.json", "company-index.json", "leading-index.json"):
        try:
            with open(os.path.join(DATA, idx), encoding="utf-8") as f:
                known |= set(json.load(f).get("companies", {}).keys())
        except Exception:
            pass

    added = 0
    for path in sorted(glob.glob(os.path.join(PROJECT, "briefings", "*.md"))):
        m = FILEDATE.search(os.path.basename(path))
        if not m:
            continue
        date = m.group(1)
        with open(path, encoding="utf-8") as f:
            for line in f:
                comps = COMPANY.findall(line)
                links = SOURCE.findall(line)
                if len(comps) != 1 or not links:
                    continue                     # 종목이 모호한 줄은 건너뜀
                name = comps[0]
                if known and name not in known:
                    continue
                title = clean_title(line) or f"{name} 발굴 언급"
                entry = archive["companies"].setdefault(name, {"articles": []})
                arts = entry["articles"]
                for link in links:
                    if any(a.get("link") == link for a in arts):
                        continue
                    arts.append({"date": date, "source": publisher(link),
                                 "title": title, "link": link})
                    added += 1

    for entry in archive["companies"].values():
        entry["articles"].sort(key=lambda a: a.get("date", ""), reverse=True)
        del entry["articles"][120:]

    with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=1)
    have = sum(1 for e in archive["companies"].values() if e["articles"])
    print(f"[backfill] 과거 브리핑에서 {added}건 소급 추가 · 현재 기사 보유 종목 {have}개")

if __name__ == "__main__":
    main()
