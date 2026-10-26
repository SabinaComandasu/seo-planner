"""Group download against a mock AWR server.

The mock reproduces the response shapes observed from the live AWR v3 API (2026-10-26):
JSON lists with "id"/"name" (ids as strings, "-1" = all), a null search-engine entry,
URL entries among websites, domain-keywords as CSV with a "best position" column and no URL,
and {"errorCode": 3, ...} when a domain has no data.
"""
import json
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from seo_planner import awr
from seo_planner.awr import AWRClient, rows_to_facts
from seo_planner.fol import Atom

RANKS = {  # (domain, date) -> rows for group 5 ("Deals")
    ("shoeshop.example", "2026-10-19"): [{"keyword": "running shoes sale", "position": 33}],
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
            body = [{"id": "2", "name": "Shoe Shop"}]
        elif url.path == "/marketshare/projects/2/keyword-groups":
            body = [{"id": "-1", "name": "All keywords"}, {"id": "5", "name": "Deals"}, {"id": "6", "name": "Sneakers"}]
        elif url.path == "/marketshare/projects/2/search-engines":
            body = [{"id": "-1", "name": "All search engines"}, {"id": None, "displayName": None},
                    {"id": "1", "name": "Google.com Desktop Universal"}]
        elif url.path == "/marketshare/projects/2/websites":
            body = [{"id": "-1", "name": "All websites"}, {"id": "100", "name": "shoeshop.example/sale/item/"},
                    {"id": "7", "name": "runfast.example"}, {"id": "2", "name": "shoeshop.example"}]
        elif url.path == "/marketshare/projects/2/domain-keywords":
            assert q["keywordGroupId"] == "5" and q["searchEngineId"] == "1"
            assert q["domain"] in ("shoeshop.example", "runfast.example"), q["domain"]
            rows = RANKS.get((q["domain"], q["date"]))
            if not rows:
                body = {"errorCode": 3, "message": "Failed - the domain appears to not exist in the dataset."}
            else:
                lines = ["date,keyword group id,keyword group,search engine id,search engine,domain,keyword,best position"]
                lines += [f"{q['date']},5,Deals,1,Google.com Desktop Universal,{q['domain']},{r['keyword']},{r['position']}"
                          for r in rows]
                return self._reply("\n".join(lines).encode(), "text/csv")
        else:
            self.send_response(404); self.end_headers(); return
        self._reply(json.dumps(body).encode(), "application/json")

    def _reply(self, data, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class TestGroupDownload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls._cache_dir, awr.CACHE_DIR = awr.CACHE_DIR, Path(cls.tmp.name)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockAWR)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.client = AWRClient("test-token", base_url=f"http://127.0.0.1:{cls.server.server_port}", save_raw=False)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        awr.CACHE_DIR = cls._cache_dir
        cls.tmp.cleanup()

    def test_options(self):
        pid = self.client.ms_project_id("shoe shop")
        self.assertEqual(pid, "2")
        self.assertEqual([g["name"] for g in self.client.ms_keyword_groups(pid)], ["All keywords", "Deals", "Sneakers"])
        self.assertEqual([e["id"] for e in self.client.ms_search_engines(pid)], ["1", "-1"])   # null dropped, -1 last
        self.assertEqual(self.client.ms_websites(pid), ["runfast.example", "shoeshop.example"])

    def test_group_rows_to_facts(self):
        MockAWR.calls.clear()
        rows, stats = self.client.export_group_rankings("2", {"id": "5", "name": "Deals"}, ["2026-10-19", "2026-10-12"],
                                                        {"id": "1", "name": "Google"}, refresh=True)
        # only the group's keywords were requested: 2 websites x 2 dates, no full export
        paths = [p for p, _ in MockAWR.calls]
        self.assertEqual(paths.count("/marketshare/projects/2/domain-keywords"), 4)   # 2 domains x 2 dates
        self.assertNotIn("export-rankings", " ".join(paths))
        facts, info = rows_to_facts(rows, "shoeshop.example", current="2026-10-19", previous="2026-10-12")
        self.assertIn(Atom("Ranking", ("running shoes sale", 33)), facts)
        self.assertIn(Atom("Ranking", ("cheap running shoes", 101)), facts)          # lost its ranking
        self.assertIn(Atom("PreviousRanking", ("cheap running shoes", 18)), facts)
        self.assertIn(Atom("CompetitorRanking", ("cheap running shoes", "runfast.example", 12)), facts)
        self.assertIn(Atom("InGroup", ("running shoes sale", "Deals")), facts)
        # loading the same group again is served from the cache: no new domain-keywords calls
        MockAWR.calls.clear()
        again, stats = self.client.export_group_rankings("2", {"id": "5", "name": "Deals"}, ["2026-10-19", "2026-10-12"],
                                                         {"id": "1", "name": "Google"})
        self.assertEqual(sorted(map(str, again)), sorted(map(str, rows)))
        self.assertEqual([p for p, _ in MockAWR.calls if p.endswith("domain-keywords")], [])


if __name__ == "__main__":
    unittest.main()
