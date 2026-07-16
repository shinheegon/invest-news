import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("collect_news", ROOT / "scripts" / "collect-news.py")
collect_news = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(collect_news)

class CompanyTitleMatchTests(unittest.TestCase):
    def test_nc_does_not_match_english_words(self):
        title = "All entry-level jobs require 3-5 years of experience. How can anyone get hired?"
        self.assertFalse(collect_news.company_title_match(title, "NC"))

    def test_nc_matches_verified_alias(self):
        self.assertTrue(collect_news.company_title_match("엔씨소프트, 신작 글로벌 출시", "NC"))
        self.assertTrue(collect_news.company_title_match("NCSoft reports quarterly results", "NC"))

    def test_sk_hynix_is_not_sk_holding(self):
        self.assertFalse(collect_news.company_title_match("SK하이닉스, 나스닥 데뷔", "SK"))
        self.assertTrue(collect_news.company_title_match("SK(주), 실적 개선 전망", "SK"))

    def test_short_ascii_uses_token_boundaries(self):
        self.assertTrue(collect_news.company_title_match("IBM launches new chip", "IBM"))
        self.assertFalse(collect_news.company_title_match("Subprime banking outlook", "IBM"))

    def test_korean_company_name(self):
        self.assertTrue(collect_news.company_title_match("엔비디아와 삼성전자 협력 확대", "삼성전자"))

if __name__ == "__main__":
    unittest.main()
