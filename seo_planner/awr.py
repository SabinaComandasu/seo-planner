"""Advanced Web Ranking (AWR) API v3 client and conversion of ranking rows into FOL facts.

API reference: https://docs.advancedwebranking.com/api-reference  (server .../v3, Bearer token)
  GET /projects                              list projects
  GET /projects/{name}/dates                 dates with ranking data
  GET /projects/{name}/export-rankings       ?startDate=YYYY-MM-DD&stopDate=YYYY-MM-DD

The documentation does not publish the response schema of export-rankings, so the client
accepts every shape we may plausibly get back: JSON rows, a JSON body containing a download
link (an export that is prepared asynchronously), a ZIP archive, or CSV text. Every raw
response is saved under data/raw/ so the mapping can be checked against a real account.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .fol import Atom

BASE_URL = "https://api.advancedwebranking.com/v3"
API_HOST = urllib.parse.urlparse(BASE_URL).hostname
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
NOT_RANKING = 101


class AWRError(RuntimeError):
    pass


class AWRClient:
    def __init__(self, token: str | None = None, base_url: str = BASE_URL, timeout: int = 60,
                 save_raw: bool = True):
        self.token = token or os.environ.get("AWR_API_TOKEN")
        if not self.token:
            raise AWRError("no API token: set the AWR_API_TOKEN environment variable or pass --token")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.save_raw = save_raw

    # ------------------------------------------------------------------ HTTP
    def _request(self, url: str) -> tuple[str, bytes]:
        headers = {"Accept": "application/json, text/csv, application/zip, */*"}
        # Only ever send the token to the AWR API host, never to a third-party download link.
        if urllib.parse.urlparse(url).hostname == API_HOST:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.headers.get("Content-Type", ""), resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()[:500].decode("utf-8", "replace")
            if e.code == 401:
                raise AWRError("401 Unauthorized: check your AWR API token") from None
            raise AWRError(f"HTTP {e.code} for {url}: {body}") from None

    def _get(self, path: str, params: dict | None = None, tag: str = "response") -> tuple[str, bytes]:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        ctype, body = self._request(url)
        self._save(tag, ctype, body)
        check_api_error(body)
        return ctype, body

    def _save(self, tag, ctype, body):
        if not self.save_raw:
            return
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        ext = ".zip" if body[:2] == b"PK" else ".json" if "json" in ctype else ".csv" if "csv" in ctype else ".txt"
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{datetime.now():%Y%m%d-%H%M%S}-{tag}{ext}")
        (RAW_DIR / name).write_bytes(body)

    # ------------------------------------------------------------------ endpoints
    def projects(self) -> list:
        _, body = self._get("/projects", tag="projects")
        data = json.loads(body)
        return data.get("projects", data) if isinstance(data, dict) else data

    def dates(self, project: str) -> list[str]:
        _, body = self._get(f"/projects/{_q(project)}/dates", tag=f"dates-{project}")
        found = set(re.findall(r"\d{4}-\d{2}-\d{2}", body.decode("utf-8", "replace")))
        return sorted(found)

    def export_rankings(self, project: str, start: str | None = None, stop: str | None = None,
                        poll_seconds: int = 10, max_polls: int = 30) -> list[dict]:
        ctype, body = self._get(f"/projects/{_q(project)}/export-rankings",
                                {"startDate": start, "stopDate": stop}, tag=f"export-{project}")
        rows = rows_from_payload(ctype, body)
        if rows is not None:
            return rows
        link = find_download_link(body)
        if not link:
            raise AWRError("could not find ranking rows or a download link in the export response; "
                           f"inspect the raw file in {RAW_DIR}")
        # Exports may be prepared asynchronously: poll the link until the file is ready.
        for attempt in range(max_polls):
            try:
                ctype, body = self._request(link)
            except AWRError as e:
                if "HTTP 404" not in str(e) and "HTTP 202" not in str(e):
                    raise
                body = b""
            if body:
                self._save(f"export-file-{project}", ctype, body)
                rows = rows_from_payload(ctype, body)
                if rows:
                    return rows
            time.sleep(poll_seconds)
        raise AWRError(f"export file at {link} was not ready after {max_polls * poll_seconds}s")

    def keyword_groups(self, project: str, project_id=None) -> dict[str, set[str]]:
        """Best-effort keyword -> groups mapping from GET /projects/{id}/keywords.

        Used only when the ranking export has no group column. The response schema is not
        documented, so we look for objects that have a keyword field and a group-like field.
        """
        ident = str(project_id) if project_id not in (None, "") else project
        _, body = self._get(f"/projects/{_q(ident)}/keywords", tag=f"keywords-{project}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = rows_from_payload("text/csv", body) or []
        mapping: dict[str, set[str]] = defaultdict(set)
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, list):
                stack.extend(cur)
            elif isinstance(cur, dict):
                kw_key = _col(cur.keys(), "keyword")
                grp_keys = [k for k in cur if "group" in _norm(k)]
                if kw_key and isinstance(cur[kw_key], str) and grp_keys:
                    for gk in grp_keys:
                        mapping[cur[kw_key].strip()] |= _group_names(cur[gk])
                stack.extend(v for v in cur.values() if isinstance(v, (list, dict)))
        return {k: v for k, v in mapping.items() if v}


def check_api_error(body: bytes) -> None:
    """AWR reports failures as HTTP 200 with {"response_code": N, "message": "Failed - ..."}."""
    if not body.lstrip().startswith(b"{"):
        return
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    code = data.get("response_code") if isinstance(data, dict) else None
    if code in (None, 0, "0"):
        return
    message = str(data.get("message", ""))
    if set(data) <= {"response_code", "message", "details"} or message.lower().startswith("fail"):
        if code in (11, "11") or "invalid token" in message.lower():
            raise AWRError("invalid API key (AWR: " + message + ")")
        raise AWRError(f"{message or 'request failed'} (AWR response_code {code})")


def _q(name: str) -> str:
    return urllib.parse.quote(name, safe="")


# ---------------------------------------------------------------------- payload decoding

def rows_from_payload(ctype: str, body: bytes) -> list[dict] | None:
    """Return a list of row dicts, or None if the payload holds no rows (e.g. only a link)."""
    if body[:2] == b"PK":
        rows = []
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            for name in zf.namelist():
                data = zf.read(name)
                if name.lower().endswith((".csv", ".json", ".txt", ".tsv")):
                    rows += rows_from_payload("application/json" if name.endswith(".json") else "text/csv", data) or []
        return rows or None
    text = body.decode("utf-8-sig", "replace").strip()
    if not text:
        return None
    if text[0] in "[{":
        try:
            return _rows_from_json(json.loads(text))
        except json.JSONDecodeError:
            pass
    if "\n" in text and ("," in text or ";" in text or "\t" in text):
        return rows_from_csv(text)
    return None


def _rows_from_json(data) -> list[dict] | None:
    """Find the first list of objects that looks like ranking rows anywhere in the JSON."""
    if isinstance(data, list) and data and all(isinstance(r, dict) for r in data):
        if any(_col(r.keys(), "keyword") for r in data[:5]):
            return [_flatten(r) for r in data]
    if isinstance(data, list):
        for item in data:
            rows = _rows_from_json(item)
            if rows:
                return rows
    if isinstance(data, dict):
        for value in data.values():
            rows = _rows_from_json(value)
            if rows:
                return rows
    return None


def _flatten(row: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, dict):
            out.update(_flatten(v, f"{prefix}{k}_"))
        else:
            out[f"{prefix}{k}"] = v
    return out


def rows_from_csv(text: str) -> list[dict]:
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))


def find_download_link(body: bytes) -> str | None:
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    stack = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
        elif isinstance(cur, str) and cur.startswith(("http://", "https://")):
            return cur
    return None


# ---------------------------------------------------------------------- rows -> facts

COLUMN_ALIASES = {
    "keyword": ["keyword", "keyword_name", "kw", "search term", "query"],
    "position": ["position", "rank", "ranking", "pos", "position_value", "organic position"],
    "website": ["website", "website_name", "site", "domain", "website url"],
    "date": ["date", "ranking date", "day"],
    "engine": ["search engine", "search_engine", "searchengine", "engine", "search engine name"],
    "url": ["url", "page", "landing page", "ranking url", "result url"],
    "group": ["keyword group", "keyword groups", "keyword_group", "keywordgroup", "group", "groups", "group name"],
}


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", " ", str(s)).strip().lower()


def _col(columns, field: str) -> str | None:
    cols = {_norm(c): c for c in columns}
    for alias in COLUMN_ALIASES[field]:
        if _norm(alias) in cols:
            return cols[_norm(alias)]
    return None


def _group_names(v) -> set[str]:
    """Group cell -> set of names. Accepts 'A; B', 'A|B', ['A', 'B'] or [{'name': 'A'}]."""
    if v is None:
        return set()
    if isinstance(v, dict):
        v = v.get("name") or v.get("group") or v.get("title") or ""
    if isinstance(v, (list, tuple)):
        return set().union(*(_group_names(x) for x in v)) if v else set()
    return {g.strip() for g in re.split(r"[;|]", str(v)) if g.strip()}


def norm_date(v) -> str:
    """Normalise the date formats AWR may use to YYYY-MM-DD (unknown formats pass through)."""
    s = str(v).strip()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    for f in ("%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d", "%b %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s


def summarize_rows(rows: list[dict]) -> dict:
    """What the UI needs to offer choices: websites, search engines, groups, dates."""
    if not rows:
        return {"websites": [], "engines": [], "groups": [], "dates": [], "columns": [], "keywords": 0}
    columns = list(rows[0].keys())
    col = {f: _col(columns, f) for f in COLUMN_ALIASES}
    sites = defaultdict(set)
    for r in rows:
        if col["website"] and col["keyword"]:
            sites[_domain(r[col["website"]])].add(str(r[col["keyword"]]))
    return {
        "websites": sorted(sites, key=lambda w: (-len(sites[w]), w)),
        "engines": sorted({str(r[col["engine"]]) for r in rows}) if col["engine"] else [],
        "groups": sorted(set().union(*(_group_names(r[col["group"]]) for r in rows))) if col["group"] else [],
        "dates": sorted({norm_date(r[col["date"]]) for r in rows}) if col["date"] else [],
        "columns": columns,
        "keywords": len({str(r[col["keyword"]]) for r in rows}) if col["keyword"] else 0,
    }


def attach_groups(rows: list[dict], mapping: dict[str, set[str]]) -> list[dict]:
    """Add a 'Keyword Group' column to export rows from a keyword -> groups mapping."""
    if not mapping or not rows:
        return rows
    kcol = _col(rows[0].keys(), "keyword")
    return [{**r, "Keyword Group": "; ".join(sorted(mapping.get(str(r[kcol]).strip(), ())))} for r in rows]


def _parse_position(v) -> int:
    try:
        p = int(float(str(v).strip().lstrip(">")))
    except ValueError:
        return NOT_RANKING
    return p if 1 <= p <= 100 else NOT_RANKING


def _domain(s: str) -> str:
    s = str(s).strip().lower()
    host = urllib.parse.urlparse(s if "://" in s else "http://" + s).hostname or s
    return host[4:] if host.startswith("www.") else host


def rows_to_facts(rows: list[dict], site: str, engine: str | None = None,
                  current: str | None = None, previous: str | None = None) -> tuple[list[Atom], dict]:
    """Convert long-format ranking rows (one row per date/keyword/website) into base facts.

    Our site's position on `current` (default: latest date) -> Ranking(K, P); on `previous`
    (default: the update before `current`) -> PreviousRanking(K, P); every other website on `current` ->
    CompetitorRanking(K, C, P) (best position); a group column -> InGroup(K, G).
    Returns (facts, info) where info summarises what was used.
    """
    if not rows:
        raise AWRError("no ranking rows to convert")
    columns = list(rows[0].keys())
    col = {f: _col(columns, f) for f in COLUMN_ALIASES}
    missing = [f for f in ("keyword", "position", "website") if not col[f]]
    if missing:
        raise AWRError(f"cannot find column(s) {missing} among {columns}. "
                       "Add the real column name to COLUMN_ALIASES in seo_planner/awr.py.")

    engines = sorted({str(r[col["engine"]]) for r in rows}) if col["engine"] else []
    if engines and engine is None:
        engine = engines[0]
    if engine is not None and col["engine"]:
        rows = [r for r in rows if engine.lower() in str(r[col["engine"]]).lower()]

    site_d = _domain(site)
    # position[(keyword, website)][date] = best position on that date
    pos: dict = defaultdict(dict)
    urls: dict = {}
    groups: dict = defaultdict(set)
    dates = set()
    for r in rows:
        kw = str(r[col["keyword"]]).strip()
        web = _domain(r[col["website"]])
        d = norm_date(r[col["date"]]) if col["date"] else ""
        dates.add(d)
        p = _parse_position(r[col["position"]])
        key = (kw, web)
        pos[key][d] = min(p, pos[key].get(d, NOT_RANKING))
        if web == site_d and col["url"] and r.get(col["url"]) and p < NOT_RANKING:
            urls.setdefault(kw, {})[d] = str(r[col["url"]]).strip()
        if col["group"]:
            groups[kw] |= _group_names(r[col["group"]])

    websites = {w for _, w in pos}
    if site_d not in websites:
        raise AWRError(f"site {site!r} not found in the data; websites present: {sorted(websites)}")
    latest = norm_date(current) if current else max(dates)
    earliest = norm_date(previous) if previous else max((d for d in dates if d < latest), default=latest)
    if latest not in dates:
        raise AWRError(f"no ranking rows for {latest}; dates in the data: {sorted(dates)}")
    keywords = sorted({k for k, _ in pos})

    facts: list[Atom] = []
    for kw in keywords:
        facts.append(Atom("Tracked", (kw,)))
        ours = pos.get((kw, site_d), {})
        facts.append(Atom("Ranking", (kw, ours.get(latest, NOT_RANKING))))
        if earliest != latest and earliest in ours:
            facts.append(Atom("PreviousRanking", (kw, ours[earliest])))
        if latest in urls.get(kw, {}):
            facts.append(Atom("RankingUrl", (kw, urls[kw][latest])))
        for web in sorted(websites - {site_d}):
            p = pos.get((kw, web), {}).get(latest, NOT_RANKING)
            if p < NOT_RANKING:
                facts.append(Atom("CompetitorRanking", (kw, web, p)))
        for g in sorted(groups.get(kw, ())):
            facts.append(Atom("InGroup", (kw, g)))
    info = {"keywords": len(keywords), "competitors": sorted(websites - {site_d}), "site": site_d,
            "engine": engine, "engines_available": engines, "current_date": latest,
            "previous_date": earliest if earliest != latest and earliest in dates else None,
            "groups": sorted(set().union(*groups.values())) if groups else []}
    return facts, info


def write_facts(path, facts: list[Atom], info: dict, source: str) -> None:
    lines = [
        f"% Facts generated from Advanced Web Ranking data ({source})",
        f"% site: {info['site']}   search engine: {info['engine'] or 'n/a'}",
        f"% current date: {info['current_date'] or 'n/a'}   previous date: {info['previous_date'] or 'n/a'}",
        f"% competitors: {', '.join(info['competitors']) or 'none'}",
        "",
    ]
    lines += [f"{f!r}." for f in facts]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
