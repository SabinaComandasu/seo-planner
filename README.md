# Intelligent SEO Optimization Planner

**Topic 5: Integrating Logic and Search (a simple planner).** The planner takes keyword ranking data from **Advanced Web Ranking (AWR)** and turns it into first-order logic facts. It reasons over those facts with FOL rules, then uses search (A\*, UCS, BFS) to find an ordered, cost-optimal sequence of SEO actions.

```
 AWR API v3 / CSV export ──► facts (FOL) ──► rules (FOL, forward chaining) ──► planner (STRIPS + A*/UCS/BFS) ──► action plan
   awr.py                      facts_*.fol      seo_rules.fol / fol.py            planner.py / search.py
```

The project is written in pure Python 3.10+ with **no external dependencies**. It has its own FOL engine, unification and search code, so every part of the AI is implemented here and can be explained.

## Web interface

```powershell
cd seo-planner
python -m seo_planner.web            # opens http://127.0.0.1:8765 in your browser
```

1. **Connect:** paste your AWR API key and click *Connect*, or click *Use sample data* to work offline. The key is held only in the local server's memory. It is never written to disk and only ever sent to `api.advancedwebranking.com`.
2. **Ranking data:**
   - Choose the project, the **ranking update** date to analyse, and the update to **compare with** (used for drops and improvements).
   - Click *Load rankings*.
   - In the API mode, changing the dates later requires loading again.
3. **Plan settings:** choose your website, the **keyword group**, how many keywords to plan, and the search algorithm. Pick *Compare all three* to run BFS, UCS and A* side by side. You can also tick specific keywords in the table to plan only those.

The interface has four tabs:
- **Keywords:** the classification derived by the rules.
- **Plan:** each step with its cost and a "why is this action allowed?" proof. You can download the plan (.md) and the facts (.fol) from here.
- **Query:** ask FOL queries, optionally with proof trees.
- **Rules:** the rules, grouped by stratum.

`http://127.0.0.1:8765/#demo-plan` loads the sample data and generates a plan in one go, which is handy for a presentation.

**Keyword groups.** In step 2 you pick a keyword group *before* loading, and only that group is downloaded. The AWR `export-rankings` endpoint has no group filter, so for a single group the app uses the Market Share endpoints instead:

| Endpoint | Used for |
|---|---|
| `GET /marketshare/projects` | the numeric project id |
| `GET /marketshare/projects/{id}/keyword-groups` | the group list |
| `GET /marketshare/projects/{id}/search-engines` | the search engine list |
| `GET /marketshare/projects/{id}/websites` | your site and the competitors |
| `GET /marketshare/projects/{id}/domain-keywords?domain=&date=&keywordGroupId=&searchEngineId=` | positions and URLs; one call per website per date |

That's 2 × (number of websites) small calls instead of a full export. Limitation: `domain-keywords` only lists keywords on which a website was found, so a keyword where *none* of the tracked websites rank doesn't appear.

Choosing **All keywords** uses the full `export-rankings` export. In that case, groups are read from its keyword-group column, or from `GET /projects/{id}/keywords`. Either way, groups become `InGroup(K, G)` facts, and the planner's scope query becomes `NeedsOptimization(K), InGroup(K, G)`.

**Errors.** AWR reports some errors as HTTP 200 with a body such as `{"response_code": 11, "message": "Failed - invalid token"}`. The client turns these into readable errors.

## Quick start (command line)

```powershell
cd seo-planner
python -m unittest discover -s tests -t .                                      # 52 tests

# offline, using the bundled sample data (fictional .example domains)
python -m seo_planner import data/sample_awr_export.csv --site shoeshop.example --out knowledge_base/facts_sample.fol
python -m seo_planner rules
python -m seo_planner query knowledge_base/facts_sample.fol "FirstPage(K), BeatenBy(K, C)"
python -m seo_planner plan  knowledge_base/facts_sample.fol --compare
```

### Using your AWR account

You need an API token (AWR: *Settings → API*). Developer API access depends on your AWR plan.

```powershell
$env:AWR_API_TOKEN = "your-token"                      # never commit the token
python -m seo_planner projects                         # list project names
python -m seo_planner fetch --project "My Project" --site mysite.com --date 2026-10-19 --compare-date 2026-10-12
python -m seo_planner plan knowledge_base/facts_mysite_com.fol
```

`fetch` calls the documented AWR v3 endpoints (`https://api.advancedwebranking.com/v3`, Bearer auth):

