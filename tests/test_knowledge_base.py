import unittest
from pathlib import Path

from seo_planner.fol import Atom, KnowledgeBase, Var, load_program, parse_program
from seo_planner.planner import RULES_FILE

FACTS = Path(__file__).resolve().parent.parent / "knowledge_base" / "facts_sample.fol"
K = Var("K")


class TestParserAndEngine(unittest.TestCase):
    def test_parse_rule_and_fact(self):
        facts, rules = parse_program("""
            % comment
            Ranking('a b', 12).        # another comment
            Bad(K) :- Ranking(K, P), P > 10, not Good(K).
        """)
        self.assertEqual(facts, [Atom("Ranking", ("a b", 12))])
        self.assertEqual(rules[0].to_fol(), "∀K,P (Ranking(K, P) ∧ P > 10 ∧ ¬Good(K) → Bad(K))")

    def test_arithmetic(self):
        facts, rules = parse_program("R(a, 14). Prev(a, 5). Drop(K, D) :- R(K, P), Prev(K, Q), D is P - Q.")
        kb = KnowledgeBase(rules)
        self.assertEqual(kb.query("Drop(a, D)", facts), [{Var("D"): 9}])

    def test_recursion(self):
        _, rules = parse_program("Path(X, Y) :- Edge(X, Y). Path(X, Z) :- Edge(X, Y), Path(Y, Z).")
        facts, _ = parse_program("Edge(a, b). Edge(b, c). Edge(c, d).")
        kb = KnowledgeBase(rules)
        self.assertEqual(len(kb.query("Path(a, X)", facts)), 3)

    def test_unstratifiable_rejected(self):
        _, rules = parse_program("P(X) :- Q(X), not P(X).")
        with self.assertRaises(ValueError):
            KnowledgeBase(rules)

    def test_negation_uses_lower_stratum(self):
        facts, rules = parse_program("T(a). T(b). Bad(a). Good(X) :- T(X), not Bad(X).")
        self.assertEqual(KnowledgeBase(rules).query("Good(X)", facts), [{Var("X"): "b"}])


class TestSEOKnowledgeBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        facts, rules = load_program(RULES_FILE, FACTS)
        cls.kb = KnowledgeBase(rules)
        cls.store = cls.kb.closure(facts)

    def ask(self, q):
        return sorted(a[K] for a in self.kb.query(q, self.store))

    def test_dropped(self):
        self.assertEqual(self.ask("Dropped(K)"), ["trail running shoes", "womens running shoes"])

    def test_healthy(self):
        self.assertEqual(self.ask("Healthy(K)"), ["kids running shoes", "running socks"])

    def test_not_ranking(self):
        self.assertEqual(self.ask("NotRanking(K)"), ["cheap running shoes"])

    def test_first_page_but_losing(self):
        # Non-trivial: on page one, and at least one competitor ranks higher.
        self.assertEqual(self.ask("FirstPage(K), LosingToCompetitor(K)"),
                         ["waterproof sneakers", "womens running shoes"])

    def test_needs_work_without_competition(self):
        self.assertEqual(self.ask("NeedsOptimization(K), not LosingToCompetitor(K)"),
                         ["marathon shoes", "running shoes sale"])

    def test_outranked_by_all(self):
        self.assertEqual(self.ask("OutrankedByAll(K)"),
                         ["best running shoes", "cheap running shoes", "sneaker cleaning kit", "trail running shoes",
                          "womens running shoes"])

    def test_keyword_groups(self):
        self.assertEqual(self.ask("InGroup(K, 'Deals')"), ["cheap running shoes", "running shoes sale"])
        self.assertEqual(self.ask("InGroup(K, 'Accessories'), NeedsOptimization(K)"), ["sneaker cleaning kit"])

    def test_priority_is_unique(self):
        for k in self.ask("NeedsOptimization(K)"):
            self.assertEqual(len(self.kb.query(f"Priority('{k}', P)", self.store)), 1, k)


if __name__ == "__main__":
    unittest.main()
