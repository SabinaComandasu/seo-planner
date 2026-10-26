"""Plain-English rendering of facts, query answers and proofs.

The logic stays the source of truth; these sentences are only a reading aid for the UI.
Every unknown predicate falls back to its logic notation, so nothing is ever hidden.
"""
from __future__ import annotations

from .fol import BUILTINS, Atom, Compound, Not, fmt

NOT_RANKING = 101


def _kw(t) -> str:
    return f"“{t}”"


def _pos(p) -> str:
    return "not ranking" if isinstance(p, (int, float)) and p >= NOT_RANKING else f"#{p}"


def _ranking(a):
    k, p = a
    return f"we're not ranking for {_kw(k)}" if p >= NOT_RANKING else f"we rank #{p} for {_kw(k)}"


def _previous(a):
    k, p = a
    return (f"we weren't ranking for {_kw(k)} in the previous update" if p >= NOT_RANKING
            else f"we ranked #{p} for {_kw(k)} in the previous update")


# predicate -> (positive sentence, negative sentence or None for the generic "not" form)
PHRASES = {
    "Tracked": (lambda a: f"{_kw(a[0])} is tracked in AWR", None),
    "Ranking": (_ranking, None),
    "PreviousRanking": (_previous, None),
    "CompetitorRanking": (lambda a: f"{a[1]} ranks {_pos(a[2])} for {_kw(a[0])}", None),
    "RankingUrl": (lambda a: f"our page {a[1]} ranks for {_kw(a[0])}", None),
    "InGroup": (lambda a: f"{_kw(a[0])} is in the keyword group {_kw(a[1])}", None),
    "InTop3": (lambda a: f"{_kw(a[0])} is in the top 3", lambda a: f"{_kw(a[0])} is not in the top 3"),
    "FirstPage": (lambda a: f"{_kw(a[0])} is on page 1", lambda a: f"{_kw(a[0])} is not on page 1"),
    "StrikingDistance": (lambda a: f"{_kw(a[0])} is within striking distance (#4–#20)",
                         lambda a: f"{_kw(a[0])} is not within striking distance (#4–#20)"),
    "NotRanking": (lambda a: f"we're not ranking for {_kw(a[0])} (below #50)",
                   lambda a: f"we do rank for {_kw(a[0])} (#50 or better)"),
    "Dropped": (lambda a: f"{_kw(a[0])} dropped 5 or more positions",
                lambda a: f"{_kw(a[0])} did not drop 5 or more positions"),
    "Improving": (lambda a: f"{_kw(a[0])} climbed 5 or more positions", None),
    "BeatenBy": (lambda a: f"{a[1]} ranks above us for {_kw(a[0])}", None),
    "LosingToCompetitor": (lambda a: f"a competitor ranks above us for {_kw(a[0])}",
                           lambda a: f"no competitor ranks above us for {_kw(a[0])}"),
    "OutrankedByAll": (lambda a: f"every competitor ranks above us for {_kw(a[0])}", None),
    "BeatsSomeCompetitor": (lambda a: f"we beat at least one competitor for {_kw(a[0])}",
                            lambda a: f"we don't beat any competitor for {_kw(a[0])}"),
    "RankingPageExists": (lambda a: f"we have a page for {_kw(a[0])}",
                          lambda a: f"we don't have a page for {_kw(a[0])} yet"),
    "NeedsOptimization": (lambda a: f"{_kw(a[0])} needs work", lambda a: f"{_kw(a[0])} doesn't need work"),
    "Healthy": (lambda a: f"{_kw(a[0])} is healthy", None),
    "Urgent": (lambda a: f"{_kw(a[0])} is urgent", lambda a: f"{_kw(a[0])} is not urgent"),
    "Priority": (lambda a: f"{_kw(a[0])} has priority {a[1]} (1 = most urgent)", None),
    "HigherPriority": (lambda a: f"{_kw(a[0])} comes before {_kw(a[1])} in priority", None),
    "InScope": (lambda a: f"{_kw(a[0])} is part of this plan", None),
    # planning state
    "Audited": (lambda a: f"{_kw(a[0])} has been audited", lambda a: f"{_kw(a[0])} hasn't been audited yet"),
    "DropInvestigated": (lambda a: f"the drop of {_kw(a[0])} has been investigated",
                         lambda a: f"the drop of {_kw(a[0])} hasn't been investigated yet"),
    "CompetitorsAnalyzed": (lambda a: f"the competitors for {_kw(a[0])} have been analysed",
                            lambda a: f"the competitors for {_kw(a[0])} haven't been analysed yet"),
    "OnPageOptimized": (lambda a: f"the page for {_kw(a[0])} got an on-page tune-up",
                        lambda a: f"the page for {_kw(a[0])} hasn't had an on-page tune-up yet"),
    "ContentImproved": (lambda a: f"the content for {_kw(a[0])} has been improved",
                        lambda a: f"the content for {_kw(a[0])} hasn't been improved yet"),
    "HasLandingPage": (lambda a: f"a landing page for {_kw(a[0])} has been built",
                       lambda a: f"there is no new landing page for {_kw(a[0])} yet"),
    "InternalLinksAdded": (lambda a: f"internal links to {_kw(a[0])} have been added",
                           lambda a: f"internal links to {_kw(a[0])} haven't been added yet"),
    "Rechecked": (lambda a: f"a ranking re-check for {_kw(a[0])} is scheduled",
                  lambda a: f"no ranking re-check for {_kw(a[0])} is scheduled yet"),
    "Improved": (lambda a: f"the page for {_kw(a[0])} has been improved", None),
    "DropHandled": (lambda a: f"any drop of {_kw(a[0])} has been dealt with", None),
    "GapHandled": (lambda a: f"the competitor gap for {_kw(a[0])} has been dealt with", None),
    "Addressed": (lambda a: f"all the work for {_kw(a[0])} is done", None),
    "Blocked": (lambda a: f"{_kw(a[0])} must wait for a more urgent keyword",
                lambda a: f"no more urgent keyword is still waiting before {_kw(a[0])}"),
    "Done": (lambda a: f"{_kw(a[0])} is done", None),
}

