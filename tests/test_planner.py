import unittest
from pathlib import Path

from seo_planner.planner import load_problem, plan

FACTS = Path(__file__).resolve().parent.parent / "knowledge_base" / "facts_sample.fol"


def replay(problem, steps):
    """Check that every action is applicable when executed and that the goal is reached."""
    state = problem.initial
    for action, _ in steps:
        options = {repr(a): nxt for a, nxt, _ in problem.successors(state)}
        assert repr(action) in options, f"{action!r} not applicable"
        state = options[repr(action)]
    return problem.is_goal(state)


class TestPlanner(unittest.TestCase):
    def test_astar_plan_is_valid(self):
        p = load_problem(FACTS, top=5)
        res = plan(p, "astar")
        self.assertTrue(res.found)
        self.assertTrue(replay(p, res.plan))

    def test_astar_matches_ucs_cost(self):
        costs = {a: plan(load_problem(FACTS, top=3), a).cost for a in ("astar", "ucs")}
        self.assertEqual(costs["astar"], costs["ucs"])

    def test_bfs_has_fewest_steps_ucs_lowest_cost(self):
        kw = dict(keywords=["running shoes sale"])
        b, u = plan(load_problem(FACTS, **kw), "bfs"), plan(load_problem(FACTS, **kw), "ucs")
        self.assertLess(len(b.plan), len(u.plan))
        self.assertLess(u.cost, b.cost)

    def test_heuristic_admissible_along_optimal_plan(self):
        p = load_problem(FACTS, top=4, strict_priority=False)
        res = plan(p, "astar")
        state, remaining = p.initial, res.cost
        for action, cost in res.plan:
            self.assertLessEqual(p.heuristic(state), remaining)
            state = dict((repr(a), n) for a, n, _ in p.successors(state))[repr(action)]
            remaining -= cost
        self.assertEqual(p.heuristic(state), 0)

    def test_strict_priority_order(self):
        p = load_problem(FACTS, top=5)
        audits = [a.args[0] for a, _ in plan(p).plan if a.schema.name == "AuditPage"]
        self.assertEqual(audits, p.scope)

    def test_dropped_keyword_gets_investigated(self):
        steps = [repr(a) for a, _ in plan(load_problem(FACTS, keywords=["trail running shoes"])).plan]
        self.assertIn("InvestigateDrop('trail running shoes')", steps)

    def test_not_ranking_keyword_gets_landing_page(self):
        steps = [repr(a) for a, _ in plan(load_problem(FACTS, keywords=["cheap running shoes"])).plan]
        self.assertIn("CreateLandingPage('cheap running shoes')", steps)
        self.assertLess(steps.index("CreateLandingPage('cheap running shoes')"),
                        steps.index("CloseContentGap('cheap running shoes')"))

    def test_healthy_keyword_rejected(self):
        with self.assertRaises(ValueError):
            load_problem(FACTS, keywords=["kids running shoes"])


if __name__ == "__main__":
    unittest.main()
