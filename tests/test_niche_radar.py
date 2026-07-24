#!/usr/bin/env python3

import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "niche_radar", ROOT / "scripts" / "niche-radar.py"
)
niche_radar = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(niche_radar)


class NicheRadarTests(unittest.TestCase):
    def test_corpus_merge_is_idempotent(self):
        today = date(2026, 7, 24)
        row = {
            "date": "2026-07-24",
            "title": "SAMG엔터, 글로벌 협업 확대",
            "source": "테스트",
        }
        merged = niche_radar.merge_corpus([row], [row, row], today)
        self.assertEqual(merged, [row])

    def test_generated_briefing_line_is_not_raw_news(self):
        self.assertFalse(
            niche_radar.is_raw_headline(
                "- 🌱 조기 출몰(선점 후보): 아이씨에이치(368600)"
            )
        )
        self.assertTrue(
            niche_radar.is_raw_headline(
                "아이씨에이치, 갤럭시 Z에 노이즈 차단 소재 공급"
            )
        )

    def test_ambiguous_company_name_requires_company_punctuation(self):
        self.assertFalse(
            niche_radar.company_name_matches(
                "제주도, 청정에너지 등 미래산업 육성", "미래산업", "025560"
            )
        )
        self.assertTrue(
            niche_radar.company_name_matches(
                "미래산업, 아산 신공장 145억에 확보", "미래산업", "025560"
            )
        )
        self.assertFalse(
            niche_radar.company_name_matches(
                "ServiceNow faces a new AI threat", "NEW", "160550"
            )
        )

    def test_longer_company_name_does_not_double_match(self):
        names = [
            ("씨메스", "111111"),
            ("씨메스로보틱스", "222222"),
        ]
        self.assertEqual(
            niche_radar.scan_company("씨메스로보틱스, 신규 수주", names),
            {"222222"},
        )

    def test_pure_negative_repetition_has_no_catalyst(self):
        today = date(2026, 7, 24)
        rows = [
            (
                {"date": "2026-07-23", "title": "코오롱티슈진 임상 실패"},
                {"950160"},
            ),
            (
                {"date": "2026-07-24", "title": "코오롱티슈진 목표가 급락"},
                {"950160"},
            ),
        ]
        self.assertEqual(
            niche_radar.signal_mentions(rows, "950160", today),
            (2, 0),
        )


if __name__ == "__main__":
    unittest.main()
