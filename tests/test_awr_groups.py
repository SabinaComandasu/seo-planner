"""Group download against a mock AWR server.

The real response bodies of the market-share endpoints are not documented; the mock uses a
plausible shape. If AWR's actual shape differs, the raw responses saved in data/raw/ show it.
"""
import json
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from seo_planner.awr import AWRClient, rows_to_facts
from seo_planner.fol import Atom

RANKS = {  # (domain, date) -> rows for group 5 ("Deals")
    ("shoeshop.example", "2026-10-19"): [{"keyword": "running shoes sale", "position": 33, "url": "https://shoeshop.example/sale"}],
    ("shoeshop.example", "2026-10-12"): [{"keyword": "running shoes sale", "position": 35, "url": "https://shoeshop.example/sale"},
                                         {"keyword": "cheap running shoes", "position": 18, "url": "https://shoeshop.example/cheap"}],
    ("runfast.example", "2026-10-19"): [{"keyword": "cheap running shoes", "position": 12, "url": "https://runfast.example/c"}],
    ("runfast.example", "2026-10-12"): [{"keyword": "cheap running shoes", "position": 13, "url": "https://runfast.example/c"}],
}


class MockAWR(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        MockAWR.calls.append((url.path, q))
        if url.path == "/marketshare/projects":
            body = {"projects": [{"id": 2, "name": "Shoe Shop"}]}
        elif url.path == "/marketshare/projects/2/keyword-groups":
            body = {"keywordGroups": [{"id": 5, "name": "Deals"}, {"id": 6, "name": "Sneakers"}]}
        elif url.path == "/marketshare/projects/2/search-engines":
            body = {"searchEngines": [{"id": 1, "name": "Google", "location": "United States", "device": "desktop"}]}
        elif url.path == "/marketshare/projects/2/websites":
            body = {"websites": [{"name": "shoeshop.example"}, {"name": "runfast.example"}]}
        elif url.path == "/marketshare/projects/2/domain-keywords":
            assert q["keywordGroupId"] == "5" and q["searchEngineId"] == "1"
            body = {"keywords": RANKS.get((q["domain"], q["date"]), [])}
        else:
            self.send_response(404); self.end_headers(); return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class TestGroupDownload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockAWR)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.client = AWRClient("test-token", base_url=f"http://127.0.0.1:{cls.server.server_port}", save_raw=False)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_options(self):
        pid = self.client.ms_project_id("shoe shop")
        self.assertEqual(pid, 2)
        self.assertEqual(self.client.ms_keyword_groups(pid), [{"id": 5, "name": "Deals"}, {"id": 6, "name": "Sneakers"}])
        self.assertEqual(self.client.ms_search_engines(pid), [{"id": 1, "name": "Google (United States, desktop)"}])

    def test_group_rows_to_facts(self):
        MockAWR.calls.clear()
        rows = self.client.export_group_rankings(2, {"id": 5, "name": "Deals"}, ["2026-10-19", "2026-10-12"],
                                                 {"id": 1, "name": "Google"})
        # only the group's keywords were requested: 2 websites x 2 dates, no full export
        paths = [p for p, _ in MockAWR.calls]
        self.assertEqual(paths.count("/marketshare/projects/2/domain-keywords"), 4)
        self.assertNotIn("export-rankings", " ".join(paths))
        facts, info = rows_to_facts(rows, "shoeshop.example", current="2026-10-19", previous="2026-10-12")
        self.assertIn(Atom("Ranking", ("running shoes sale", 33)), facts)
        self.assertIn(Atom("Ranking", ("cheap running shoes", 101)), facts)          # lost its ranking
        self.assertIn(Atom("PreviousRanking", ("cheap running shoes", 18)), facts)
        self.assertIn(Atom("CompetitorRanking", ("cheap running shoes", "runfast.example", 12)), facts)
        self.assertIn(Atom("InGroup", ("running shoes sale", "Deals")), facts)


if __name__ == "__main__":
    unittest.main()
