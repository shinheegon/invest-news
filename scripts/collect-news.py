#!/usr/bin/env python3
# 경제뉴스 RSS 전수 수집기 — 브리핑 전에 실행해 헤드라인을 빠짐없이 모은다.
# JS로 렌더되는 포털 페이지 대신, 순수 XML(RSS)을 긁어 누락을 없앤다.
# 표준 라이브러리만 사용. 산출물:
#   data/news-feed.json : 전체 항목(소스·제목·링크) + 집계 메타
#   data/news-feed.txt  : 브리핑이 읽기 쉬운 헤드라인 목록(소스별)
import json, re, html, sys, os, time
from urllib.request import Request, urlopen
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
from company_matcher import (
    entity_matches,
    load_company_entities,
    matching_entities,
    split_company_name,
)

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
MAX_AGE_DAYS = 3        # 이보다 오래된 기사는 '오늘 뉴스' 아님 → 배제(구기사 혼입 차단)
MIN_ITEMS_WARN = 150    # 이 미만이면 수집 이상 경고

# (이름, URL) — 실패하는 피드는 자동 skip. 필요시 여기에 추가만 하면 된다.
FEEDS = [
    ("한국경제·경제",  "https://www.hankyung.com/feed/economy"),
    ("한국경제·증권",  "https://www.hankyung.com/feed/finance"),
    ("연합뉴스·경제",  "https://www.yna.co.kr/rss/economy.xml"),
    ("이데일리·경제",  "https://rss.edaily.co.kr/economy_news.xml"),
    ("파이낸셜뉴스",   "https://www.fnnews.com/rss/r20/fn_realnews_economy.xml"),
    ("파이낸셜·증권",  "https://www.fnnews.com/rss/r20/fn_realnews_stock.xml"),
    ("머니투데이·증권", "https://rss.mt.co.kr/mt_news_stock.xml"),
    ("아시아경제",     "https://www.asiae.co.kr/rss/stock.htm"),
    ("이데일리·증권",  "https://rss.edaily.co.kr/stock_news.xml"),
    ("뉴시스·경제",    "https://newsis.com/RSS/economy.xml"),
    ("연합인포맥스",   "https://news.einfomax.co.kr/rss/allArticle.xml"),
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

def fetch(url, tries=3):
    """재시도 + http 폴백. 한 번 실패로 0건 되는 것 방지."""
    last = None
    for i in range(tries):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; news-briefing-bot)"})
            with urlopen(req, timeout=15) as r:
                raw = r.read()
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "ignore")
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last

def parse_date(block):
    """RSS pubDate / Atom published·updated / dc:date 파싱 → KST datetime(없으면 None)."""
    raw = ""
    for tag in ("pubDate", "published", "updated", "dc:date", "date"):
        raw = field(block, tag)
        if raw:
            break
    if not raw:
        return None
    # RFC822 (RSS)
    try:
        dt = parsedate_to_datetime(raw)
        if dt:
            return dt.astimezone(KST) if dt.tzinfo else dt.replace(tzinfo=KST)
    except Exception:
        pass
    # ISO 8601 (Atom)
    try:
        s = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.astimezone(KST) if dt.tzinfo else dt.replace(tzinfo=KST)
    except Exception:
        pass
    # YYYY-MM-DD 또는 YYYY.MM.DD
    m = re.search(r"(20\d{2})[-.](\d{1,2})[-.](\d{1,2})", raw)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=KST)
        except Exception:
            pass
    return None

def parse_items(xml, now_dt):
    """항목 파싱 + 날짜 필터(최근 MAX_AGE_DAYS일만). 날짜 없으면 보류(keep)."""
    out, dropped_old = [], 0
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
        dt = parse_date(b)
        if dt is not None:
            age = (now_dt - dt).days
            if age > MAX_AGE_DAYS or age < -1:   # 구기사·미래오류 배제
                dropped_old += 1
                continue
        out.append({"title": title, "link": link,
                    "date": dt.strftime("%Y-%m-%d") if dt else now_dt.strftime("%Y-%m-%d")})
    return out, dropped_old

