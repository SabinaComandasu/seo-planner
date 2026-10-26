"""Generic state-space search: breadth-first search, uniform-cost search and A*.

A problem supplies:
  initial               -> hashable start state
  is_goal(state)        -> bool
  successors(state)     -> iterable of (action, next_state, step_cost)
  heuristic(state)      -> admissible estimate of remaining cost (A* only)
"""
from __future__ import annotations

import heapq
import itertools
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class SearchResult:
    algorithm: str
    plan: list | None          # list of (action, step_cost); None if no plan was found
    cost: float
    expanded: int
    generated: int
    seconds: float
    reason: str = ""           # why the search stopped without a plan

    @property
    def found(self) -> bool:
        return self.plan is not None


class _Limit(Exception):
    pass


def _reconstruct(parents, state):
    plan = []
    while parents[state] is not None:
        prev, action, cost = parents[state]
        plan.append((action, cost))
        state = prev
    return plan[::-1]


def bfs(problem, max_expanded: int = 200_000) -> SearchResult:
    """Fewest actions (ignores costs). Goal test on generation."""
    start = time.perf_counter()
    parents = {problem.initial: None}
    if problem.is_goal(problem.initial):
        return SearchResult("BFS", [], 0, 0, 1, time.perf_counter() - start)
    frontier, expanded, generated = deque([problem.initial]), 0, 1
    while frontier:
        state = frontier.popleft()
        expanded += 1
        if expanded > max_expanded:
            return SearchResult("BFS", None, 0, expanded, generated, time.perf_counter() - start,
                                f"node limit {max_expanded} reached")
        for action, nxt, cost in problem.successors(state):
            generated += 1
            if nxt in parents:
                continue
            parents[nxt] = (state, action, cost)
            if problem.is_goal(nxt):
                plan = _reconstruct(parents, nxt)
                return SearchResult("BFS", plan, sum(c for _, c in plan), expanded, generated,
                                    time.perf_counter() - start)
            frontier.append(nxt)
    return SearchResult("BFS", None, 0, expanded, generated, time.perf_counter() - start, "no plan exists")


def best_first(problem, use_heuristic: bool, max_expanded: int = 200_000) -> SearchResult:
    """Uniform-cost search (h = 0) or A* (f = g + h). Optimal when h is admissible and consistent.

    Ties on f are broken in favour of larger g (deeper nodes), which avoids exploring the many
    equal-cost interleavings of independent actions.
    """
    name = "A*" if use_heuristic else "UCS"
    h = problem.heuristic if use_heuristic else (lambda s: 0)
    start = time.perf_counter()
    counter = itertools.count()
    g = {problem.initial: 0}
    parents = {problem.initial: None}
    frontier = [(h(problem.initial), 0, next(counter), problem.initial)]
    closed, expanded, generated = set(), 0, 1
    while frontier:
        _, neg_g, _, state = heapq.heappop(frontier)
        if state in closed:
            continue
        if problem.is_goal(state):
            plan = _reconstruct(parents, state)
            return SearchResult(name, plan, g[state], expanded, generated, time.perf_counter() - start)
        closed.add(state)
        expanded += 1
        if expanded > max_expanded:
            return SearchResult(name, None, 0, expanded, generated, time.perf_counter() - start,
                                f"node limit {max_expanded} reached")
        for action, nxt, cost in problem.successors(state):
            generated += 1
            new_g = g[state] + cost
            if nxt not in g or new_g < g[nxt]:
                g[nxt] = new_g
                parents[nxt] = (state, action, cost)
                heapq.heappush(frontier, (new_g + h(nxt), -new_g, next(counter), nxt))
    return SearchResult(name, None, 0, expanded, generated, time.perf_counter() - start, "no plan exists")


def ucs(problem, max_expanded: int = 200_000) -> SearchResult:
    return best_first(problem, use_heuristic=False, max_expanded=max_expanded)


def astar(problem, max_expanded: int = 200_000) -> SearchResult:
    return best_first(problem, use_heuristic=True, max_expanded=max_expanded)


ALGORITHMS = {"bfs": bfs, "ucs": ucs, "astar": astar}