| Endpoint | Used for |
|---|---|
| `GET /projects` | `projects` command |
| `GET /projects/{name}/dates` | the ranking update dates (default: latest vs. the one before) |
| `GET /projects/{name}/export-rankings?startDate=&stopDate=` | the ranking rows |
| `GET /projects/{id}/keywords` | keyword groups, if the export has no group column |

> **First run with real data:** AWR's public reference doesn't document the response body of `export-rankings`. So the client accepts JSON rows, a JSON body containing a download link (polled until ready), a ZIP archive, or CSV. Every raw response is saved in `data/raw/`. If `fetch` reports a missing column, open the raw file and add the real column name to `COLUMN_ALIASES` in `seo_planner/awr.py`. You can also export rankings as CSV from the AWR UI and use `import` instead of `fetch`.

If the project tracks several search engines, the first one is used; choose another with `--engine "google"` (substring match).

## 1. Knowledge representation (FOL)

### Facts generated from AWR

| Predicate | Meaning |
|---|---|
| `Tracked(K)` | keyword K is tracked in the AWR project |
| `Ranking(K, P)` | our position at the latest update (101 = not in the top 100) |
| `PreviousRanking(K, P)` | our position at the start of the compared period |
| `CompetitorRanking(K, C, P)` | best position of competitor website C |
| `RankingUrl(K, U)` | our page that ranks for K |
| `InGroup(K, G)` | keyword K belongs to AWR keyword group G |

### Rules ([`knowledge_base/seo_rules.fol`](knowledge_base/seo_rules.fol))

The rules are Horn clauses with negation-as-failure, written in a Prolog-like syntax. Variables start with an uppercase letter. `python -m seo_planner rules` prints them in standard FOL notation, for example:

```
∀K,P (Ranking(K, P) ∧ P >= 4 ∧ P <= 20 → StrikingDistance(K))
∀D,K,P,P0 (Ranking(K, P) ∧ PreviousRanking(K, P0) ∧ D is P - P0 ∧ D >= 5 → Dropped(K))
∀C,K,P,Q (Ranking(K, P) ∧ CompetitorRanking(K, C, Q) ∧ Q < P → BeatenBy(K, C))
∀K (StrikingDistance(K) ∧ LosingToCompetitor(K) → NeedsOptimization(K))
∀K (NeedsOptimization(K) ∧ ¬Urgent(K) ∧ StrikingDistance(K) → Priority(K, 2))
∀K (Improved(K) ∧ InternalLinksAdded(K) ∧ DropHandled(K) ∧ GapHandled(K) → Addressed(K))
```

Main derived concepts:
- **Classification:** `StrikingDistance`, `NotRanking`, `Dropped`, `Improving`, `BeatenBy`, `LosingToCompetitor`, `OutrankedByAll`, `Healthy`.
- **Decisions:** `NeedsOptimization`, `Urgent`, `Priority(K, 1..3)`, and `HigherPriority`, which gives a total order.
- **Planning-state concepts:** `Improved`, `DropHandled`, `GapHandled`, `Addressed`, `Blocked`.

### Inference engine ([`seo_planner/fol.py`](seo_planner/fol.py))

- **Unification:** Robinson's algorithm with occurs check, supporting function terms (`unify`). There's also a fast path for matching flat atoms against ground facts.
- **Forward chaining:** the engine computes the least model of the facts and rules.
- **Negation-as-failure:** rules are **stratified automatically**, so `not` is only applied to fully computed predicates. A program with recursion through negation is rejected.
- **Built-ins:** `> < >= <= != =` and arithmetic `X is A - B`.
- **Query answering:** conjunctive queries with variables, negation and arithmetic.
- **`--why` proof trees:** show which rule and which facts derived an answer.

## 2. Planning model ([`seo_planner/planner.py`](seo_planner/planner.py))

The planner uses a STRIPS-style model. Preconditions are **FOL queries over the knowledge base**: an action is applicable for every substitution θ such that `KB ∪ state ⊨ pre·θ`. Those substitutions are found by unification, and that's how action schemas get grounded.

- **State:** the set of fluents done so far (`Audited(K)`, `ContentImproved(K)`, …). Everything else is derived by the rules from the AWR facts plus the state.
- **Goal:** `∀K (InScope(K) → Rechecked(K))`. The keywords in scope are the top-N by the KB's `HigherPriority` order (`--top`), or the ones you pass with `--keyword`.

