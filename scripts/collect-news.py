#!/usr/bin/env python3
# 경제뉴스 RSS 전수 수집기 — 브리핑 전에 실행해 헤드라인을 빠짐없이 모은다.
# JS로 렌더되는 포털 페이지 대신, 순수 XML(RSS)을 긁어 누락을 없앤다.
# 표준 라이브러리만 사용. 산출물:
#   data/news-feed.json : 전체 항목(소스·제목·링크) + 집계 메타
#   data/news-feed.txt  : 브리핑이 읽기 쉬운 헤드라인 목록(소스별)
import json, re, html, sys, os
from urllib.request import Request, urlopen
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))

# (이름, URL) — 실패하는 피드는 자동 skip. 필요시 여기에 추가만 하면 된다.
FEEDS = [
    ("한국경제·경제",  "https://www.hankyung.com/feed/economy"),
    ("한국경제·증권",  "https://www.hankyung.com/feed/finance"),
    ("연합뉴스·경제",  "https://www.yna.co.kr/rss/economy.xml"),
    ("이데일리·경제",  "https://rss.edaily.co.kr/economy_news.xml"),
    ("파이낸셜뉴스",   "https://www.fnnews.com/rss/r20/fn_realnews_economy.xml"),
    ("머니투데이·증권", "https://rss.mt.co.kr/mt_news_stock.xml"),
    ("아시아경제",     "https://www.asiae.co.kr/rss/stock.htm"),
    ("CNBC·Economy",  "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("CNBC·Markets",  "https://www.cnbc.com/id/15839135/device/rss/rss.html"),
    ("CNBC·Finance",  "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
    ("MarketWatch",   "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
]

TAG = re.compile(r"<[^>]+>")
def clean(s):
    if s is None:
        return ""
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = TAG.sub("", s)
    s = html.unescape(s).strip()
    return re.sub(r"\s+", " ", s)

def field(block, name):
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S | re.I)
    return clean(m.group(1)) if m else ""

def fetch(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; news-briefing-bot)"})
    with urlopen(req, timeout=15) as r:
        raw = r.read()
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")

def parse_items(xml):
    out = []
    blocks = re.findall(r"<item\b.*?</item>", xml, re.S | re.I) or \
             re.findall(r"<entry\b.*?</entry>", xml, re.S | re.I)
    for b in blocks:
        title = field(b, "title")
        if not title:
            continue
        link = field(b, "link")
        if not link:  # atom <link href="...">
            m = re.search(r'<link[^>]*href="([^"]+)"', b, re.I)
            link = m.group(1) if m else ""
        out.append({"title": title, "link": link})
    return out

def _base_name(name):
    """'우리로(046970)' -> '우리로' (티커·괄호 제거)."""
    return re.sub(r"\(.*?\)", "", name).strip()

def update_article_archive(all_items, now):
    """수집된 기사를 발굴·회사·선행 종목명으로 매칭해 종목별로 '누적' 저장한다.
    news-feed.json은 매번 덮어써 오늘치만 남지만, 이 아카이브는 과거 기사를 보존해
    종목별로 '언론사별 기사 흐름'을 지속적으로 볼 수 있게 한다(링크 기준 중복 제거)."""
    universe = {}  # base_name(소문자) -> 표시용 원본 종목명
    for idx_file in ("discovery-index.json", "company-index.json", "leading-index.json"):
        try:
            with open(os.path.join(DATA, idx_file), encoding="utf-8") as f:
                comps = json.load(f).get("companies", {})
        except Exception:
            continue
        for full in comps:
            b = _base_name(full)
            if len(b) >= 2:
                universe.setdefault(b.lower(), full)
    if not universe:
        return

    path = os.path.join(DATA, "article-archive.json")
    try:
        with open(path, encoding="utf-8") as f:
            archive = json.load(f)
    except Exception:
        archive = {"companies": {}}
    archive.setdefault("companies", {})

    today = now[:10]
    for it in all_items:
        title = it.get("title", "")
        low = title.lower()
        for b, full in universe.items():
            if b in low:
                entry = archive["companies"].setdefault(full, {"articles": []})
                arts = entry["articles"]
                link = it.get("link", "")
                if any((link and a.get("link") == link) or a.get("title") == title for a in arts):
                    continue  # 이미 있는 기사
                arts.append({"date": today, "source": it.get("source", ""),
                             "title": title, "link": link})

    # 종목별 최신순 정렬 + 과대 누적 방지(종목당 최대 120건 보관)
    for entry in archive["companies"].values():
        entry["articles"].sort(key=lambda a: a.get("date", ""), reverse=True)
        del entry["articles"][120:]

    archive["updatedAt"] = now
    with open(path, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=1)
    matched = sum(1 for e in archive["companies"].values() if e["articles"])
    print(f"[collect] 기사 아카이브 갱신 · 종목 {matched}개에 누적 기사 보유")

def main():
    all_items, per_source, seen = [], {}, set()
    for name, url in FEEDS:
        try:
            items = parse_items(fetch(url))
        except Exception as e:
            sys.stderr.write(f"[collect] skip {name}: {e}\n")
            per_source[name] = 0
            continue
        kept = 0
        for it in items:
            key = it["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            all_items.append({"source": name, "title": it["title"], "link": it["link"]})
            kept += 1
        per_source[name] = kept

    now = datetime.now(KST).isoformat(timespec="seconds")
    payload = {"updatedAt": now, "count": len(all_items),
               "sources": per_source, "items": all_items}
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "news-feed.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # 브리핑이 읽을 헤드라인 목록(소스별 그룹)
    lines = [f"# 경제뉴스 헤드라인 전수 수집 — {now} (총 {len(all_items)}건)", ""]
    cur = None
    for it in all_items:
        if it["source"] != cur:
            cur = it["source"]
            lines.append(f"\n## {cur} ({per_source.get(cur,0)}건)")
        lines.append(f"- {it['title']}")
    with open(os.path.join(DATA, "news-feed.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # 종목별 기사 아카이브 누적(언론사별 흐름·내 관심 추적용)
    try:
        update_article_archive(all_items, now)
    except Exception as e:
        sys.stderr.write(f"[collect] 아카이브 갱신 실패: {e}\n")

    ok = sum(1 for v in per_source.values() if v)
    print(f"[collect] {len(all_items)}건 수집 · 피드 {ok}/{len(FEEDS)}개 성공")
    for n, c in per_source.items():
        print(f"  {'✅' if c else '❌'} {n}: {c}")

if __name__ == "__main__":
    main()
