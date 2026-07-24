#!/usr/bin/env python3
# 📡 틈새 레이더 — 원본 뉴스 헤드라인을 KRX 전종목 사전으로 기계적으로 스캔해, '작지만 며칠째
# 조용히 반복 언급되는' 상장사·키워드를 결정적으로 찾아낸다(에이전트 판단·salience 편향 제거).
# 핵심 논리: 낮은 누적 + 최근 반복(가속) = 아직 시장이 모르는 틈새 신호. 메가워드/대형주는 제외.
# 누적 카운트를 파일로 관리(매번 오늘치만 스캔) + 최초 1회 article-archive로 히스토리 부트스트랩.
# 표준 라이브러리만.
import json, os, re
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
KRX = os.path.join(DATA, "krx-names.json")
FEED = os.path.join(DATA, "news-feed.json")
ARCHIVE = os.path.join(DATA, "article-archive.json")
CORPUS = os.path.join(DATA, "corpus.jsonl")           # 롤링 원본 헤드라인 누적
CNT = os.path.join(DATA, "niche-counts.json")          # {code: {date: n}} 종목 언급 누적
KWCNT = os.path.join(DATA, "niche-kw-counts.json")     # {term: {date: n}} 키워드 누적
OUT = os.path.join(DATA, "niche-radar.json")

WINDOW = 30        # 관측 창(일)
RECENT = 3         # 최근 반복 판정 창(일)
NICHE_MAX = 18     # 이 누적 이하만 '틈새'(이미 크면 늦음)
SMALL_CAP_MAX = 15000  # 시총 이 억원(=1.5조) 이하만 '작은 회사'(대형주 제외)

def is_hangul(ch):
    return "가" <= ch <= "힣"

# 회사명 매칭에서 뺄 아주 흔한 2글자(오탐 방지). 진짜 신호는 대개 3글자↑.
COMMON2 = {"동양", "대한", "한국", "서울", "미래", "세계", "우리", "대성", "삼성", "현대",
           "미창", "한창", "부산", "경남", "대구", "국도", "이건", "형지", "세방"}
# 키워드 n-gram에서 뺄 메가워드/일반어 stoplist(이미 큰 흐름 = 틈새 아님)
KW_STOP = set("""AI 반도체 AI반도체 메모리 슈퍼사이클 HBM 인플레이션 고환율 금리 인상 우려 연준
휴머노이드 국제유가 외국인 수급 전력 인프라 데이터센터 코스피 코스닥 삼성전자 하이닉스 실적
전망 상승 하락 급등 급락 관련주 대장주 종목 오늘 증시 시장 마감 개장 코스닥 투자 주가 미국
중국 트럼프 관세 원달러 환율 국고채 채권 나스닥 다우 상한가 하한가 매수 매도 순매수 순매도
호르무즈 이란 중동 유가 방산 로봇 이차전지 배터리 바이오 제약 기업 회사 사업 발표 공시""".split())


def get_titles_today(today):
    """오늘 수집 헤드라인(news-feed.json)."""
    out = []
    if os.path.exists(FEED):
        try:
            d = json.load(open(FEED, encoding="utf-8"))
            items = d.get("items", d if isinstance(d, list) else [])
            for it in items:
                t = (it.get("title") or "").strip()
                if t:
                    out.append({"date": today, "title": t, "source": it.get("source", "")})
        except Exception:
            pass
    return out


def bootstrap_from_archive():
    """최초 1회: article-archive의 날짜별 헤드라인으로 히스토리 시드."""
    rows = []
    if not os.path.exists(ARCHIVE):
        return rows
    try:
        arch = json.load(open(ARCHIVE, encoding="utf-8")).get("companies", {})
        seen = set()
        for c in arch.values():
            for a in (c.get("articles") or []):
                t = (a.get("title") or "").strip()
                d = (a.get("date") or "")[:10]
                if t and d and (d, t) not in seen:
                    seen.add((d, t)); rows.append({"date": d, "title": t, "source": a.get("source", "")})
    except Exception:
        pass
    return rows


def load(path, default):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def scan_company(title, name_items):
    """헤드라인에서 상장사명 매칭 → {code} (경계검사 + 부분중복 제거)."""
    hits = {}
    for name, code in name_items:
        idx = title.find(name)
        if idx < 0:
            continue
        before = title[idx - 1] if idx > 0 else " "
        if is_hangul(before):        # 단어 중간 매칭 방지
            continue
        hits[code] = name
    # 부분중복 제거: 다른 매칭명의 substring인 이름은 버림(대한 vs 대한항공)
    names = list(hits.values())
    drop = set()
    for a in names:
        for b in names:
            if a != b and a in b:
                drop.add(a)
    return {code for code, nm in hits.items() if nm not in drop}


def kw_ngrams(title):
    """한글 2~5글자 토큰 추출(공백·조사 경계 기준, stoplist 제외)."""
    toks = re.findall(r"[가-힣]{2,10}", title)
    out = set()
    for t in toks:
        # 앞에서부터 2~5글자 조각(간이 명사 후보)
        for L in (4, 3, 2):
            if len(t) >= L:
                frag = t[:L]
                if frag not in KW_STOP and not any(s in frag for s in KW_STOP):
                    out.add(frag)
    return out