| Action(K) | Precondition | Effect | Cost |
|---|---|---|---|
| AuditPage | `InScope(K) ∧ ¬Audited(K) ∧ ¬Blocked(K)` | `Audited(K)` | 1 |
| InvestigateDrop | `Audited(K) ∧ Dropped(K)` | `DropInvestigated(K)` | 2 |
| AnalyzeCompetitors | `Audited(K) ∧ LosingToCompetitor(K)` | `CompetitorsAnalyzed(K)` | 2 |
| OptimizeOnPage | `Audited(K) ∧ StrikingDistance(K)` | `OnPageOptimized(K)` | 2 |
| CloseContentGap | `CompetitorsAnalyzed(K) ∧ RankingPageExists(K)` | `ContentImproved(K)` | 4 |
| RewriteContent | `Audited(K) ∧ RankingPageExists(K) ∧ ¬StrikingDistance(K) ∧ ¬NotRanking(K)` | `ContentImproved(K)` | 5 |
| CreateLandingPage | `Audited(K) ∧ NotRanking(K)` | `HasLandingPage(K)` | 8 |
| PublishSupportingArticle | `Audited(K) ∧ RankingPageExists(K)` | `ContentImproved(K)`, `InternalLinksAdded(K)` | 7 |
| AddInternalLinks | `Improved(K)` | `InternalLinksAdded(K)` | 1 |
| ScheduleRecheck | `Addressed(K)` | `Rechecked(K)` | 1 |

(Every action also requires that its own effect isn't already true.)

**Strict-priority policy:** the rule `Blocked(K) :- HigherPriority(J, K), InScope(J), not Addressed(J)` means work on a keyword can't start until all more urgent keywords are addressed. Turn it off with `--no-strict-priority` to see a much larger search space.

**Honest modelling:** effects describe *work done*, never ranking gains. No action asserts that a position improves. That can only be observed in the next AWR update, which is why every plan ends with `ScheduleRecheck`. After the update, re-run `fetch` and `plan`: the new facts produce a new plan (a plan → act → observe loop).

## 3. Search ([`seo_planner/search.py`](seo_planner/search.py))

| Algorithm | Optimises | Notes |
|---|---|---|
| BFS | number of actions | goal test on generation; ignores costs |
| UCS | total cost | Dijkstra-style; optimal; no heuristic |
| A\* | total cost | `f = g + h`; ties broken towards deeper nodes |

**Heuristic (A\*).** For each in-scope keyword that isn't yet rechecked, h adds the cheapest cost of every milestone that the rules make unavoidable and that hasn't been reached yet:
- recheck: 1
- internal links: 1
- audit: 1
- a drop investigation if `Dropped`: 2
- a landing page if `NotRanking`: 8
- competitor analysis and content work if `LosingToCompetitor`: 2 + 4
- otherwise, the cheapest improvement: 2

Each milestone can only be achieved by actions that cost at least that much. The one action with two effects, `PublishSupportingArticle`, costs 7, which is at least the sum of the milestones it covers. So **h never overestimates (admissible)** and A\* returns optimal plans. `tests/test_planner.py` checks this along the optimal plan. `--heuristic goalcount` uses a weaker admissible heuristic for comparison.

Results on the sample data (top 3 keywords, no priority policy):

```
  algorithm found   steps  cost  expanded  generated
  BFS       True       14    37     10154      62838
  UCS       True       17    31     10655      64450
  A*        True       17    31        17         97
```

BFS finds the plan with the fewest steps, but it costs more: it uses the expensive `PublishSupportingArticle` shortcut. UCS and A\* find the same optimal plan, and A\* expands about 600× fewer nodes.

## Project layout

```
seo_planner/
  fol.py        terms, unification, parser, stratified forward chaining, queries, proofs
  planner.py    action schemas, planning problem, heuristic, explanations
  search.py     BFS, UCS, A*
  awr.py        AWR API v3 client, payload decoding, rows -> facts
  __main__.py   command-line interface
  web.py        local web interface (stdlib HTTP server) + static/index.html
knowledge_base/
  seo_rules.fol          the rules (domain knowledge)
  facts_sample.fol       facts generated from the sample export
data/sample_awr_export.csv  fictional sample in AWR's long format (date, engine, keyword, website, position, url)
docs/examples.md        complete example queries and plans with real output
tests/                  unification, knowledge base, planner and AWR-parsing tests
```

## Deliverables checklist (Topic 5)

- [x] Problem domain defined: SEO optimisation of tracked keywords, using AWR data
- [x] Rules represented in FOL: `knowledge_base/seo_rules.fol`, printed in FOL notation by `rules`
- [x] Search algorithm finds a valid action sequence: A\*, UCS, BFS; plan validity is tested by replaying it
- [x] Planner code: `seo_planner/`
- [x] Examples of generated plans: `docs/examples.md`
- [x] Documentation: this file
