#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import os
import random
import re
import statistics
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


ASSIGN_RE = re.compile(
    r"^(?P<indent>\s{4})(?P<name>[A-Z][A-Z0-9_]+)\s*=\s*(?P<value>-?\d+(?:\.\d+)?)\s*$",
    re.M,
)
DAY_RE = re.compile(r"^\s*(?P<day>-?\d+)\s+(?P<ticks>\d+)\s+(?P<fills>\d+)\s+(?P<pnl>-?\d[\d,]*\.\d+)\s*$", re.M)
DEFAULT_PARAM_KEYS = ("TH", "LIMIT", "SPREAD", "WIDTH", "MULT", "CAP", "ALPHA", "WEIGHT", "QTY", "DECAY")


@dataclass(frozen=True)
class Constant:
    name: str
    value: float
    is_int: bool


@dataclass(frozen=True)
class Patch:
    name: str
    updates: Dict[str, float]


@dataclass
class Result:
    name: str
    ok: bool
    score: float
    total_pnl: float
    mean_daily_pnl: float
    daily_std: float
    sharpe: float
    max_drawdown: float
    min_day: float
    trader_path: Path
    updates: Dict[str, float]
    error: str = ""


def numeric_constants(source: str) -> Dict[str, Constant]:
    constants: Dict[str, Constant] = {}
    for match in ASSIGN_RE.finditer(source):
        name = match.group("name")
        raw_value = match.group("value")
        if name.startswith("_"):
            continue
        constants[name] = Constant(name=name, value=float(raw_value), is_int="." not in raw_value)
    return constants


def choose_constants(constants: Dict[str, Constant], names: Sequence[str], max_params: int) -> List[Constant]:
    if names:
        chosen = [constants[name] for name in names if name in constants]
        missing = [name for name in names if name not in constants]
        if missing:
            print(f"Skipping unknown params: {', '.join(missing)}", file=sys.stderr)
        return chosen

    chosen = [
        constant
        for name, constant in constants.items()
        if any(key in name for key in DEFAULT_PARAM_KEYS)
    ]
    return chosen[:max_params]


def rounded_value(value: float, is_int: bool) -> float:
    if is_int:
        return float(int(round(value)))
    if abs(value) >= 100:
        return round(value, 1)
    if abs(value) >= 10:
        return round(value, 2)
    if abs(value) >= 1:
        return round(value, 3)
    return round(value, 5)


def perturb_constant(constant: Constant, rng: random.Random, nudge_scale: float) -> float:
    base = constant.value
    scale = max(0.0, nudge_scale)

    if base == 0:
        value = rng.uniform(-0.1, 0.1) * scale
    elif abs(base) >= 1000:
        value = base + rng.uniform(-5.0, 5.0) * scale
    elif abs(base) >= 100:
        value = base + rng.uniform(-2.0, 2.0) * scale
    else:
        # Small constants usually behave more naturally under relative nudges.
        width = 0.10 * scale
        value = base * (1.0 + rng.uniform(-width, width))

    value = rounded_value(value, constant.is_int)
    if value == base:
        step = 1.0 if constant.is_int else max(abs(base) * 0.01, 0.0001)
        value = rounded_value(base + rng.choice((-step, step)), constant.is_int)
    return value


def generate_patches(
    constants: Sequence[Constant],
    trials: int,
    seed: int,
    mutation_rate: float,
    nudge_scale: float,
) -> List[Patch]:
    rng = random.Random(seed)
    mutation_rate = min(1.0, max(0.0, mutation_rate))
    patches: List[Patch] = []

    for trial in range(1, trials + 1):
        updates: Dict[str, float] = {}
        for constant in constants:
            if rng.random() <= mutation_rate:
                updates[constant.name] = perturb_constant(constant, rng, nudge_scale)

        if not updates and constants:
            constant = rng.choice(list(constants))
            updates[constant.name] = perturb_constant(constant, rng, nudge_scale)

        patches.append(Patch(name=f"trial_{trial:04d}", updates=updates))

    return patches


def format_literal(value: float, original: Constant) -> str:
    if original.is_int:
        return str(int(round(value)))
    return repr(float(value))