def emergence(daily, today_d, is_kw=False):
    """급증 점수: 낮은 누적 + 최근 반복(가속) 우대."""
    dates = sorted(daily)
    win = [d for d in dates if _ago(d, today_d) <= WINDOW]
    if not win:
        return None
    total = sum(daily[d] for d in win)
    recent = sum(daily[d] for d in win if _ago(d, today_d) <= RECENT)
    active = len([d for d in win if daily[d] > 0])
    last = win[-1]
    first = win[0]
    if _ago(last, today_d) > RECENT:      # 최근에 조용하면 신호 죽음
        return None
    if recent < 2 or active < 2:           # '반복' 아니면 제외(1회성 스파이크 배제)
        return None
    cap = NICHE_MAX * (3 if is_kw else 1)
    if total > cap:                        # 이미 크면 틈새 아님
        return None
    prior_days = max(1, WINDOW - RECENT)
    prior_rate = (total - recent) / prior_days
    accel = recent / RECENT - prior_rate   # 최근 일평균 - 이전 일평균
    score = round(recent * 3 + active * 2 + accel * 5 - total * 0.3, 1)
    return {"total": total, "recent": recent, "activeDays": active,
            "firstSeen": first, "lastSeen": last, "score": score}


def _ago(d, today_d):
    try:
        return (today_d - datetime.strptime(d, "%Y-%m-%d").date()).days
    except Exception:
        return 999


def main():
    if not os.path.exists(KRX):
        print("[niche] krx-names.json 없음 — build-krx-dict 먼저"); return
    krx = json.load(open(KRX, encoding="utf-8")).get("stocks", {})
    # 매칭용 이름 목록(길이 desc = 긴 이름 우선), 흔한 2글자 제외
    name_items = []
    for code, v in krx.items():
        nm = v["name"] if isinstance(v, dict) else v
        if len(nm) < 2 or (len(nm) == 2 and nm in COMMON2):
            continue
        name_items.append((nm, code))
    name_items.sort(key=lambda x: -len(x[0]))
    code2name = {c: (v["name"] if isinstance(v, dict) else v) for c, v in krx.items()}
    code2mkt = {c: (v.get("market") if isinstance(v, dict) else "") for c, v in krx.items()}
    code2cap = {c: (v.get("cap") if isinstance(v, dict) else None) for c, v in krx.items()}

    today = datetime.now(KST).strftime("%Y-%m-%d")
    today_d = datetime.now(KST).date()

    counts = load(CNT, {})
    bootstrap = not counts   # 최초 실행이면 아카이브로 시드

    rows = get_titles_today(today)
    if bootstrap:
        rows = bootstrap_from_archive() + rows
        print(f"[niche] 부트스트랩: 아카이브에서 {len(rows)}개 헤드라인 시드")

    # 롤링 코퍼스 append(원본 보존) — 오늘치만
    with open(CORPUS, "a", encoding="utf-8") as f:
        for r in [r for r in rows if r["date"] == today]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 스캔 → 누적 (회사명 정밀 매칭. 키워드 n-gram은 형태소 분석기 없이 노이즈라 미사용.)
    for r in rows:
        d, title = r["date"], r["title"]
        for code in scan_company(title, name_items):
            counts.setdefault(code, {})[d] = counts.get(code, {}).get(d, 0) + 1

    json.dump(counts, open(CNT, "w", encoding="utf-8"), ensure_ascii=False)

    # 최근 헤드라인 예시(종목별) — 코퍼스에서 근거 제공
    recent_titles = [r for r in rows if _ago(r["date"], today_d) <= WINDOW]

    def samples(code, k=3):
        nm = code2name.get(code, "")
        out = []
        for r in reversed(recent_titles):
            if nm and nm in r["title"]:
                out.append({"date": r["date"], "title": r["title"][:70]})
                if len(out) >= k:
                    break
        return out

    # 종목 틈새 랭킹 (소형주만 — 대형주는 '틈새'가 아님)
    comp = []
    for code, daily in counts.items():
        cap = code2cap.get(code)
        if cap and cap > SMALL_CAP_MAX:      # 대형주 제외
            continue
        e = emergence(daily, today_d)
        if e:
            comp.append({"code": code, "name": code2name.get(code, code),
                         "market": code2mkt.get(code, ""), "cap": cap,
                         **e, "samples": samples(code)})
    comp.sort(key=lambda x: -x["score"])

    out = {
        "updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "note": "원본 헤드라인을 KRX 전종목 사전으로 스캔해 '작지만 반복 언급되는' 소형주 틈새를 결정적으로 포착. 낮은 누적+최근 반복=신호. 대형주 제외. 투자권유 아님.",
        "window": WINDOW, "corpusToday": len([r for r in rows if r["date"] == today]),
        "trackedCompanies": len(counts),
        "companies": comp[:30],
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[niche] 소형 틈새주 {len(comp)} · 추적종목 {len(counts)} · 오늘 헤드라인 {out['corpusToday']}")
    for c in comp[:8]:
        print(f"   {c['name']}({c['code']}) 누적{c['total']} 최근{c['recent']} {c['activeDays']}일 score{c['score']}")


if __name__ == "__main__":
    main()