_OPS = {">": ">", "<": "<", ">=": "≥", "<=": "≤", "!=": "≠", "=": "="}


def _term(t) -> str:
    if isinstance(t, Compound) and t.functor in "+-*" and len(t.args) == 2:
        sym = {"-": "−", "+": "+", "*": "×"}[t.functor]
        return f"{_term(t.args[0])} {sym} {_term(t.args[1])}"
    if isinstance(t, (int, float)):
        return "not ranking (101)" if t >= NOT_RANKING else str(t)
    return fmt(t) if not isinstance(t, str) else str(t)


def sentence(lit) -> str:
    """One literal (ground or not) as an English sentence."""
    if isinstance(lit, Not):
        atom = lit.atom
        entry = PHRASES.get(atom.pred)
        if entry and entry[1] and atom.is_ground():
            return entry[1](atom.args)
        return f"there's no evidence that {sentence(atom)}"
    if lit.pred == "is":
        return f"{_term(lit.args[0])} = {_term(lit.args[1])}"
    if lit.pred in BUILTINS:
        return f"{_term(lit.args[0])} {_OPS.get(lit.pred, lit.pred)} {_term(lit.args[1])}"
    entry = PHRASES.get(lit.pred)
    if entry and lit.is_ground():
        try:
            return entry[0](lit.args)
        except (IndexError, TypeError):
            pass
    return repr(lit)


def proof_tree(fact: Atom, proofs: dict, depth: int = 0, max_depth: int = 8) -> dict:
    """Why a fact holds, as nested nodes for the UI.

    kind: "fact" (from AWR data), "rule" (derived), "calc" (arithmetic / comparison) or
    "not" (negation-as-failure: nothing in the knowledge base proves it).
    """
    if fact not in proofs or depth >= max_depth:
        return {"kind": "fact", "text": sentence(fact), "logic": repr(fact)}
    rule, body = proofs[fact]
    children = []
    for lit in body:
        if isinstance(lit, Not):
            children.append({"kind": "not", "text": sentence(lit), "logic": repr(lit)})
        elif lit.pred in BUILTINS:
            children.append({"kind": "calc", "text": sentence(lit), "logic": repr(lit)})
        else:
            children.append(proof_tree(lit, proofs, depth + 1, max_depth))
    return {"kind": "rule", "text": sentence(fact), "logic": repr(fact), "rule": rule.doc or repr(rule),
            "rule_logic": repr(rule), "children": children}


def proof_lines(node: dict, indent: int = 0) -> list[str]:
    """A proof tree as indented text lines (for the command line)."""
    pad = "    " * indent
    note = {"fact": "  [AWR data]", "calc": "  [calculation]", "not": "  [nothing in the data says otherwise]"}
    if node["kind"] != "rule":
        return [f"{pad}- {node['text']}{note[node['kind']]}"]
    lines = [f"{pad}- {node['text']}  [rule: {node['rule']}]", f"{pad}  because:"]
    for child in node["children"]:
        lines += proof_lines(child, indent + 1)
    return lines
