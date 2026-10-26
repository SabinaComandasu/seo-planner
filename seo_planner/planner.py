"""SEO optimisation planner: a STRIPS-style action model whose preconditions are FOL queries.

State      = frozenset of ground fluent atoms (what has been done so far).
Knowledge  = closure(static AWR facts ∪ state) under the rules in seo_rules.fol.
Action     = schema with parameters, a precondition (conjunction of literals, may use NAF),
             add/delete effects and a cost. An action is applicable in a state for every
             substitution θ such that  KB ∪ state ⊨ precondition·θ  (found by unification).
Goal       = ∀K ( InScope(K) → Rechecked(K) )

Note: effects model *work being done* (e.g. ContentImproved), never ranking changes.
Whether rankings actually improve is measured by the next AWR update, which is why every
plan ends by re-checking rankings.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .fol import Atom, FactStore, KnowledgeBase, Not, Rule, Var, fmt, load_program, parse_body, parse_atom, \
    solve, substitute
from .search import ALGORITHMS, SearchResult

RULES_FILE = Path(__file__).resolve().parent.parent / "knowledge_base" / "seo_rules.fol"

FLUENTS = {"Audited", "DropInvestigated", "CompetitorsAnalyzed", "OnPageOptimized", "ContentImproved",
           "HasLandingPage", "InternalLinksAdded", "Rechecked"}


@dataclass(frozen=True)
class ActionSchema:
    name: str
    params: tuple        # of Var
    pre: tuple           # of Literal
    add: tuple           # of Atom
    delete: tuple        # of Atom
    cost: int
    text: str            # human-readable template, {K} is replaced by the keyword

    @staticmethod
    def make(name, params, pre, add, cost, text, delete=""):
        return ActionSchema(name, tuple(Var(p) for p in params), parse_body(pre),
                            tuple(parse_atom(a) for a in add.split(";") if a.strip()),
                            tuple(parse_atom(a) for a in delete.split(";") if a.strip()), cost, text)


@dataclass(frozen=True)
class GroundAction:
    schema: ActionSchema
    args: tuple
    reasons: tuple       # ground positive preconditions that justified the action

    def __repr__(self):
        return f"{self.schema.name}({', '.join(fmt(a) for a in self.args)})"


def default_actions(strict_priority: bool = True) -> list[ActionSchema]:
    gate = ", not Blocked(K)" if strict_priority else ""
    A = ActionSchema.make
    return [
        A("AuditPage", ["K"], f"InScope(K), not Audited(K){gate}", "Audited(K)", 1,
          "Audit the ranking page and SERP for {K}"),
        A("InvestigateDrop", ["K"], "Audited(K), Dropped(K), not DropInvestigated(K)", "DropInvestigated(K)", 2,
          "Investigate why {K} dropped (indexing, cannibalisation, SERP changes)"),
        A("AnalyzeCompetitors", ["K"], "Audited(K), LosingToCompetitor(K), not CompetitorsAnalyzed(K)",
          "CompetitorsAnalyzed(K)", 2, "Analyse competitor pages outranking us for {K}"),
        A("OptimizeOnPage", ["K"], "Audited(K), StrikingDistance(K), not OnPageOptimized(K)",
          "OnPageOptimized(K)", 2, "Optimise title, meta description and headings for {K}"),
        A("CloseContentGap", ["K"], "CompetitorsAnalyzed(K), RankingPageExists(K), not ContentImproved(K)",
          "ContentImproved(K)", 4, "Add the topics competitors cover that our page misses for {K}"),
        A("RewriteContent", ["K"],
          "Audited(K), RankingPageExists(K), not StrikingDistance(K), not NotRanking(K), not ContentImproved(K)",
          "ContentImproved(K)", 5, "Rewrite and expand the content targeting {K}"),
        A("CreateLandingPage", ["K"], "Audited(K), NotRanking(K), not HasLandingPage(K)", "HasLandingPage(K)", 8,
          "Create a dedicated landing page for {K}"),
        A("PublishSupportingArticle", ["K"],
          "Audited(K), RankingPageExists(K), not ContentImproved(K), not InternalLinksAdded(K)",
          "ContentImproved(K); InternalLinksAdded(K)", 7,
          "Publish a supporting article on {K} that covers missing topics and links to the page"),
        A("AddInternalLinks", ["K"], "Improved(K), not InternalLinksAdded(K)", "InternalLinksAdded(K)", 1,
          "Add internal links pointing to the page for {K}"),
        A("ScheduleRecheck", ["K"], "Addressed(K), not Rechecked(K)", "Rechecked(K)", 1,
          "Schedule an AWR ranking update to measure the effect on {K}"),
    ]


class SEOPlanningProblem:
    def __init__(self, facts: list[Atom], rules: list[Rule], top: int | None = 5,
                 keywords: list[str] | None = None, strict_priority: bool = True, group: str | None = None):
        self.kb = KnowledgeBase(rules)
        self.actions = default_actions(strict_priority)
        self.static = self.kb.closure(facts)

        # Choose the keywords in scope: explicit list, or the top-N by the KB's priority order.
        goal = "NeedsOptimization(K)" + (f", InGroup(K, {fmt(group)})" if group else "")
        candidates = [a[Var("K")] for a in self.kb.query(goal, self.static)]
        if keywords:
            unknown = set(keywords) - set(candidates)
            if unknown:
                raise ValueError(f"not keywords needing optimisation: {sorted(unknown)}")
            candidates = keywords
        else:
            candidates.sort(key=self._priority_key)
            if top is not None:
                candidates = candidates[:top]
        self.scope = candidates

        # Rules that never mention fluents are already applied in `static`; per state we only
        # re-run the rules that (transitively) depend on fluents or InScope.
        dynamic_rules = self._dynamic_rules(rules)
        dynamic_preds = {r.head.pred for r in dynamic_rules}
        self.dyn_kb = KnowledgeBase(dynamic_rules)
        self.base = [f for f in self.static if f.pred not in dynamic_preds] + \
                    [Atom("InScope", (k,)) for k in self.scope]
        self._cache: dict[frozenset, FactStore] = {}
        self.initial = frozenset()

    def _priority_key(self, k):
        pr = self.kb.query(f"Priority({fmt(k)}, P)", self.static)
        return (min(a[Var("P")] for a in pr) if pr else 99, k)

    @staticmethod
    def _dynamic_rules(rules):
        dynamic = set(FLUENTS) | {"InScope"}
        changed = True
        while changed:
            changed = False
            for r in rules:
                preds = {(l.atom if isinstance(l, Not) else l).pred for l in r.body}
                if r.head.pred not in dynamic and preds & dynamic:
                    dynamic.add(r.head.pred)
                    changed = True
        return [r for r in rules if r.head.pred in dynamic]

    # ------------------------------------------------------------------ search interface
    def knowledge(self, state: frozenset) -> FactStore:
        store = self._cache.get(state)
        if store is None:
            store = self.dyn_kb.closure(self.base + list(state))
            self._cache[state] = store
        return store

    def is_goal(self, state) -> bool:
        return all(Atom("Rechecked", (k,)) in state for k in self.scope)

    def applicable(self, state):
        """Ground every action schema by solving its precondition against the KB (unification).
        Sorted so that searches are reproducible regardless of hash ordering."""
        store = self.knowledge(state)
        for schema in self.actions:
            found = {}
            for s in solve(schema.pre, store):
                args = tuple(substitute(p, s) for p in schema.params)
                if args not in found:
                    found[args] = (GroundAction(schema, args, tuple(substitute(l, s) for l in schema.pre)), s)
            for args in sorted(found, key=lambda a: tuple(map(fmt, a))):
                yield found[args]

    def successors(self, state):
        for action, s in self.applicable(state):
            nxt = (state - {substitute(a, s) for a in action.schema.delete}) | \
                  {substitute(a, s) for a in action.schema.add}
            yield action, frozenset(nxt), action.schema.cost

    def heuristic(self, state) -> int:
        """Admissible lower bound: for every open keyword, add the cheapest cost of each
        milestone that the rules make unavoidable and that is not yet reached."""
        kb = self.knowledge(state)
        has = lambda pred, k: Atom(pred, (k,)) in kb
        h = 0
        for k in self.scope:
            if has("Rechecked", k):
                continue
            h += 1                                                  # ScheduleRecheck
            if not has("InternalLinksAdded", k):
                h += 1                                              # AddInternalLinks
            if not has("Audited", k):
                h += 1                                              # AuditPage
            if has("Dropped", k) and not has("DropInvestigated", k):
                h += 2                                              # InvestigateDrop
            if has("NotRanking", k) and not has("HasLandingPage", k):
                h += 8                                              # only way to Improved / a page
            if has("LosingToCompetitor", k):
                if not has("CompetitorsAnalyzed", k):
                    h += 2
                if not has("ContentImproved", k):
                    h += 4                                          # cheapest way to ContentImproved
            elif not has("Improved", k) and not has("NotRanking", k):
                h += 2                                              # min improvement action
        return h

    def goal_count_heuristic(self, state) -> int:
        return sum(1 for k in self.scope if Atom("Rechecked", (k,)) not in state)

    # ------------------------------------------------------------------ explanations
    def describe(self, action: GroundAction) -> str:
        k = action.args[0]
        text = action.schema.text.format(K=f"'{k}'")
        if action.schema.name == "AnalyzeCompetitors":
            rows = self.kb.query(f"Ranking({fmt(k)}, P), BeatenBy({fmt(k)}, C), CompetitorRanking({fmt(k)}, C, Q)",
                                 self.static)
            if rows:
                ours = rows[0][Var("P")]
                comp = ", ".join(f"{r[Var('C')]} #{r[Var('Q')]}" for r in sorted(rows, key=lambda r: r[Var("Q")]))
                text += f" [we are {_pos(ours)}; ahead of us: {comp}]"
        elif action.schema.name == "InvestigateDrop":
            r = self.kb.query(f"PreviousRanking({fmt(k)}, A), Ranking({fmt(k)}, B)", self.static)
            if r:
                text += f" [{_pos(r[0][Var('A')])} -> {_pos(r[0][Var('B')])}]"
        elif action.schema.name == "AuditPage":
            r = self.kb.query(f"Ranking({fmt(k)}, P), Priority({fmt(k)}, Pr)", self.static)
            u = self.kb.query(f"RankingUrl({fmt(k)}, U)", self.static)
            if r:
                text += f" [{_pos(r[0][Var('P')])}, priority {r[0][Var('Pr')]}"
                text += f", page {u[0][Var('U')]}]" if u else ", no ranking page]"
        return text


def _pos(p) -> str:
    return "not ranking" if p > 100 else f"#{p}"


def load_problem(facts_file, rules_file=RULES_FILE, **kw) -> SEOPlanningProblem:
    facts, rules = load_program(rules_file, facts_file)
    return SEOPlanningProblem(facts, rules, **kw)


def plan(problem: SEOPlanningProblem, algorithm: str = "astar", heuristic: str = "domain",
         max_expanded: int = 200_000) -> SearchResult:
    if heuristic == "goalcount":
        problem.heuristic = problem.goal_count_heuristic
    return ALGORITHMS[algorithm](problem, max_expanded=max_expanded)
