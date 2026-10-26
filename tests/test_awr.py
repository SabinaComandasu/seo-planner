import io
import json
import unittest
import zipfile

from seo_planner.awr import NOT_RANKING, AWRError, attach_groups, check_api_error, find_download_link, norm_date, \
    rows_from_payload, rows_to_facts, summarize_rows
from seo_planner.fol import Atom

ROWS = [
    {"Date": "2026-10-12", "Keyword": "shoes", "Website": "www.mine.example", "Position": "5", "URL": "https://mine.example/s"},
    {"Date": "2026-10-19", "Keyword": "shoes", "Website": "mine.example", "Position": "14", "URL": "https://mine.example/s"},
    {"Date": "2026-10-19", "Keyword": "shoes", "Website": "rival.example", "Position": "3", "URL": ""},
    {"Date": "2026-10-19", "Keyword": "socks", "Website": "mine.example", "Position": "-", "URL": ""},
]


class TestPayloads(unittest.TestCase):
    def test_json_rows_nested(self):
        body = json.dumps({"data": {"rankings": [{"keyword": "a", "website": "x", "position": 1}]}}).encode()
        self.assertEqual(rows_from_payload("application/json", body)[0]["keyword"], "a")

    def test_json_link_only(self):
        body = json.dumps({"status": "ok", "details": "https://files.example/export.zip"}).encode()
        self.assertIsNone(rows_from_payload("application/json", body))
        self.assertEqual(find_download_link(body), "https://files.example/export.zip")

    def test_csv(self):
        body = b"Keyword;Website;Position\nshoes;mine.example;4\n"
        self.assertEqual(rows_from_payload("text/csv", body), [{"Keyword": "shoes", "Website": "mine.example", "Position": "4"}])

    def test_zip_of_csv(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("google.csv", "Keyword,Website,Position\nshoes,mine.example,4\n")
        self.assertEqual(len(rows_from_payload("application/zip", buf.getvalue())), 1)


    def test_api_error_in_200_body(self):
        # Observed from the live API with an invalid key: HTTP 200 and this body.
        with self.assertRaisesRegex(AWRError, "invalid API key"):
            check_api_error(b'{"response_code":11,"message":"Failed - invalid token"}')
        check_api_error(b'{"response_code":0,"projects":[]}')     # success passes through


class TestRowsToFacts(unittest.TestCase):
    def setUp(self):
        self.facts, self.info = rows_to_facts(ROWS, "https://www.mine.example/")

    def test_current_and_previous(self):
        self.assertIn(Atom("Ranking", ("shoes", 14)), self.facts)
        self.assertIn(Atom("PreviousRanking", ("shoes", 5)), self.facts)

    def test_competitor(self):
        self.assertIn(Atom("CompetitorRanking", ("shoes", "rival.example", 3)), self.facts)

    def test_not_ranking(self):
        self.assertIn(Atom("Ranking", ("socks", NOT_RANKING)), self.facts)

    def test_url(self):
        self.assertIn(Atom("RankingUrl", ("shoes", "https://mine.example/s")), self.facts)

    def test_choose_dates(self):
        rows = ROWS + [{"Date": "2026-10-05", "Keyword": "shoes", "Website": "mine.example", "Position": "2", "URL": ""}]
        facts, info = rows_to_facts(rows, "mine.example")            # default: latest vs. the update before
        self.assertIn(Atom("PreviousRanking", ("shoes", 5)), facts)
        facts, info = rows_to_facts(rows, "mine.example", current="2026-10-12", previous="2026-10-05")
        self.assertIn(Atom("Ranking", ("shoes", 5)), facts)
        self.assertIn(Atom("PreviousRanking", ("shoes", 2)), facts)
        with self.assertRaises(Exception):
            rows_to_facts(rows, "mine.example", current="2026-01-01")

    def test_groups(self):
        rows = attach_groups(ROWS, {"shoes": {"Shoes", "Sale"}})
        facts, info = rows_to_facts(rows, "mine.example")
        self.assertIn(Atom("InGroup", ("shoes", "Sale")), facts)
        self.assertEqual(info["groups"], ["Sale", "Shoes"])
        self.assertEqual(summarize_rows(rows)["groups"], ["Sale", "Shoes"])

    def test_norm_date(self):
        self.assertEqual(norm_date("2026-10-05T00:00:00"), "2026-10-05")
        self.assertEqual(norm_date("19.10.2026"), "2026-10-19")

    def test_unknown_site(self):
        with self.assertRaises(Exception):
            rows_to_facts(ROWS, "other.example")


if __name__ == "__main__":
    unittest.main()
