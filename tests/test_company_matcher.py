#!/usr/bin/env python3

import json
import os
import tempfile
import unittest

from scripts.company_matcher import (
    CompanyEntity,
    alias_matches,
    entity_matches,
    load_company_entities,
    matching_entities,
)


class AliasMatchingTests(unittest.TestCase):
    def setUp(self):
        self.nc = CompanyEntity(
            name="엔씨소프트(036570)",
            ticker="036570",
            aliases=("엔씨소프트", "NC소프트", "NCSOFT", "NC"),
        )

    def test_nc_matches_real_company_headlines(self):
        self.assertTrue(entity_matches("[클릭 e종목] 신작 모멘텀 풍부한 'NC'", self.nc))
        self.assertTrue(entity_matches("엔씨소프트, 신작 출시 일정 공개", self.nc))
        self.assertTrue(entity_matches("NCSOFT shares rise after earnings", self.nc))
        self.assertTrue(entity_matches("NC는 신작 흥행을 기대한다", self.nc))

    def test_nc_rejects_unrelated_words_and_brands(self):
        unrelated = (
            "All entry-level jobs require 3-5 years of experience",
            "Alphabet tests Wall Street's patience",
            "Super Micro rises after SpaceX announcement",
            "China posts slowest growth as investment slumps",
            "대구 NC아울렛 엑스코점 철수",
            "NC다이노스, 주말 경기 승리",
            "6월 청년 취업자 감소",
        )
        for title in unrelated:
            with self.subTest(title=title):
                self.assertFalse(entity_matches(title, self.nc))

    def test_short_group_name_does_not_swallow_subsidiaries(self):
        self.assertTrue(alias_matches("한화, 2분기 실적 발표", "한화"))
        self.assertTrue(alias_matches("한화는 지주사 할인을 줄였다", "한화"))
        self.assertFalse(alias_matches("한화오션, 캐나다 잠수함 수주", "한화"))
        self.assertFalse(alias_matches("SK하이닉스, HBM 증설", "SK"))
        self.assertTrue(alias_matches("SK, 지주사 가치 재평가", "SK"))

    def test_full_korean_name_does_not_swallow_longer_company_name(self):
        self.assertTrue(alias_matches("씨메스, 로봇 수주 확대", "씨메스"))
        self.assertTrue(alias_matches("SK하이닉스향 단독 공급", "SK하이닉스"))
        self.assertFalse(alias_matches("씨메스로보틱스, 신규 상장", "씨메스"))

    def test_ascii_ticker_is_a_token(self):
        self.assertTrue(alias_matches("AMD’s rivalry with Nvidia intensifies", "AMD"))
        self.assertFalse(alias_matches("Demand for chips is increasing", "AMD"))

    def test_ambiguous_same_name_with_different_tickers_is_not_assigned(self):
        entities = (
            CompanyEntity("에어레인(163280)", "163280", ("에어레인",)),
            CompanyEntity("에어레인(316140)", "316140", ("에어레인",)),
        )
        self.assertEqual(matching_entities("에어레인, 분리막 수주", entities), [])


class EntityLoadingTests(unittest.TestCase):
    def test_same_ticker_aliases_merge_to_descriptive_canonical_name(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "companies": {
                    "NC(036570)": {"count": 1},
                    "엔씨소프트(036570)": {"count": 2},
                }
            }
            with open(
                os.path.join(directory, "company-index.json"), "w", encoding="utf-8"
            ) as file:
                json.dump(payload, file, ensure_ascii=False)

            entities = load_company_entities(directory)

        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].name, "엔씨소프트(036570)")
        self.assertIn("NC", entities[0].aliases)
        self.assertIn("엔씨소프트", entities[0].aliases)

    def test_unverified_same_ticker_companies_stay_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "companies": {
                    "에어레인(316140)": {"count": 1},
                    "우리금융지주(316140)": {"count": 2},
                }
            }
            with open(
                os.path.join(directory, "company-index.json"), "w", encoding="utf-8"
            ) as file:
                json.dump(payload, file, ensure_ascii=False)

            entities = load_company_entities(directory)

        self.assertEqual({entity.name for entity in entities}, set(payload["companies"]))


if __name__ == "__main__":
    unittest.main()
