#!/usr/bin/env python3
"""자동 생성 결과가 배포 가능한지 결정적으로 검사한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from company_matcher import entity_matches, load_company_entities


REQUIRED_HEADINGS = (
    "# 📰 투자 브리핑",
    "## 🎯 한눈에 보기",
    "## 🔗 출처 링크 모음",
)


def validate_json_files(project: Path, errors: list[str]) -> None:
    for root in (project / "data", project / "docs" / "data"):
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            try:
                with path.open(encoding="utf-8") as file:
                    json.load(file)
            except (OSError, ValueError) as error:
                errors.append(f"JSON 오류: {path.relative_to(project)} ({error})")


def validate_briefing(
    project: Path, date: str, session: str, errors: list[str]
) -> None:
    briefing = project / "briefings" / f"{date}-{session}.md"
    latest = project / "data" / "latest.md"
    for path in (briefing, latest):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            errors.append(f"필수 결과 없음: {path.relative_to(project)} ({error})")
            continue
        if len(text.strip()) < 500:
            errors.append(f"결과가 비정상적으로 짧음: {path.relative_to(project)}")
        for heading in REQUIRED_HEADINGS:
            if heading not in text:
                errors.append(f"필수 섹션 누락: {path.relative_to(project)} → {heading}")

    copied_briefing = (
        project / "docs" / "data" / "briefings" / f"{date}-{session}.md"
    )
    copied_latest = project / "docs" / "data" / "latest.md"
    for source, copied in ((briefing, copied_briefing), (latest, copied_latest)):
        try:
            if source.read_bytes() != copied.read_bytes():
                errors.append(
                    f"사이트 복사본 불일치: {copied.relative_to(project)}"
                )
        except OSError as error:
            errors.append(
                f"사이트 복사본 없음: {copied.relative_to(project)} ({error})"
            )

    manifest_path = project / "docs" / "data" / "briefings.json"
    try:
        with manifest_path.open(encoding="utf-8") as file:
            manifest = json.load(file)
        expected = f"briefings/{date}-{session}.md"
        if expected not in {
            item.get("file") for item in manifest.get("briefings", [])
        }:
            errors.append(f"브리핑 목록 누락: {expected}")
    except (OSError, ValueError) as error:
        errors.append(f"브리핑 목록 읽기 실패: {error}")


def validate_article_archive(project: Path, errors: list[str]) -> None:
    path = project / "data" / "article-archive.json"
    try:
        with path.open(encoding="utf-8") as file:
            archive = json.load(file)
    except (OSError, ValueError) as error:
        errors.append(f"기사 아카이브 읽기 실패: {error}")
        return

    copied_path = project / "docs" / "data" / "article-archive.json"
    try:
        if path.read_bytes() != copied_path.read_bytes():
            errors.append("사이트 기사 아카이브 복사본 불일치")
    except OSError as error:
        errors.append(f"사이트 기사 아카이브 없음: {error}")

    entities = {
        entity.name: entity
        for entity in load_company_entities(str(project / "data"))
    }
    for company, entry in archive.get("companies", {}).items():
        entity = entities.get(company)
        if not entity:
            errors.append(f"기사 아카이브에 인덱스 없는 회사: {company}")
            continue
        seen = set()
        for article in entry.get("articles", []):
            title = article.get("title", "")
            key = article.get("link") or title
            if key in seen:
                errors.append(f"중복 기사: {company} → {title}")
            seen.add(key)
            if not entity_matches(title, entity):
                errors.append(f"회사명 불일치 기사: {company} → {title}")


def validate_dashboard_security(project: Path, errors: list[str]) -> None:
    index = (project / "docs" / "index.html").read_text(encoding="utf-8")
    app = (project / "docs" / "app.js").read_text(encoding="utf-8")
    if "dompurify" not in index.casefold():
        errors.append("대시보드에 DOMPurify가 포함되지 않음")
    if "DOMPurify.sanitize" not in app:
        errors.append("대시보드 동적 콘텐츠 정화 함수가 적용되지 않음")
    if app.count(".innerHTML =") != 1:
        errors.append("대시보드에 정화 함수를 우회한 innerHTML 할당이 있음")
    for package in ("dompurify@", "marked@", "chart.js@"):
        if package not in index:
            errors.append(f"대시보드 외부 라이브러리 버전 미고정: {package[:-1]}")
    if index.count('integrity="sha384-') < 3:
        errors.append("대시보드 외부 라이브러리 무결성 해시 누락")


def validate_niche_radar(project: Path, errors: list[str]) -> None:
    path = project / "data" / "niche-radar.json"
    copied = project / "docs" / "data" / "niche-radar.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if path.read_bytes() != copied.read_bytes():
            errors.append("사이트 틈새 레이더 복사본 불일치")
    except (OSError, ValueError) as error:
        errors.append(f"틈새 레이더 읽기 실패: {error}")
        return

    seen_codes = set()
    for company in payload.get("companies", []):
        code = company.get("code")
        if not code or code in seen_codes:
            errors.append(f"틈새 레이더 종목코드 중복/누락: {code}")
        seen_codes.add(code)
        cap = company.get("cap")
        if not isinstance(cap, int) or not 0 < cap <= 15000:
            errors.append(f"틈새 레이더 시총 범위 오류: {code} → {cap}")
        if company.get("riskMentions", 0) and not company.get(
            "catalystMentions", 0
        ):
            errors.append(f"순수 악재 종목이 틈새 후보에 포함됨: {code}")
        if not company.get("samples"):
            errors.append(f"틈새 레이더 근거 헤드라인 없음: {code}")

    corpus_path = project / "data" / "corpus.jsonl"
    seen_articles = set()
    try:
        with corpus_path.open(encoding="utf-8") as file:
            for number, line in enumerate(file, start=1):
                row = json.loads(line)
                key = (row.get("date"), (row.get("title") or "").casefold())
                if key in seen_articles:
                    errors.append(f"코퍼스 중복 기사: {number}행")
                seen_articles.add(key)
    except (OSError, ValueError) as error:
        errors.append(f"틈새 코퍼스 읽기 실패: {error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=".")
    parser.add_argument("--date", required=True)
    parser.add_argument("--session", required=True, choices=("AM", "PM"))
    args = parser.parse_args()

    project = Path(args.project).resolve()
    errors: list[str] = []
    validate_json_files(project, errors)
    validate_briefing(project, args.date, args.session, errors)
    validate_article_archive(project, errors)
    validate_dashboard_security(project, errors)
    validate_niche_radar(project, errors)

    if errors:
        print(f"[validate] 배포 차단 · 오류 {len(errors)}건")
        for error in errors[:50]:
            print(f"  - {error}")
        if len(errors) > 50:
            print(f"  - 나머지 {len(errors) - 50}건 생략")
        return 1

    print("[validate] JSON·브리핑·기사매칭·틈새레이더·대시보드 보안 검사 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