def update_article_archive(all_items, now):
    """수집된 기사를 발굴·회사·선행 종목명으로 매칭해 종목별로 '누적' 저장한다.
    news-feed.json은 매번 덮어써 오늘치만 남지만, 이 아카이브는 과거 기사를 보존해
    종목별로 '언론사별 기사 흐름'을 지속적으로 볼 수 있게 한다.

    매번 기존 기사까지 새 매칭 규칙으로 재검사하므로, 과거의 오탐 기사도 자동 제거되고
    같은 티커의 약칭(NC)·정식명(엔씨소프트)은 하나의 대표 회사로 합쳐진다."""
    entities = load_company_entities(DATA)
    if not entities:
        return

    path = os.path.join(DATA, "article-archive.json")
    try:
        with open(path, encoding="utf-8") as f:
            archive = json.load(f)
    except Exception:
        archive = {"companies": {}}
    archive.setdefault("companies", {})

    rebuilt = {"companies": {}, "updatedAt": now}
    entity_by_name = {entity.name: entity for entity in entities}

    def archive_entity(display_name):
        exact = entity_by_name.get(display_name)
        if exact:
            return exact
        base, ticker = split_company_name(display_name)
        return next(
            (
                entity
                for entity in entities
                if entity.ticker == ticker and base in entity.aliases
            ),
            None,
        )

    def add_article(entity, article):
        entry = rebuilt["companies"].setdefault(entity.name, {"articles": []})
        key = article.get("link") or article.get("title")
        if key and not any(
            (existing.get("link") or existing.get("title")) == key
            for existing in entry["articles"]
        ):
            entry["articles"].append(article)

    # 기존 회사 귀속은 유지하면서 새 규칙에 맞지 않는 기사만 제거한다.
    # 전체 기사를 모든 회사에 다시 뿌리면 잘못 생성된 중복 티커끼리 섞일 수 있다.
    for display_name, entry in archive["companies"].items():
        entity = archive_entity(display_name)
        if not entity:
            continue
        for article in entry.get("articles", []):
            if entity_matches(article.get("title", ""), entity):
                add_article(entity, article)

    today = now[:10]
    for item in all_items:
        article = {
            "date": today,
            "source": item.get("source", ""),
            "title": item.get("title", ""),
            "link": item.get("link", ""),
        }
        for entity in matching_entities(article["title"], entities):
            add_article(entity, article)

    # 종목별 최신순 정렬 + 과대 누적 방지(종목당 최대 120건 보관)
    for entry in rebuilt["companies"].values():
        entry["articles"].sort(
            key=lambda article: (
                article.get("date", ""),
                article.get("source", ""),
                article.get("title", ""),
            ),
            reverse=True,
        )
        del entry["articles"][120:]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(rebuilt, f, ensure_ascii=False, indent=1)
    matched = sum(1 for entry in rebuilt["companies"].values() if entry["articles"])
    print(f"[collect] 기사 아카이브 재분류 · 종목 {matched}개에 누적 기사 보유")

def main():
    now_dt = datetime.now(KST)
    if "--repair-archive-only" in sys.argv:
        update_article_archive([], now_dt.isoformat(timespec="seconds"))
        return

    all_items, per_source, seen = [], {}, set()
    total_dropped = 0
    for name, url in FEEDS:
        try:
            items, dropped = parse_items(fetch(url), now_dt)
        except Exception as e:
            sys.stderr.write(f"[collect] skip {name}: {e}\n")
            per_source[name] = 0
            continue
        total_dropped += dropped
        kept = 0
        for it in items:
            key = it["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            all_items.append({"source": name, "title": it["title"],
                              "link": it["link"], "date": it.get("date")})
            kept += 1
        per_source[name] = kept

    now = now_dt.isoformat(timespec="seconds")
    payload = {"updatedAt": now, "count": len(all_items), "droppedOld": total_dropped,
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
    print(f"[collect] {len(all_items)}건 수집 · 피드 {ok}/{len(FEEDS)}개 성공 · 구기사 배제 {total_dropped}건")
    if len(all_items) < MIN_ITEMS_WARN:
        sys.stderr.write(f"[collect] ⚠️ 수집량 부족({len(all_items)}<{MIN_ITEMS_WARN}) — 피드 상태 점검 필요\n")
    for n, c in per_source.items():
        print(f"  {'✅' if c else '❌'} {n}: {c}")

if __name__ == "__main__":
    main()
