"""Unification test cases. Each case states what is being tested and why the result is expected."""
import unittest

from seo_planner.fol import Atom, Compound, Var, parse_atom, substitute, unify

X, Y, Z, K = Var("X"), Var("Y"), Var("Z"), Var("K")


def mgu(a, b):
    """Most general unifier as a fully applied dict, or None."""
    s = unify(a, b)
    return None if s is None else {v: substitute(v, s) for v in s}


class TestUnification(unittest.TestCase):
    def test_identical_ground_atoms(self):
        # Same predicate, same constants: unify with the empty substitution.
        self.assertEqual(mgu(parse_atom("Ranking(shoes, 12)"), parse_atom("Ranking(shoes, 12)")), {})

    def test_variable_binds_to_constant(self):
        # Ranking(K, 12) vs Ranking(shoes, 12): K := shoes.
        self.assertEqual(mgu(parse_atom("Ranking(K, 12)"), parse_atom("Ranking(shoes, 12)")), {K: "shoes"})

    def test_variables_on_both_sides(self):
        # Beats(X, b) vs Beats(a, Y): bindings flow in both directions.
        self.assertEqual(mgu(parse_atom("Beats(X, b)"), parse_atom("Beats(a, Y)")), {X: "a", Y: "b"})

    def test_different_constants_fail(self):
        # 12 and 7 are distinct constants: no substitution makes them equal.
        self.assertIsNone(mgu(parse_atom("Ranking(shoes, 12)"), parse_atom("Ranking(shoes, 7)")))

    def test_different_predicates_fail(self):
        self.assertIsNone(mgu(parse_atom("Ranking(K, P)"), parse_atom("PreviousRanking(K, P)")))

    def test_different_arity_fails(self):
        self.assertIsNone(mgu(parse_atom("CompetitorRanking(K, C)"), parse_atom("CompetitorRanking(K, C, 3)")))

    def test_repeated_variable_consistent(self):
        # P(X, X) vs P(a, a): X := a works for both positions.
        self.assertEqual(mgu(parse_atom("P(X, X)"), parse_atom("P(a, a)")), {X: "a"})

    def test_repeated_variable_inconsistent(self):
        # P(X, X) vs P(a, b): X cannot be both a and b.
        self.assertIsNone(mgu(parse_atom("P(X, X)"), parse_atom("P(a, b)")))

    def test_variable_chain(self):
        # P(X, Y, Y) vs P(Y, Z, a): X=Y, Y=Z, Z=a  ->  everything becomes a.
        self.assertEqual(mgu(parse_atom("P(X, Y, Y)"), parse_atom("P(Y, Z, a)")), {X: "a", Y: "a", Z: "a"})

    def test_function_terms(self):
        # Knows(f(X), Y) vs Knows(f(john), g(Z)): unify inside the function symbol.
        s = mgu(parse_atom("Knows(f(X), Y)"), parse_atom("Knows(f(john), g(Z))"))
        self.assertEqual(s, {X: "john", Y: Compound("g", (Z,))})

    def test_function_symbol_clash(self):
        self.assertIsNone(mgu(parse_atom("Knows(f(X))"), parse_atom("Knows(g(X))")))

    def test_occurs_check(self):
        # X vs f(X) would need an infinite term f(f(f(...))): the occurs check rejects it.
        self.assertIsNone(mgu(parse_atom("P(X)"), parse_atom("P(f(X))")))

    def test_occurs_check_indirect(self):
        # P(X, Y) vs P(Y, f(X)): Y := X, then X vs f(X) fails the occurs check.
        self.assertIsNone(mgu(parse_atom("P(X, Y)"), parse_atom("P(Y, f(X))")))

    def test_string_and_number_constants_differ(self):
        # '12' (text) and 12 (number) are different constants.
        self.assertIsNone(mgu(parse_atom("Ranking(k, '12')"), parse_atom("Ranking(k, 12)")))

    def test_quoted_keyword_constants(self):
        a = parse_atom("Ranking('best running shoes', P)")
        self.assertEqual(mgu(a, Atom("Ranking", ("best running shoes", 12))), {Var("P"): 12})

    def test_unifier_is_most_general(self):
        # P(X) vs P(Y): the mgu binds one variable to the other, not both to a constant.
        s = mgu(parse_atom("P(X)"), parse_atom("P(Y)"))
        self.assertEqual(len(s), 1)
        self.assertIn(s.get(X, s.get(Y)), (X, Y))


if __name__ == "__main__":
    unittest.main()
