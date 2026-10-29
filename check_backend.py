"""Small reproducible integration cases for Person 1, without altering solvers."""
import json
from experiments import (ROOT, ObservationEngine, compute_plan, forced_cells,
                         make_game, public_observation)
from minesweeper_game import Constraint
import hill_climbing as hc


def check():
    result = {"dfs_missing_safe": [], "hill_propagation": {}, "hill_transition": {}}
    for index in (2, 3):
        observation = public_observation(make_game(index))
        plan = compute_plan(observation, "DFS")
        expected, _, _ = forced_cells(observation)
        found = {tuple(c) for tag, c in plan["actions"] if tag == "safe"}
        result["dfs_missing_safe"].append({"case_id": f"T{index+1:02d}",
            "expected_safe": sorted(expected), "returned_safe": sorted(found),
            "missing_safe": sorted(expected-found)})
    cell = (0, 0)
    safe, mines, changed, status = hc.propagate(set(), set(), [Constraint(frozenset({cell}), 0)])
    result["hill_propagation"] = {"returned_safe": sorted(safe), "changed": changed,
                                  "status": status,
                                  "note": "Caller must keep returned sets before breaking on changed=False."}
    observation = {"rows": 5, "cols": 5, "mines": 4,
                   "numbers": [[2, 2, 0], [4, 3, 3]], "flags": []}
    solver = hc.HillClimbingSolver(ObservationEngine(observation))
    actual = []
    original = solver._best_candidate
    def tracked(obs, candidates, baseline):
        choice = original(obs, candidates, baseline)
        if choice is not None:
            actual.append({"current_score": baseline, "selected_score": choice[1],
                           "selected_cell": choice[0]})
        return choice
    solver._best_candidate = tracked
    for tag, cell in solver.solve():
        if tag == "guess":
            result["hill_transition"] = {"observation": observation, "accepted": actual[-1],
                                          "emitted_action": [tag, cell]}
            break
    path = ROOT / "backend_cases.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    check()
