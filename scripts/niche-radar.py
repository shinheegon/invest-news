#!/usr/bin/env python3
"""원본 뉴스에서 반복 언급되는 소형 상장사를 멱등적으로 탐지한다."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from company_matcher import alias_matches


PROJECT = Path(__file__).resolve().parents[1]
DATA = PROJECT / "data"
KST = timezone(timedelta(hours=9))
KRX = DATA / "krx-names.json"
FEED = DATA / "news-feed.json"
ARCHIVE = DATA / "article-archive.json"
CORPUS = DATA / "corpus.jsonl"
CNT = DATA / "niche-counts.json"
OUT = DATA / "niche-radar.json"

WINDOW = 30
RECENT = 3
NICHE_MAX = 18
SMALL_CAP_MAX = 15000  # 억원(1.5조)

# 일반 문장에서도 회사와 무관하게 쓰이는 이름은 회사형 문장부호가 있을 때만 인정한다.
AMBIGUOUS_NAMES = {
    "NEW",
    "미래산업",
    "우리기술",
    "우리산업",
}
GENERATED_MARKERS = ("🌱", "🔮", "조기 출몰", "선점 후보", "발굴 언급")
NEGATIVE_TERMS = {
    "실패",
    "급락",
    "하락",
    "적자",
    "부진",
    "쇼크",
    "소송",
    "제재",
    "중단",
    "취소",
    "기각",
    "압수수색",
    "상장폐지",
    "거래정지",
}
CATALYST_TERMS = {
    "수주",
    "계약",
    "공급",
    "납품",
    "선정",
    "특허",
    "승인",
    "확보",
    "신제품",
    "증설",
    "양산",
    "출시",
    "협력",
    "투자",
    "인수",
    "흑자",
    "성장",
    "확대",
}


def load_json(path: Path, default):
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError, TypeError):
        return default


def ago(value: str, today: date) -> int:
    try:
        return (today - datetime.strptime(value, "%Y-%m-%d").date()).days
    except (TypeError, ValueError):
        return 999


def is_raw_headline(title: str) -> bool:
    """과거 브리핑에서 역수집된 합성 문장을 원본 기사로 재사용하지 않는다."""
    value = (title or "").strip()
    if not value or value.startswith(("-", "•")):
        return False
    return not any(marker in value for marker in GENERATED_MARKERS)


def get_feed_rows(today: str) -> list[dict]:
    payload = load_json(FEED, {})
    items = payload.get("items", []) if isinstance(payload, dict) else []
    rows = []
    for item in items:
        title = (item.get("title") or "").strip()
        if is_raw_headline(title):
            rows.append(
                {
                    "date": today,
                    "title": title,
                    "source": item.get("source", ""),
                }
            )
    return rows


def bootstrap_rows() -> list[dict]:
    archive = load_json(ARCHIVE, {}).get("companies", {})
    rows = []
    for entry in archive.values():
        for article in entry.get("articles", []):
            title = (article.get("title") or "").strip()
            day = (article.get("date") or "")[:10]
            if day and is_raw_headline(title):
                rows.append(
                    {
                        "date": day,
                        "title": title,
                        "source": article.get("source", ""),
                    }
                )
    return rows


def read_corpus() -> list[dict]:
    rows = []
    try:
        with CORPUS.open(encoding="utf-8") as file:
            for line in file:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("date") and is_raw_headline(row.get("title", "")):
                    rows.append(row)
    except OSError:
        pass
    return rows


def merge_corpus(existing: list[dict], incoming: list[dict], today: date) -> list[dict]:
    """같은 기사 재실행을 중복 집계하지 않고 최근 관측창만 유지한다."""
    unique: dict[tuple[str, str], dict] = {}
    for row in [*existing, *incoming]:
        day = (row.get("date") or "")[:10]
        title = (row.get("title") or "").strip()
        age = ago(day, today)
        if not title or not is_raw_headline(title) or not 0 <= age < WINDOW:
            continue
        key = (day, title.casefold())
        unique.setdefault(
            key,
            {"date": day, "title": title, "source": row.get("source", "")},
        )
    return sorted(
        unique.values(),
        key=lambda row: (row["date"], row["title"].casefold()),
    )


def write_corpus(rows: list[dict]) -> None:
    with CORPUS.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def company_name_matches(title: str, name: str, code: str) -> bool:
    if code and code in title and re.search(
        rf"(?<!\d){re.escape(code)}(?!\d)", title
    ):
        return True
    if name.casefold() not in title.casefold():
        return False
    if not alias_matches(title, name):
        return False
    if name not in AMBIGUOUS_NAMES:
        return True
    return re.search(rf"{re.escape(name)}\s*[,·:（(]", title) is not None


def scan_company(
    title: str, name_items: list[tuple[str, str]]
) -> set[str]:
    """회사명 경계와 중첩을 검사해 제목에 실제 등장한 종목코드를 반환한다."""
    hits = {
        code: name
        for name, code in name_items
        if company_name_matches(title, name, code)
    }
    drop = {
        code
        for code, name in hits.items()
        if any(name != other and name in other for other in hits.values())
    }
    return set(hits) - drop


def emergence(daily: dict[str, int], today: date) -> dict | None:
    days = sorted(day for day in daily if 0 <= ago(day, today) < WINDOW)
    if not days:
        return None
    total = sum(daily[day] for day in days)
    recent = sum(daily[day] for day in days if ago(day, today) < RECENT)
    active = sum(1 for day in days if daily[day] > 0)
    if ago(days[-1], today) >= RECENT or recent < 2 or active < 2:
        return None
    if total > NICHE_MAX:
        return None
    prior_rate = (total - recent) / max(1, WINDOW - RECENT)
    acceleration = recent / RECENT - prior_rate
    score = round(recent * 3 + active * 2 + acceleration * 5 - total * 0.3, 1)
    return {
        "total": total,
        "recent": recent,
        "activeDays": active,
        "firstSeen": days[0],
        "lastSeen": days[-1],
        "score": score,
    }


def signal_mentions(
    matched_rows: list[tuple[dict, set[str]]], code: str, today: date
) -> tuple[int, int]:
    titles = [
        row["title"]
        for row, codes in matched_rows
        if code in codes and ago(row["date"], today) < RECENT
    ]
    risk = sum(any(term in title for term in NEGATIVE_TERMS) for title in titles)
    catalyst = sum(any(term in title for term in CATALYST_TERMS) for title in titles)
    return risk, catalyst


def main() -> int:
    krx = load_json(KRX, {}).get("stocks", {})
    if not krx:
        print("[niche] krx-names.json 없음 — build-krx-dict 먼저")
        return 1

    name_items = []
    for code, value in krx.items():
        name = value.get("name", "") if isinstance(value, dict) else str(value)
        # 두 글자 회사명은 일반어·약어 오탐 위험이 커서 레이더 자동승격에서 제외한다.
        if len(name) >= 3:
            name_items.append((name, code))
    name_items.sort(key=lambda item: -len(item[0]))

    code_to_name = {
        code: value.get("name", code) if isinstance(value, dict) else str(value)
        for code, value in krx.items()
    }
    code_to_market = {
        code: value.get("market", "") if isinstance(value, dict) else ""
        for code, value in krx.items()
    }
    code_to_cap = {
        code: value.get("cap") if isinstance(value, dict) else None
        for code, value in krx.items()
    }

    now = datetime.now(KST)
    today = now.date()
    today_text = today.isoformat()
    existing = read_corpus()
    # 초기 버전이 오늘치만 저장했어도 과거 원문을 복구할 수 있도록 아카이브를
    # 매번 병합한다. merge_corpus가 중복 제거하므로 재실행해도 점수는 늘지 않는다.
    seed = bootstrap_rows()
    rows = merge_corpus(existing, [*seed, *get_feed_rows(today_text)], today)
    write_corpus(rows)

    counts: dict[str, dict[str, int]] = {}
    matched_rows: list[tuple[dict, set[str]]] = []
    for row in rows:
        codes = scan_company(row["title"], name_items)
        matched_rows.append((row, codes))
        for code in codes:
            daily = counts.setdefault(code, {})
            daily[row["date"]] = daily.get(row["date"], 0) + 1

    with CNT.open("w", encoding="utf-8") as file:
        json.dump(counts, file, ensure_ascii=False, indent=1)

    def samples(code: str, limit: int = 3) -> list[dict]:
        selected = []
        for row, codes in reversed(matched_rows):
            if code in codes:
                selected.append(
                    {"date": row["date"], "title": row["title"][:100]}
                )
                if len(selected) >= limit:
                    break
        return selected

    companies = []
    for code, daily in counts.items():
        cap = code_to_cap.get(code)
        if cap is None or cap > SMALL_CAP_MAX:
            continue
        metrics = emergence(daily, today)
        if not metrics:
            continue
        risk, catalyst = signal_mentions(matched_rows, code, today)
        # 최근 반복이 전부 악재이고 성장 촉발재가 없으면 발굴 후보에서 제외한다.
        if risk and not catalyst:
            continue
        companies.append(
            {
                "code": code,
                "name": code_to_name.get(code, code),
                "market": code_to_market.get(code, ""),
                "cap": cap,
                **metrics,
                "riskMentions": risk,
                "catalystMentions": catalyst,
                "samples": samples(code),
            }
        )
    companies.sort(key=lambda company: -company["score"])

    payload = {
        "updatedAt": now.isoformat(timespec="seconds"),
        "note": (
            "원본 헤드라인의 반복 언급을 탐지한 조사 후보이며 투자권유가 아니다. "
            "동일 기사 재실행은 한 번만 집계하고, 순수 악재 반복과 모호한 회사명은 제외한다."
        ),
        "window": WINDOW,
        "corpusToday": sum(row["date"] == today_text for row in rows),
        "trackedCompanies": len(counts),
        "companies": companies[:30],
    }
    with OUT.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=1)

    print(
        f"[niche] 소형 틈새주 {len(companies)} · 추적종목 {len(counts)} "
        f"· 오늘 고유 헤드라인 {payload['corpusToday']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