def patch_source(source: str, patch: Patch, constants: Dict[str, Constant]) -> str:
    updated = source
    for name, value in patch.updates.items():
        original = constants[name]
        pattern = rf"^(?P<indent>\s{{4}}){re.escape(name)}\s*=\s*-?\d+(?:\.\d+)?\s*$"
        literal = format_literal(value, original)
        replacement = lambda m, n=name, v=literal: f"{m.group('indent')}{n} = {v}"
        updated, count = re.subn(pattern, replacement, updated, count=1, flags=re.M)
        if count != 1:
            raise RuntimeError(f"Could not patch {name}")
    return updated


def run_backtester(backtester: Path, trader: Path, dataset: Path, timeout: int) -> Tuple[bool, List[float], str]:
    cmd = [
        sys.executable,
        str(backtester),
        "--trader",
        str(trader),
        "--dataset",
        str(dataset),
        "--products",
        "off",
        "--jobs",
        "1",
    ]
    try:
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout if isinstance(exc.stdout, str) else ""
        return False, [], output + "\nTimed out"

    output = proc.stdout
    if proc.returncode != 0:
        return False, [], output

    days: List[float] = []
    for match in DAY_RE.finditer(output):
        days.append(float(match.group("pnl").replace(",", "")))
    return bool(days), days, output


def max_drawdown(days: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for pnl in days:
        equity += pnl
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return abs(worst)


def metrics(days: Sequence[float], score_mode: str, std_penalty: float) -> Tuple[float, float, float, float, float, float, float]:
    total = float(sum(days))
    mean = statistics.mean(days) if days else float("-inf")
    daily_std = statistics.pstdev(days) if len(days) > 1 else 0.0
    min_day = min(days) if days else float("-inf")
    drawdown = max_drawdown(days)

    if daily_std == 0:
        sharpe = math.copysign(float("inf"), mean) if mean != 0 else 0.0
    else:
        sharpe = (mean / daily_std) * math.sqrt(len(days))

    if score_mode == "mean_std":
        score = mean - std_penalty * daily_std
    elif score_mode == "total_std":
        score = total - std_penalty * daily_std
    elif score_mode == "sharpe":
        score = sharpe
    elif score_mode == "std":
        score = -daily_std
    elif score_mode == "total":
        score = total
    else:
        raise ValueError(f"Unknown score mode: {score_mode}")

    return score, total, mean, daily_std, sharpe, drawdown, min_day


def evaluate_candidate(
    name: str,
    trader_path: Path,
    updates: Dict[str, float],
    backtester: Path,
    dataset: Path,
    timeout: int,
    score_mode: str,
    std_penalty: float,
) -> Result:
    ok, days, output = run_backtester(backtester, trader_path, dataset, timeout)
    if not ok:
        return Result(
            name=name,
            ok=False,
            score=float("-inf"),
            total_pnl=float("-inf"),
            mean_daily_pnl=float("-inf"),
            daily_std=float("inf"),
            sharpe=float("-inf"),
            max_drawdown=float("inf"),
            min_day=float("-inf"),
            trader_path=trader_path,
            updates=updates,
            error=output.strip().splitlines()[-1] if output.strip() else "backtest failed",
        )

    score, total, mean, daily_std, sharpe, drawdown, min_day = metrics(days, score_mode, std_penalty)
    return Result(
        name=name,
        ok=True,
        score=score,
        total_pnl=total,
        mean_daily_pnl=mean,
        daily_std=daily_std,
        sharpe=sharpe,
        max_drawdown=drawdown,
        min_day=min_day,
        trader_path=trader_path,
        updates=updates,
    )


def finite_str(value: float) -> str:
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    if math.isnan(value):
        return "nan"
    return f"{value:.4f}"


def write_results(path: Path, results: Iterable[Result]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "name",
                "ok",
                "score",
                "total_pnl",
                "mean_daily_pnl",
                "daily_std",
                "sharpe",
                "max_drawdown",
                "min_day",
                "updates",
                "trader_path",
                "error",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "name": result.name,
                    "ok": int(result.ok),
                    "score": finite_str(result.score),
                    "total_pnl": finite_str(result.total_pnl),
                    "mean_daily_pnl": finite_str(result.mean_daily_pnl),
                    "daily_std": finite_str(result.daily_std),
                    "sharpe": finite_str(result.sharpe),
                    "max_drawdown": finite_str(result.max_drawdown),
                    "min_day": finite_str(result.min_day),
                    "updates": repr(result.updates),
                    "trader_path": str(result.trader_path),
                    "error": result.error,
                }
            )


