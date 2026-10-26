"""First-order logic core: terms, atoms, unification, a parser and a forward-chaining engine.

Conventions (Prolog-like):
  * Variables start with an uppercase letter or "_"            -> K, P0, _x
  * Constants are lowercase identifiers, numbers or quoted text -> nike, 12, 'best running shoes'
  * Rules are Horn clauses with negation-as-failure:            Head :- L1, L2, not L3.
  * Built-in comparison / arithmetic literals:                  P > 10, D is P - P0, J != K

Read as FOL, the rule  H(X) :- B1(X, Y), not B2(Y).  means
  forall X, Y ( B1(X, Y) and not B2(Y) -> H(X) )
where "not" is negation-as-failure under the closed-world assumption.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Iterator, Union


# --------------------------------------------------------------------------- terms

@dataclass(frozen=True)
class Var:
    name: str

    def __repr__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Compound:
    """A function term f(t1, ..., tn), e.g. the arithmetic expression P - P0 is Compound('-', (P, P0))."""
    functor: str
    args: tuple

    def __repr__(self) -> str:
        if self.functor in ARITH_OPS and len(self.args) == 2:
            return f"{fmt(self.args[0])} {self.functor} {fmt(self.args[1])}"
        return f"{self.functor}({', '.join(fmt(a) for a in self.args)})"


@dataclass(frozen=True)
class Atom:
    pred: str
    args: tuple

    def __repr__(self) -> str:
        if self.pred in BUILTINS and len(self.args) == 2:
            return f"{fmt(self.args[0])} {self.pred} {fmt(self.args[1])}"
        return f"{self.pred}({', '.join(fmt(a) for a in self.args)})"

    def is_ground(self) -> bool:
        return not variables(self)


@dataclass(frozen=True)
class Not:
    atom: Atom

    def __repr__(self) -> str:
        return f"not {self.atom!r}"


Term = Union[Var, Compound, str, int, float]
Literal = Union[Atom, Not]
Subst = dict  # Var -> Term

_IDENT = re.compile(r"[a-z][A-Za-z0-9_]*$")


def fmt(t: Term) -> str:
    if isinstance(t, str):
        return t if _IDENT.match(t) else "'" + t.replace("'", "\\'") + "'"
    return repr(t)


def variables(t) -> set:
    if isinstance(t, Var):
        return {t}
    if isinstance(t, (Atom, Compound)):
        return set().union(*(variables(a) for a in t.args)) if t.args else set()
    if isinstance(t, Not):
        return variables(t.atom)
    return set()


# --------------------------------------------------------------------------- unification

def walk(t: Term, s: Subst) -> Term:
    while isinstance(t, Var) and t in s:
        t = s[t]
    return t


def occurs(v: Var, t: Term, s: Subst) -> bool:
    t = walk(t, s)
    if t == v:
        return True
    if isinstance(t, (Atom, Compound)):
        return any(occurs(v, a, s) for a in t.args)
    return False


def unify(x, y, s: Subst | None = None) -> Subst | None:
    """Robinson unification with occurs check. Returns the extended substitution or None.

    The substitution is kept in triangular form (bindings may point at other variables);
    use `substitute` to fully apply it.
    """
    if s is None:
        s = {}
    x, y = walk(x, s), walk(y, s)
    if isinstance(x, Var) and isinstance(y, Var) and x == y:
        return s
    if isinstance(x, Var):
        return None if occurs(x, y, s) else {**s, x: y}
    if isinstance(y, Var):
        return None if occurs(y, x, s) else {**s, y: x}
    if isinstance(x, (Atom, Compound)) or isinstance(y, (Atom, Compound)):
        if type(x) is not type(y):
            return None
        name_x = x.pred if isinstance(x, Atom) else x.functor
        name_y = y.pred if isinstance(y, Atom) else y.functor
        if name_x != name_y or len(x.args) != len(y.args):
            return None
        for a, b in zip(x.args, y.args):
            s = unify(a, b, s)
            if s is None:
                return None
        return s
    # Two constants. type check keeps 'a' != 1 and avoids True == 1 surprises.
    if type(x) in (int, float) and type(y) in (int, float):
        return s if x == y else None
    return s if type(x) is type(y) and x == y else None


def substitute(t, s: Subst):
    t = walk(t, s)
    if isinstance(t, Atom):
        return Atom(t.pred, tuple(substitute(a, s) for a in t.args))
    if isinstance(t, Compound):
        return Compound(t.functor, tuple(substitute(a, s) for a in t.args))
    if isinstance(t, Not):
        return Not(substitute(t.atom, s))
    return t


# --------------------------------------------------------------------------- built-ins

ARITH_OPS = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b}


def evaluate(t: Term, s: Subst):
    t = walk(t, s)
    if isinstance(t, Compound) and t.functor in ARITH_OPS:
        return ARITH_OPS[t.functor](evaluate(t.args[0], s), evaluate(t.args[1], s))
    if isinstance(t, Var):
        raise ValueError(f"unbound variable {t} in arithmetic/comparison")
    return t


def _compare(op):
    def check(args, s):
        a, b = evaluate(args[0], s), evaluate(args[1], s)
        try:
            ok = op(a, b)
        except TypeError:  # e.g. 'abc' < 3
            ok = False
        if ok:
            yield s
    return check


def _is(args, s):
    out = unify(args[0], evaluate(args[1], s), s)
    if out is not None:
        yield out


def _eq(args, s):
    out = unify(args[0], args[1], s)
    if out is not None:
        yield out


BUILTINS = {
    ">": _compare(lambda a, b: a > b),
    "<": _compare(lambda a, b: a < b),
    ">=": _compare(lambda a, b: a >= b),
    "<=": _compare(lambda a, b: a <= b),
    "!=": _compare(lambda a, b: a != b),
    "=": _eq,
    "is": _is,
}


# --------------------------------------------------------------------------- facts and rules

class FactStore:
    """Ground facts indexed by predicate name."""

    def __init__(self, facts: Iterable[Atom] = ()):
        self._by_pred: dict[str, set[Atom]] = {}
        for f in facts:
            self.add(f)

    def add(self, fact: Atom) -> bool:
        bucket = self._by_pred.setdefault(fact.pred, set())
        if fact in bucket:
            return False
        bucket.add(fact)
        return True

    def __contains__(self, fact: Atom) -> bool:
        return fact in self._by_pred.get(fact.pred, ())

    def with_pred(self, pred: str) -> set[Atom]:
        return self._by_pred.get(pred, set())

    def __iter__(self):
        for bucket in self._by_pred.values():
            yield from bucket

    def __len__(self):
        return sum(len(b) for b in self._by_pred.values())


@dataclass(frozen=True)
class Rule:
    head: Atom
    body: tuple  # of Literal

    def __repr__(self) -> str:
        return f"{self.head!r} :- {', '.join(map(repr, self.body))}."

    def to_fol(self) -> str:
        """Render as a universally quantified FOL implication."""
        vs = sorted(variables(self.head).union(*(variables(l) for l in self.body)), key=lambda v: v.name)
        quant = "∀" + ",".join(v.name for v in vs) + " " if vs else ""
        parts = [("¬" + repr(l.atom)) if isinstance(l, Not) else repr(l) for l in self.body]
        return f"{quant}({' ∧ '.join(parts)} → {self.head!r})"


def solve(body: tuple, store: FactStore, s: Subst | None = None) -> Iterator[Subst]:
    """Enumerate substitutions satisfying a conjunction of literals against the store.

    Negated literals are evaluated as "no instance exists" (¬∃), so variables that appear
    only inside a negation are existentially quantified inside it.
    """
    s = {} if s is None else s
    if not body:
        yield s
        return
    first, rest = body[0], body[1:]
    if isinstance(first, Not):
        if next(solve((first.atom,), store, s), None) is None:
            yield from solve(rest, store, s)
        return
    if first.pred in BUILTINS:
        for s2 in BUILTINS[first.pred](first.args, s):
            yield from solve(rest, store, s2)
        return
    goal = substitute(first, s)
    flat = not any(isinstance(a, Compound) for a in goal.args)
    for fact in store.with_pred(goal.pred):
        s2 = _match_flat(goal, fact, s) if flat else unify(goal, fact, s)
        if s2 is not None:
            yield from solve(rest, store, s2)


def _match_flat(goal: Atom, fact: Atom, s: Subst) -> Subst | None:
    """Fast path of unification for a goal with no function terms against a ground fact."""
    if len(goal.args) != len(fact.args):
        return None
    new = None
    for g, f in zip(goal.args, fact.args):
        if isinstance(g, Var):
            bound = new.get(g, g) if new else g
            if bound is g:
                new = {**s, g: f} if new is None else {**new, g: f}
            elif unify(bound, f) is None:
                return None
        elif unify(g, f) is None:
            return None
    return s if new is None else new


class KnowledgeBase:
    """A set of rules, automatically stratified so negation-as-failure is well defined."""

    def __init__(self, rules: Iterable[Rule]):
        self.rules = list(rules)
        self.strata = self._stratify()

    def _stratify(self) -> list[list[Rule]]:
        heads = {r.head.pred for r in self.rules}
        level = {p: 0 for p in heads}
        for _ in range(len(heads) + 1):
            changed = False
            for r in self.rules:
                for lit in r.body:
                    neg = isinstance(lit, Not)
                    pred = lit.atom.pred if neg else lit.pred
                    if pred not in level:
                        continue  # base (EDB) predicate or built-in
                    need = level[pred] + (1 if neg else 0)
                    if level[r.head.pred] < need:
                        level[r.head.pred] = need
                        changed = True
            if not changed:
                break
        else:
            raise ValueError("rules are not stratifiable (recursion through negation)")
        strata: list[list[Rule]] = [[] for _ in range(max(level.values(), default=0) + 1)]
        for r in self.rules:
            strata[level[r.head.pred]].append(r)
        return strata

    def closure(self, facts: Iterable[Atom], proofs: dict | None = None) -> FactStore:
        """Forward chaining to the least (perfect) model. If `proofs` is a dict, record for each
        derived fact the rule and ground body that first produced it."""
        store = FactStore(facts)
        for stratum in self.strata:
            changed = True
            while changed:
                changed = False
                for rule in stratum:
                    for s in list(solve(rule.body, store)):
                        fact = substitute(rule.head, s)
                        if store.add(fact):
                            changed = True
                            if proofs is not None:
                                proofs[fact] = (rule, [substitute(l, s) for l in rule.body])
        return store

    def query(self, goal: str | tuple, facts: Iterable[Atom] | FactStore) -> list[Subst]:
        body = parse_body(goal) if isinstance(goal, str) else goal
        store = facts if isinstance(facts, FactStore) else self.closure(facts)
        qvars = sorted(set().union(*(variables(l) for l in body)), key=lambda v: v.name)
        seen, answers = set(), []
        for s in solve(body, store):
            ans = tuple((v, substitute(v, s)) for v in qvars if not v.name.startswith("_"))
            if ans not in seen:
                seen.add(ans)
                answers.append(dict(ans))
        return answers


def explain(fact: Atom, proofs: dict, indent: int = 0) -> list[str]:
    """Proof tree for a derived fact, as indented lines."""
    pad = "  " * indent
    if fact not in proofs:
        return [f"{pad}{fact!r}   [fact]"]
    rule, body = proofs[fact]
    lines = [f"{pad}{fact!r}   [rule: {rule!r}]"]
    for lit in body:
        if isinstance(lit, Not):
            lines.append(f"{pad}  {lit!r}   [not provable]")
        elif lit.pred in BUILTINS:
            lines.append(f"{pad}  {lit!r}   [built-in]")
        else:
            lines.extend(explain(lit, proofs, indent + 1))
    return lines


# --------------------------------------------------------------------------- parser

_TOKEN = re.compile(r"""
    \s*(?:
      (?P<str>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
    | (?P<num>-?\d+(?:\.\d+)?)
    | (?P<op>:-|>=|<=|!=|[<>=+\-*(),.])
    | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
    )""", re.VERBOSE)


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens, pos = [], 0
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise SyntaxError(f"unexpected character at {pos}: {text[pos:pos + 20]!r}")
        pos = m.end()
        kind = m.lastgroup
        tokens.append((kind, m.group(kind)))
    return tokens


class _Parser:
    def __init__(self, text: str):
        self.toks = _tokenize(text)
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self, value=None):
        tok = self.peek()
        if tok[0] is None or (value is not None and tok[1] != value):
            raise SyntaxError(f"expected {value!r}, got {tok[1]!r}")
        self.i += 1
        return tok

    def done(self):
        return self.i >= len(self.toks)

    def term(self) -> Term:
        left = self.simple_term()
        while self.peek()[1] in ("+", "-", "*"):
            op = self.take()[1]
            left = Compound(op, (left, self.simple_term()))
        return left

    def simple_term(self) -> Term:
        kind, val = self.take()
        if kind == "str":
            return re.sub(r"\\(.)", r"\1", val[1:-1])
        if kind == "num":
            return float(val) if "." in val else int(val)
        if kind == "id":
            if self.peek()[1] == "(":
                return Compound(val, self.args())
            return Var(val) if (val[0].isupper() or val[0] == "_") else val
        raise SyntaxError(f"unexpected token {val!r}")

    def args(self) -> tuple:
        self.take("(")
        out = []
        if self.peek()[1] != ")":
            out.append(self.term())
            while self.peek()[1] == ",":
                self.take(",")
                out.append(self.term())
        self.take(")")
        return tuple(out)

    def literal(self) -> Literal:
        if self.peek() == ("id", "not"):
            self.take()
            return Not(self.literal())
        kind, val = self.peek()
        if kind == "id" and self.toks[self.i + 1:self.i + 2] == [("op", "(")] and val[0].isupper():
            self.take()
            atom = Atom(val, self.args())
            if self.peek()[1] not in BUILTINS:
                return atom
            left: Term = Compound(atom.pred, atom.args)  # unusual: compound on lhs of comparison
        else:
            left = self.term()
        op = self.take()[1]
        if op not in BUILTINS:
            raise SyntaxError(f"expected comparison operator, got {op!r}")
        return Atom(op, (left, self.term()))

    def body(self) -> tuple:
        lits = [self.literal()]
        while self.peek()[1] == ",":
            self.take(",")
            lits.append(self.literal())
        return tuple(lits)


def parse_atom(text: str) -> Atom:
    p = _Parser(text)
    lit = p.literal()
    if p.peek()[1] == ".":
        p.take(".")
    if not p.done() or not isinstance(lit, Atom):
        raise SyntaxError(f"not a single atom: {text!r}")
    return lit


def parse_body(text: str) -> tuple:
    p = _Parser(text)
    body = p.body()
    if p.peek()[1] == ".":
        p.take(".")
    if not p.done():
        raise SyntaxError(f"trailing input in {text!r}")
    return body


def parse_program(text: str) -> tuple[list[Atom], list[Rule]]:
    """Parse a .fol file: clauses end with '.', comments start with '%' or '#'."""
    facts, rules = [], []
    clean = "\n".join(_strip_comment(line) for line in text.splitlines())
    for clause in _split_clauses(clean):
        p = _Parser(clause)
        head = p.literal()
        if not isinstance(head, Atom) or head.pred in BUILTINS:
            raise SyntaxError(f"clause head must be an atom: {clause!r}")
        if p.done():
            if not head.is_ground():
                raise SyntaxError(f"facts must be ground: {clause!r}")
            facts.append(head)
            continue
        p.take(":-")
        rules.append(Rule(head, p.body()))
        if not p.done():
            raise SyntaxError(f"trailing input in {clause!r}")
    return facts, rules


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            out.append(ch)
        elif ch in "%#":
            break
        else:
            out.append(ch)
    return "".join(out)


def _split_clauses(text: str) -> list[str]:
    """Split on '.' that ends a clause (not inside quotes and not a decimal point)."""
    clauses, cur, quote = [], [], None
    for i, ch in enumerate(text):
        if quote:
            cur.append(ch)
            if ch == quote and text[i - 1] != "\\":
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        if ch == "." and not (i + 1 < len(text) and text[i + 1].isdigit() and i > 0 and text[i - 1].isdigit()):
            clause = "".join(cur).strip()
            if clause:
                clauses.append(clause)
            cur = []
            continue
        cur.append(ch)
    if "".join(cur).strip():
        raise SyntaxError(f"clause missing final '.': {''.join(cur).strip()!r}")
    return clauses


def load_program(*paths) -> tuple[list[Atom], list[Rule]]:
    facts, rules = [], []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            f, r = parse_program(fh.read())
        facts += f
        rules += r
    return facts, rules
