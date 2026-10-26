"""Local web interface: python -m seo_planner.web  ->  http://127.0.0.1:8765

The server listens on 127.0.0.1 only. The AWR API key typed into the page is kept in this
process's memory and is never written to disk. Every API call from the page must carry a
per-run session secret, which is embedded in the page when it is served, so other websites
open in the same browser cannot drive this server.
"""
from __future__ import annotations

import argparse
import json
import secrets
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import awr
from .fol import Atom, KnowledgeBase, Var, explain, fmt, load_program, parse_body, substitute
from .planner import RULES_FILE, SEOPlanningProblem, plan

ROOT = Path(__file__).resolve().parent.parent
INDEX = Path(__file__).resolve().parent / "static" / "index.html"
SAMPLE_CSV = ROOT / "data" / "sample_awr_export.csv"
SESSION_SECRET = secrets.token_urlsafe(24)
MAX_NODES = 30_000


class Session:
    """State of the single local user."""

    def __init__(self):
        self.lock = threading.Lock()
        self.client: awr.AWRClient | None = None
        self.projects: list[dict] = []
        self.rows: list[dict] = []
        self.source = ""
        self.group_source = ""
        self.facts: list[Atom] = []
        self.info: dict = {}

    def require_client(self) -> awr.AWRClient:
        if self.client is None:
            raise UserError("Connect with your AWR API key first.")
        return self.client


SESSION = Session()


class UserError(Exception):
    pass


# ---------------------------------------------------------------------- API handlers

def api_connect(body):
    token = (body.get("token") or "").strip()
    if not token:
        raise UserError("Paste your AWR API key.")
    client = awr.AWRClient(token)
    projects = client.projects()       # also validates the key (401 -> AWRError)
    norm = []
    for p in projects:
        if isinstance(p, dict):
            name = p.get("name") or p.get("projectName") or p.get("title") or str(p.get("id"))
            norm.append({"name": name, "id": p.get("id") or p.get("projectId")})
        else:
            norm.append({"name": str(p), "id": None})
    with SESSION.lock:
        SESSION.client, SESSION.projects = client, norm
    return {"projects": sorted(norm, key=lambda p: p["name"].lower())}


def api_disconnect(body):
    with SESSION.lock:
        SESSION.client, SESSION.projects = None, []
    return {"ok": True}


def api_dates(body):
    client = SESSION.require_client()
    dates = client.dates(body["project"])
    if not dates:
        raise UserError("AWR returned no ranking dates for this project.")
    return {"dates": sorted(dates, reverse=True)}


def api_load(body):
    """Export rankings for [previous, current] and remember the rows."""
    client = SESSION.require_client()
    project, current, previous = body["project"], body["current"], body.get("previous") or None
    start = previous or current
    if start > current:
        raise UserError("The comparison date must be before the ranking update date.")
    rows = client.export_rankings(project, start, current)
    if not rows:
        raise UserError("The export contained no ranking rows for these dates.")
    summary = awr.summarize_rows(rows)
    group_source = "keyword group column in the ranking export" if summary["groups"] else ""
    if not summary["groups"]:
        pid = next((p["id"] for p in SESSION.projects if p["name"] == project), None)
        try:
            mapping = client.keyword_groups(project, pid)
        except awr.AWRError as e:
            mapping, group_source = {}, f"none (keywords endpoint: {e})"
        if mapping:
            rows = awr.attach_groups(rows, mapping)
            summary = awr.summarize_rows(rows)
            group_source = "AWR project keywords endpoint"
        elif not group_source:
            group_source = "none found in this project's data"
    with SESSION.lock:
        SESSION.rows, SESSION.source = rows, f"AWR project “{project}”"
        SESSION.group_source = group_source
    return _load_result(summary, current, previous)


def api_load_sample(body):
    rows = awr.rows_from_csv(SAMPLE_CSV.read_text(encoding="utf-8-sig"))
    summary = awr.summarize_rows(rows)
    with SESSION.lock:
        SESSION.rows, SESSION.source = rows, "sample data (fictional)"
        SESSION.group_source = "keyword group column in the sample export"
    dates = summary["dates"]
    return {**_load_result(summary, dates[-1], dates[-2]), "dates": sorted(dates, reverse=True)}


def _load_result(summary, current, previous):
    return {"source": SESSION.source, "rows": len(SESSION.rows), "keywords": summary["keywords"],
            "websites": summary["websites"], "engines": summary["engines"], "groups": summary["groups"],
            "group_source": SESSION.group_source, "data_dates": summary["dates"],
            "current": current, "previous": previous, "columns": summary["columns"]}


def _build(body):
    if not SESSION.rows:
        raise UserError("Load ranking data first.")
    facts, info = awr.rows_to_facts(SESSION.rows, body["site"], body.get("engine") or None,
                                    body.get("current") or None, body.get("previous") or None)
    with SESSION.lock:
        SESSION.facts, SESSION.info = facts, info
    rule_facts, rules = load_program(RULES_FILE)
    return facts + rule_facts, rules, info