def print_table(results: Sequence[Result], limit: int) -> None:
    print("NAME             OK        SCORE      TOTAL_PNL       MEAN       STD    SHARPE    MAX_DD    MIN_DAY")
    for result in results[:limit]:
        print(
            f"{result.name[:15]:<15} {str(result.ok):>3} "
            f"{result.score:>12.2f} {result.total_pnl:>14.2f} {result.mean_daily_pnl:>10.2f} "
            f"{result.daily_std:>9.2f} {result.sharpe:>9.3f} {result.max_drawdown:>9.2f} {result.min_day:>10.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Parallel Monte Carlo tuner for nearby IMC trader constants")
    parser.add_argument("--trader", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--backtester", type=Path, default=Path(__file__).with_name("backtester.py"))
    parser.add_argument("--output", type=Path, default=Path("monte_carlo_tuner_results.csv"))
    parser.add_argument("--materialize-best", type=Path)
    parser.add_argument("--params", nargs="*", default=[], help="Specific class constants to tune")
    parser.add_argument("--max-params", type=int, default=12, help="Maximum auto-detected params to perturb")
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--nudge-scale", type=float, default=1.0)
    parser.add_argument("--mutation-rate", type=float, default=0.35)
    parser.add_argument("--std-penalty", type=float, default=1.0)
    parser.add_argument(
        "--score-mode",
        choices=("mean_std", "total_std", "sharpe", "std", "total"),
        default="mean_std",
        help="Ranking metric; mean_std is mean_daily_pnl - std_penalty * daily_std",
    )
    parser.add_argument("--top", type=int, default=10, help="Rows to print after sorting")
    args = parser.parse_args()

    source = args.trader.read_text()
    constants = numeric_constants(source)
    chosen = choose_constants(constants, args.params, args.max_params)
    if not chosen:
        raise SystemExit("No tunable constants found. Pass --params with class-level numeric constant names.")

    print("Tuning params: " + ", ".join(constant.name for constant in chosen))

    patches = generate_patches(
        constants=chosen,
        trials=max(0, args.trials),
        seed=args.seed,
        mutation_rate=args.mutation_rate,
        nudge_scale=args.nudge_scale,
    )

    results: List[Result] = [
        evaluate_candidate(
            name="baseline",
            trader_path=args.trader,
            updates={},
            backtester=args.backtester,
            dataset=args.dataset,
            timeout=args.timeout,
            score_mode=args.score_mode,
            std_penalty=args.std_penalty,
        )
    ]

    with tempfile.TemporaryDirectory(prefix="imc_mc_tune_") as tmp:
        tmpdir = Path(tmp)
        jobs = []
        for index, patch in enumerate(patches, 1):
            candidate = tmpdir / f"candidate_{index:04d}.py"
            candidate.write_text(patch_source(source, patch, constants))
            jobs.append((patch, candidate))

        with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = [
                pool.submit(
                    evaluate_candidate,
                    patch.name,
                    candidate,
                    patch.updates,
                    args.backtester,
                    args.dataset,
                    args.timeout,
                    args.score_mode,
                    args.std_penalty,
                )
                for patch, candidate in jobs
            ]
            for future in as_completed(futures):
                results.append(future.result())

    results.sort(key=lambda result: result.score, reverse=True)
    write_results(args.output, results)
    print_table(results, args.top)

    best = results[0]
    if args.materialize_best:
        if best.updates:
            args.materialize_best.write_text(patch_source(source, Patch(best.name, best.updates), constants))
            print(f"\nBest patched trader written to {args.materialize_best}")
        else:
            print("\nBaseline ranked best; no patched trader written.")

    print(f"\nFull results written to {args.output}")


if __name__ == "__main__":
    main()
