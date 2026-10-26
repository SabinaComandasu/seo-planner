import unittest
from pathlib import Path

from seo_planner.explain import proof_tree, sentence
from seo_planner.fol import Atom, KnowledgeBase, Not, load_program, parse_atom, parse_body, parse_program
from seo_planner.planner import RULES_FILE

FACTS = Path(__file__).resolve().parent.parent / "knowledge_base" / "facts_sample.fol"


class TestRuleDescriptions(unittest.TestCase):
    def test_doc_comment_attaches_to_next_rule(self):
        _, rules = parse_program("""
            %% Anything below #10 needs work. It's simple.
            Bad(K) :- Ranking(K, P), P > 10.
            Good(K) :- Ranking(K, P), P <= 10.
        """)
        self.assertEqual(rules[0].doc, "Anything below #10 needs work. It's simple.")
        self.assertEqual(rules[1].doc, "")

    def test_every_rule_in_the_knowledge_base_is_described(self):
        _, rules = load_program(RULES_FILE)
        self.assertEqual([repr(r) for r in rules if not r.doc], [])


class TestSentences(unittest.TestCase):
    def test_facts(self):
        self.assertEqual(sentence(parse_atom("Ranking('banana bread', 1)")), "we rank #1 for “banana bread”")
        self.assertEqual(sentence(parse_atom("Ranking('banana bread', 101)")), "we're not ranking for “banana bread”")
        self.assertEqual(sentence(parse_atom("BeatenBy(shoes, 'rival.com')")), "rival.com ranks above us for “shoes”")

    def test_negation_and_calculation(self):
        self.assertEqual(sentence(Not(parse_atom("Audited(shoes)"))), "“shoes” hasn't been audited yet")
        lits = parse_body("D is 14 - 5, 9 >= 5")
        self.assertEqual([sentence(l) for l in lits], ["D = 14 − 5", "9 ≥ 5"])

    def test_unknown_predicate_falls_back_to_logic(self):
        self.assertEqual(sentence(parse_atom("Foo(a, 1)")), "Foo(a, 1)")


class TestProofTree(unittest.TestCase):
    def test_priority_proof(self):
        facts, rules = load_program(RULES_FILE, FACTS)
        proofs = {}
        KnowledgeBase(rules).closure(facts, proofs)
        tree = proof_tree(Atom("Priority", ("trail running shoes", 1)), proofs)
        self.assertEqual(tree["kind"], "rule")
        self.assertEqual(tree["rule"], "Urgent keywords get priority 1.")
        leaves, stack = [], [tree]
        while stack:
            node = stack.pop()
            stack.extend(node.get("children", []))
            if node["kind"] != "rule":
                leaves.append(node["text"])
        self.assertIn("we rank #14 for “trail running shoes”", leaves)
        self.assertIn("9 ≥ 5", leaves)


if __name__ == "__main__":
    unittest.main()
