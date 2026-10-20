"""Reproducible LR09 reference experiment. Never writes project velocity/forecast."""

import argparse
import csv
import hashlib
import json
import math
import random
from pathlib import Path


def simulate(remaining, history, simulations=10000, seed=20261020):
    if not math.isfinite(remaining) or remaining < 0:
        raise ValueError("remaining must be finite and nonnegative")
    if simulations < 1000:
        raise ValueError("at least 1000 simulations required")
    if remaining == 0:
        return [0] * simulations
    if not history or any(not math.isfinite(v) or v < 0 for v in history):
        raise ValueError("velocity must be a nonempty finite nonnegative sample")
    if not any(v > 0 for v in history):
        raise ValueError("all-zero velocity cannot produce a finite forecast")
    rng = random.Random(seed)
    results = []
    for _ in range(simulations):
        left, sprints = remaining, 0
        while left > 0:
            left -= rng.choice(history)
            sprints += 1  # A zero-velocity sprint still consumes time.
            if sprints > 100000:
                raise RuntimeError("simulation too long; result not truncated")
        results.append(sprints)
    return sorted(results)


def percentile(sorted_results, probability):
    """Nearest rank: first integer sprint with empirical CDF >= probability."""
    if not sorted_results or not 0 < probability <= 1:
        raise ValueError("nonempty sorted sample and 0 < probability <= 1 required")
    return sorted_results[math.ceil(probability * len(sorted_results)) - 1]


def self_test():
    # Known mathematical cases, including the zero-throughput trap.
    assert simulate(0, [], 1000) == [0] * 1000
    assert simulate(25, [10], 1000) == [3] * 1000
    assert percentile([1, 2, 3, 4], 0.50) == 2
    assert percentile([1, 2, 3, 4], 0.85) == 4
    for history in ([0, 0], [-1, 10], [float("nan")], []):
        try:
            simulate(20, history, 1000)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid history accepted")
    draws = simulate(20, [0, 10], 10000)
    assert min(draws) == 2 and max(draws) > 2
    # Exact negative-binomial CDF: two successes in <=3 fair draws has P=0.5.
    cdf_at_three = sum(v <= 3 for v in draws) / len(draws)
    assert abs(cdf_at_three - 0.5) < 0.03
    assert draws == simulate(20, [0, 10], 10000)


def reference_experiment(path, points, simulations, seed):
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_sprint = {int(row["sprint"]): float(row["points_done"]) for row in rows}
    if len(rows) != 12 or set(by_sprint) != set(range(1, 13)):
        raise ValueError("expected the 12-sprint course reference dataset")
    groups = {"all_12": list(range(1, 13)), "sprints_1_2": [1, 2], "sprints_5_6": [5, 6]}
    output = {
        "source": "course reference, not CampusReserve velocity",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "points": points,
        "simulations_per_run": simulations,
        "seed_per_run": seed,
        "quantile": "nearest rank: ceil(p*N)-1 in a sorted zero-indexed list",
        "runs": {},
    }
    for name, ids in groups.items():
        history = [by_sprint[i] for i in ids]
        results = simulate(points, history, simulations, seed)
        p50, p85 = percentile(results, 0.50), percentile(results, 0.85)
        output["runs"][name] = {
            "history": history, "n": len(history),
            "p50_sprints": p50, "p85_sprints": p85, "width": p85 - p50,
        }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=Path(__file__).with_name("reference_velocity.csv"))
    parser.add_argument("--points", type=float, default=220)
    parser.add_argument("--simulations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("Self-test passed: exact duration, quantiles, zeros, input validation, seed.")
    else:
        print(json.dumps(reference_experiment(args.reference, args.points, args.simulations, args.seed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