def api_analyze(body):
    """Keyword table: facts + derived classifications, optionally filtered by group."""
    facts, rules, info = _build(body)
    kb = KnowledgeBase(rules)
    store = kb.closure(facts)
    group = body.get("group") or None
    has = lambda pred, *args: Atom(pred, args) in store
    first = lambda q: (kb.query(q, store) or [None])[0]
    keywords = sorted(a[Var("K")] for a in kb.query("Tracked(K)", store))
    table = []
    for k in keywords:
        groups = sorted(a[Var("G")] for a in kb.query(f"InGroup({fmt(k)}, G)", store))
        if group and group not in groups:
            continue
        pos = first(f"Ranking({fmt(k)}, P)")
        prev = first(f"PreviousRanking({fmt(k)}, P)")
        comps = sorted(((a[Var("Q")], a[Var("C")]) for a in kb.query(f"CompetitorRanking({fmt(k)}, C, Q)", store)))
        pr = first(f"Priority({fmt(k)}, P)")
        flags = [f for f in ("Dropped", "Improving", "NotRanking", "StrikingDistance", "LosingToCompetitor",
                             "OutrankedByAll", "InTop3", "Healthy") if has(f, k)]
        table.append({
            "keyword": k, "groups": groups,
            "position": pos[Var("P")] if pos else None,
            "previous": prev[Var("P")] if prev else None,
            "competitor": {"site": comps[0][1], "position": comps[0][0]} if comps else None,
            "needs": has("NeedsOptimization", k), "priority": pr[Var("P")] if pr else None,
            "flags": flags,
        })
    return {"info": info, "keywords": table}


def api_plan(body):
    facts, rules, info = _build(body)
    algo = body.get("algorithm", "astar")
    kw = dict(top=int(body.get("top") or 5), group=body.get("group") or None,
              keywords=body.get("keywords") or None, strict_priority=bool(body.get("strict", True)))
    problem = SEOPlanningProblem(facts, rules, **kw)
    if not problem.scope:
        raise UserError("No keyword in this selection needs optimisation.")
    algos = ["bfs", "ucs", "astar"] if algo == "compare" else [algo]
    runs, shown = [], None
    for a in algos:
        p = SEOPlanningProblem(facts, rules, **kw)
        res = plan(p, a, body.get("heuristic", "domain"), MAX_NODES)
        runs.append({"algorithm": res.algorithm, "found": res.found, "steps": len(res.plan) if res.found else None,
                     "cost": res.cost if res.found else None, "expanded": res.expanded,
                     "generated": res.generated, "seconds": round(res.seconds, 3), "reason": res.reason})
        if a == "astar" or len(algos) == 1:
            shown = (p, res)
    p, res = shown
    steps = []
    if res.found:
        for action, cost in res.plan:
            steps.append({"action": repr(action), "name": action.schema.name, "keyword": action.args[0],
                          "cost": cost, "text": p.describe(action),
                          "because": [repr(l) for l in action.reasons]})
    return {"info": info, "scope": p.scope, "algorithm": res.algorithm, "found": res.found,
            "reason": res.reason, "cost": res.cost, "steps": steps, "runs": runs}


def api_query(body):
    if not SESSION.facts:
        raise UserError("Analyse the data first (choose your website and click Analyse).")
    rule_facts, rules = load_program(RULES_FILE)
    kb = KnowledgeBase(rules)
    proofs = {}
    store = kb.closure(SESSION.facts + rule_facts, proofs)
    try:
        goal = parse_body(body["goal"])
    except SyntaxError as e:
        raise UserError(f"Syntax error: {e}")
    answers = kb.query(goal, store)[:500]
    out = []
    for a in sorted(answers, key=lambda a: [(v.name, fmt(t)) for v, t in a.items()]):
        proof = []
        if body.get("why"):
            for lit in goal:
                if isinstance(lit, Atom) and lit.pred[0].isupper():
                    proof += explain(substitute(lit, a), proofs)
        out.append({"bindings": {v.name: fmt(t) for v, t in a.items()}, "proof": proof})
    return {"answers": out}


def api_rules(body):
    _, rules = load_program(RULES_FILE)
    kb = KnowledgeBase(rules)
    return {"strata": [[{"fol": r.to_fol(), "clause": repr(r)} for r in s] for s in kb.strata]}


def api_facts(body):
    if not SESSION.facts:
        raise UserError("Analyse the data first.")
    info = SESSION.info
    lines = [f"% Facts generated from Advanced Web Ranking data ({SESSION.source})",
             f"% site: {info['site']}   search engine: {info['engine'] or 'n/a'}",
             f"% ranking update: {info['current_date']}   compared with: {info['previous_date'] or 'n/a'}", ""]
    return {"text": "\n".join(lines + [f"{f!r}." for f in SESSION.facts]) + "\n"}


ROUTES = {"connect": api_connect, "disconnect": api_disconnect, "dates": api_dates, "load": api_load,
          "load-sample": api_load_sample, "analyze": api_analyze, "plan": api_plan, "query": api_query,
          "rules": api_rules, "facts": api_facts}


# ---------------------------------------------------------------------- HTTP plumbing

class Handler(BaseHTTPRequestHandler):
    server_version = "SEOPlanner/1.0"

    def log_message(self, fmt_, *args):   # keep the console quiet; never log request bodies
        pass

    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = INDEX.read_text(encoding="utf-8").replace("{{SESSION_SECRET}}", SESSION_SECRET)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        name = self.path.removeprefix("/api/")
        if self.headers.get("X-Session") != SESSION_SECRET:
            return self._send(403, {"error": "invalid session; reload the page"})
        if name not in ROUTES:
            return self._send(404, {"error": "unknown endpoint"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            self._send(200, ROUTES[name](body))
        except (UserError, awr.AWRError, ValueError, KeyError) as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # unexpected: report without leaking the request body
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})


def main(argv=None):
    ap = argparse.ArgumentParser(description="SEO planner web interface")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"SEO planner running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
