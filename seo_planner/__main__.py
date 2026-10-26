"""Command-line interface.

  python -m seo_planner projects                                  list AWR projects
  python -m seo_planner fetch  --project P --site example.com     AWR API -> facts file
  python -m seo_planner import data/export.csv --site example.com AWR CSV export -> facts file
  python -m seo_planner rules                                     print the rules in FOL notation
  python -m seo_planner query  FACTS "BeatenBy(K, C)" [--why]     answer a query
  python -m seo_planner plan   FACTS [--algorithm astar|ucs|bfs] [--compare] [--group G]
  python -m seo_planner.web                                       web interface
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import awr
from .explain import proof_lines, proof_tree, sentence
from .fol import Atom, KnowledgeBase, fmt, load_program, parse_body, substitute
from .planner import RULES_FILE, load_problem, plan

ROOT = Path(__file__).resolve().parent.parent


def cmd_projects(args):
    client = awr.AWRClient(args.token)
    for p in client.projects():
        print(p.get("name", p) if isinstance(p, dict) else p)


def cmd_fetch(args):
    client = awr.AWRClient(args.token)
    start, stop = args.compare_date, args.date
    if not (start and stop):
        dates = client.dates(args.project)
        if not dates:
            sys.exit("AWR returned no ranking dates for this project")
        stop = stop or dates[-1]
        older = [d for d in dates if d < stop]
        start = start or (older[-1] if older else stop)
    args.date, args.compare_date = stop, start
    print(f"Exporting rankings for {args.project!r} from {start} to {stop} ...")
    rows = client.export_rankings(args.project, start, stop)
    _write(rows, args, source=f"API project {args.project}, {start}..{stop}")


def cmd_import(args):
    text = Path(args.csv).read_text(encoding="utf-8-sig")
    _write(awr.rows_from_csv(text), args, source=f"CSV {Path(args.csv).name}")


def _write(rows, args, source):
    facts, info = awr.rows_to_facts(rows, args.site, args.engine, args.date, args.compare_date)
    out = args.out or ROOT / "knowledge_base" / f"facts_{info['site'].replace('.', '_')}.fol"
    awr.write_facts(out, facts, info, source)
    print(json.dumps(info, indent=2))
    if len(info["engines_available"]) > 1:
        print(f"note: data has several search engines; used {info['engine']!r} (choose with --engine)")
    print(f"Wrote {len(facts)} facts to {out}")


def cmd_rules(args):
    _, rules = load_program(args.rules)
    kb = KnowledgeBase(rules)
    for i, stratum in enumerate(kb.strata):
        print(f"--- stratum {i}")
        for r in stratum:
            print("  " + r.to_fol())


def cmd_query(args):
    facts, rules = load_program(args.rules, args.facts)
    kb = KnowledgeBase(rules)
    proofs = {}
    store = kb.closure(facts, proofs)
    body = parse_body(args.goal)
    answers = sorted(kb.query(body, store), key=lambda a: [(v.name, fmt(t)) for v, t in a.items()])
    if not answers:
        print("no")
        return
    for a in answers:
        print(", ".join(f"{v} = {fmt(t)}" for v, t in a.items()) if a else "yes")
        if args.why:
            ground = [substitute(lit, a) for lit in body]
            print("  " + " and ".join(sentence(l) for l in ground if not (isinstance(l, Atom) and l.pred == "is")))
            print("  Why:")
            for lit in ground:
                if isinstance(lit, Atom) and lit.pred[0].isupper():
                    for line in proof_lines(proof_tree(lit, proofs), 1):
                        print(line)
            print()
    print(f"({len(answers)} answer{'s' if len(answers) != 1 else ''})")


def cmd_plan(args):
    kw = dict(top=args.top, keywords=args.keyword, strict_priority=not args.no_strict_priority, group=args.group)
    problem = load_problem(args.facts, args.rules, **kw)
    print(f"Keywords in scope ({len(problem.scope)}), most urgent first:")
    for k in problem.scope:
        print(f"  - {k}")
    algos = ["bfs", "ucs", "astar"] if args.compare else [args.algorithm]
    results = []
    for algo in algos:
        problem = load_problem(args.facts, args.rules, **kw)   # fresh cache for fair timing
        res = plan(problem, algo, args.heuristic, args.max_nodes)
        results.append(res)
        if not args.compare or algo == "astar":
            _print_plan(problem, res)
    if args.compare:
        print("\nAlgorithm comparison")
        print(f"  {'algorithm':<10}{'found':<7}{'steps':>6}{'cost':>6}{'expanded':>10}{'generated':>11}{'time':>9}")
        for r in results:
            steps = len(r.plan) if r.found else "-"
            print(f"  {r.algorithm:<10}{str(r.found):<7}{steps:>6}{r.cost if r.found else '-':>6}"
                  f"{r.expanded:>10}{r.generated:>11}{r.seconds:>8.2f}s  {r.reason}")


def _print_plan(problem, res):
    print(f"\n{res.algorithm}: ", end="")
    if not res.found:
        print(f"no plan ({res.reason}); expanded {res.expanded} nodes")
        return
    print(f"plan with {len(res.plan)} steps, total cost {res.cost}, "
          f"{res.expanded} nodes expanded, {res.seconds:.2f}s\n")
    for i, (action, cost) in enumerate(res.plan, 1):
        print(f"{i:>3}. [{cost}] {problem.describe(action)}")
        print(f"        {action!r}  because {', '.join(map(repr, action.reasons))}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="seo_planner", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rules", default=RULES_FILE, help="rules file (default: knowledge_base/seo_rules.fol)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("projects", help="list AWR projects")
    p.add_argument("--token", help="AWR API token (default: $AWR_API_TOKEN)")
    p.set_defaults(func=cmd_projects)

    for name, func, helptext in (("fetch", cmd_fetch, "export rankings via the AWR API"),
                                 ("import", cmd_import, "convert an AWR ranking CSV export")):
        p = sub.add_parser(name, help=helptext)
        if name == "fetch":
            p.add_argument("--project", required=True, help="AWR project name")
            p.add_argument("--token", help="AWR API token (default: $AWR_API_TOKEN)")
        else:
            p.add_argument("csv")
        p.add_argument("--date", help="ranking update to analyse, YYYY-MM-DD (default: latest)")
        p.add_argument("--compare-date", help="update to compare with, YYYY-MM-DD (default: the one before --date)")
        p.add_argument("--site", required=True, help="your website's domain as tracked in AWR")
        p.add_argument("--engine", help="search engine to use if the data has several (substring match)")
        p.add_argument("--out", help="facts file to write (default: knowledge_base/facts_<site>.fol)")
        p.set_defaults(func=func)

    p = sub.add_parser("rules", help="print the rules in FOL notation, by stratum")
    p.set_defaults(func=cmd_rules)

    p = sub.add_parser("query", help="answer a conjunctive query against the knowledge base")
    p.add_argument("facts")
    p.add_argument("goal", help='e.g. "NeedsOptimization(K), not LosingToCompetitor(K)"')
    p.add_argument("--why", action="store_true", help="print a proof tree for each answer")
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("plan", help="search for an optimisation plan")
    p.add_argument("facts")
    p.add_argument("--algorithm", choices=["astar", "ucs", "bfs"], default="astar")
    p.add_argument("--heuristic", choices=["domain", "goalcount"], default="domain")
    p.add_argument("--top", type=int, default=5, help="plan for the N most urgent keywords (default 5)")
    p.add_argument("--group", help="only plan keywords in this AWR keyword group")
    p.add_argument("--keyword", action="append", help="plan for this keyword (repeatable; overrides --top)")
    p.add_argument("--no-strict-priority", action="store_true",
                   help="allow work on keywords in any order (larger search space)")
    p.add_argument("--compare", action="store_true", help="run BFS, UCS and A* and compare")
    p.add_argument("--max-nodes", type=int, default=200_000)
    p.set_defaults(func=cmd_plan)

    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # ∀ ∧ → ¬ on Windows consoles
    try:
        args.func(args)
    except awr.AWRError as e:
        sys.exit(f"AWR error: {e}")


if __name__ == "__main__":
    main()
