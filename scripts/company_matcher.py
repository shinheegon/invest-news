#!/usr/bin/env python3
"""회사명/종목 별칭을 기사 제목에 안전하게 매칭하는 공용 유틸리티."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Iterable


INDEX_FILES = ("discovery-index.json", "company-index.json", "leading-index.json")
MANUAL_ALIASES = {
    # 짧은 영문명은 일반 단어 안에 섞이기 쉬우므로 종목코드 기준으로 명시한다.
    "036570": ("엔씨소프트", "NC소프트", "NCSOFT", "NC"),
}
KOREAN_PARTICLES = tuple(
    sorted(
        (
            "으로부터",
            "에서부터",
            "에게서",
            "으로는",
            "으로도",
            "으로",
            "에서",
            "에게",
            "부터",
            "까지",
            "처럼",
            "보다",
            "향",
            "발",
            "측",
            "와",
            "과",
            "은",
            "는",
            "이",
            "가",
            "의",
            "을",
            "를",
            "에",
            "도",
            "만",
            "로",
        ),
        key=len,
        reverse=True,
    )
)
FINAL_TICKER = re.compile(r"\(([^()]+)\)\s*$")


@dataclass(frozen=True)
class CompanyEntity:
    name: str
    ticker: str
    aliases: tuple[str, ...]


def split_company_name(display_name: str) -> tuple[str, str]:
    """'엔씨소프트(036570)' -> ('엔씨소프트', '036570')."""
    value = (display_name or "").strip()
    match = FINAL_TICKER.search(value)
    ticker = match.group(1).strip().upper() if match else ""
    base = value[: match.start()].strip() if match else value
    return base, ticker


def _canonical_score(display_name: str) -> tuple[int, int, str]:
    base, _ = split_company_name(display_name)
    hangul = sum("가" <= ch <= "힣" for ch in base)
    compact_len = sum(ch.isalnum() for ch in base)
    return (hangul, compact_len, base)


def load_company_entities(data_dir: str) -> list[CompanyEntity]:
    """여러 인덱스의 같은 티커 별칭을 하나의 대표 회사로 합친다."""
    groups: dict[str, set[str]] = {}
    for filename in INDEX_FILES:
        path = os.path.join(data_dir, filename)
        try:
            with open(path, encoding="utf-8") as file:
                companies = json.load(file).get("companies", {})
        except (OSError, ValueError, TypeError):
            continue
        for display_name in companies:
            base, ticker = split_company_name(display_name)
            if len(base) < 2:
                continue
            # 생성 데이터에는 드물게 잘못된 종목코드가 섞여 있다. 따라서 모든 회사를
            # 티커만으로 합치지 않고, 사람이 확인한 별칭 그룹만 티커 기준으로 병합한다.
            group_key = (
                f"verified-ticker:{ticker}"
                if ticker in MANUAL_ALIASES
                else f"display:{display_name.casefold()}"
            )
            groups.setdefault(group_key, set()).add(display_name)

    entities: list[CompanyEntity] = []
    for names in groups.values():
        canonical = max(names, key=_canonical_score)
        _, ticker = split_company_name(canonical)
        aliases = {split_company_name(name)[0] for name in names}
        aliases.update(MANUAL_ALIASES.get(ticker, ()))
        aliases = {alias.strip() for alias in aliases if len(alias.strip()) >= 2}
        entities.append(
            CompanyEntity(
                name=canonical,
                ticker=ticker,
                aliases=tuple(sorted(aliases, key=lambda value: (-len(value), value.casefold()))),
            )
        )
    return sorted(entities, key=lambda entity: entity.name.casefold())


def _is_word_char(char: str) -> bool:
    return bool(char) and (char.isalnum() or char == "_")


def _allows_korean_particle(text: str) -> bool:
    """짧은 종목명 뒤에 붙는 조사만 허용하고 'NC아울렛' 같은 합성어는 막는다."""
    for particle in KOREAN_PARTICLES:
        if not text.startswith(particle):
            continue
        remainder = text[len(particle) :]
        if not remainder or not _is_word_char(remainder[0]):
            return True
    return False


def _token_match(title: str, alias: str) -> bool:
    pattern = re.compile(re.escape(alias), re.IGNORECASE)
    for match in pattern.finditer(title):
        before = title[match.start() - 1] if match.start() else ""
        after = title[match.end() :]
        if _is_word_char(before):
            continue
        if not after:
            return True
        next_char = after[0]
        if not _is_word_char(next_char):
            return True
        if "가" <= next_char <= "힣" and _allows_korean_particle(after):
            return True
    return False


def alias_matches(title: str, alias: str) -> bool:
    """회사명이 독립 토큰이거나 조사·확인된 접미사와 이어질 때만 매칭한다."""
    title = title or ""
    alias = (alias or "").strip()
    if not title or not alias:
        return False
    return _token_match(title, alias)


def entity_matches(title: str, entity: CompanyEntity) -> bool:
    return any(alias_matches(title, alias) for alias in entity.aliases)


def matching_entities(title: str, entities: Iterable[CompanyEntity]) -> list[CompanyEntity]:
    # 같은 이름이 서로 다른 티커에 붙은 생성 오류는 어느 쪽에도 자동 귀속하지 않는다.
    # 서로 다른 회사명이 한 기사에 함께 나온 경우는 각각 정상적으로 보존한다.
    matched: list[tuple[CompanyEntity, tuple[str, ...]]] = []
    alias_owners: dict[str, set[str]] = {}
    for entity in entities:
        aliases = tuple(alias for alias in entity.aliases if alias_matches(title, alias))
        if not aliases:
            continue
        matched.append((entity, aliases))
        for alias in aliases:
            alias_owners.setdefault(alias.casefold(), set()).add(entity.name)

    return [
        entity
        for entity, aliases in matched
        if any(len(alias_owners[alias.casefold()]) == 1 for alias in aliases)
    ]
