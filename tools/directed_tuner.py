#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import itertools
import math
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


ASSIGN_RE = re.compile(r"^(?P<indent>\s{4})(?P<name>[A-Z][A-Z0-9_]+)\s*=\s*(?P<value>-?\d+(?:\.\d+)?)\s*$", re.M)
DAY_RE = re.compile(r"^\s*(?P<day>-?\d+)\s+(?P<ticks>\d+)\s+(?P<fills>\d+)\s+(?P<pnl>-?\d[\d,]*\.\d+)\s*$", re.M)


@dataclass(frozen=True)
class Patch:
    name: str
    updates: Dict[str, float]


@dataclass
class Result:
    name: str
    score: float
    total_pnl: float
    daily_std: float
    min_day: float
    ok: bool
    trader_path: Path
    updates: Dict[str, float]


def numeric_constants(source: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for match in ASSIGN_RE.finditer(source):
        name = match.group("name")
        if name.startswith("_"):
            continue
        out[name] = float(match.group("value"))
    return out


def nearby_values(value: float) -> List[float]:
    if value == 0:
        return [0.0, 0.05, -0.05, 0.1, -0.1]
    if abs(value) >= 1000:
        return [round(value + delta, 1) for delta in (-5.0, -2.0, -1.0, 1.0, 2.0, 5.0)]
    if abs(value) >= 100:
        return [round(value + delta, 1) for delta in (-2.0, -1.0, 1.0, 2.0)]
    multipliers = [0.9, 0.95, 1.05, 1.1]
    values = [value * m for m in multipliers]
    if abs(value) >= 10:
        return [round(v, 1) for v in values]
    if abs(value) >= 1:
        return [round(v, 2) for v in values]
    return [round(v, 4) for v in values]


def generate_patches(constants: Dict[str, float], names: Sequence[str], max_patches: int) -> List[Patch]:
    chosen = [name for name in names if name in constants]
    if not chosen:
        chosen = [
            name for name in constants
            if any(key in name for key in ("TH", "LIMIT", "SPREAD", "WIDTH", "MULT", "CAP", "ALPHA", "WEIGHT"))
        ][:12]
    patches: List[Patch] = []
    for name in chosen:
        base = constants[name]
        for value in nearby_values(base):
            if value == base:
                continue
            patches.append(Patch(f"{name}={value:g}", {name: value}))
            if len(patches) >= max_patches:
                return patches
    return patches


def patch_source(source: str, patch: Patch) -> str:
    updated = source
    for name, value in patch.updates.items():
        pattern = rf"^(?P<indent>\s{{4}}){re.escape(name)}\s*=\s*-?\d+(?:\.\d+)?\s*$"
        replacement = lambda m, n=name, v=value: f"{m.group('indent')}{n} = {repr(v)}"
        updated, count = re.subn(pattern, replacement, updated, count=1, flags=re.M)
        if count != 1:
            raise RuntimeError(f"Could not patch {name}")
    return updated


def run_backtester(backtester: Path, trader: Path, dataset: Path, timeout: int) -> Tuple[bool, List[float], str]:
    cmd = [sys.executable, str(backtester), "--trader", str(trader), "--dataset", str(dataset), "--products", "off"]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    output = proc.stdout
    if proc.returncode != 0:
        return False, [], output
    days: List[float] = []
    for match in DAY_RE.finditer(output):
        days.append(float(match.group("pnl").replace(",", "")))
    return bool(days), days, output


def score_days(days: Sequence[float], variance_penalty: float) -> Tuple[float, float, float, float]:
    total = float(sum(days))
    daily_std = statistics.pstdev(days) if len(days) > 1 else 0.0
    min_day = min(days) if days else float("-inf")
    score = total - variance_penalty * daily_std
    return score, total, daily_std, min_day


def evaluate(
    name: str,
    trader_path: Path,
    updates: Dict[str, float],
    backtester: Path,
    dataset: Path,
    timeout: int,
    variance_penalty: float,
) -> Result:
    ok, days, _output = run_backtester(backtester, trader_path, dataset, timeout)
    if not ok:
        return Result(name, float("-inf"), float("-inf"), float("inf"), float("-inf"), False, trader_path, updates)
    score, total, daily_std, min_day = score_days(days, variance_penalty)
    return Result(name, score, total, daily_std, min_day, True, trader_path, updates)


def write_results(path: Path, results: Iterable[Result]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["name", "ok", "score", "total_pnl", "daily_std", "min_day", "updates", "trader_path"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "name": result.name,
                    "ok": int(result.ok),
                    "score": f"{result.score:.4f}" if math.isfinite(result.score) else result.score,
                    "total_pnl": f"{result.total_pnl:.4f}" if math.isfinite(result.total_pnl) else result.total_pnl,
                    "daily_std": f"{result.daily_std:.4f}" if math.isfinite(result.daily_std) else result.daily_std,
                    "min_day": f"{result.min_day:.4f}" if math.isfinite(result.min_day) else result.min_day,
                    "updates": repr(result.updates),
                    "trader_path": str(result.trader_path),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Directed one-constant-at-a-time tuner for IMC trader constants")
    parser.add_argument("--trader", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--backtester", type=Path, default=Path(__file__).with_name("backtester.py"))
    parser.add_argument("--output", type=Path, default=Path("directed_tuner_results.csv"))
    parser.add_argument("--materialize-best", type=Path)
    parser.add_argument("--params", nargs="*", default=[], help="Specific class constants to tune")
    parser.add_argument("--max-patches", type=int, default=40)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--variance-penalty", type=float, default=0.5)
    args = parser.parse_args()

    source = args.trader.read_text()
    constants = numeric_constants(source)
    patches = generate_patches(constants, args.params, args.max_patches)

    results: List[Result] = []
    baseline = evaluate("baseline", args.trader, {}, args.backtester, args.dataset, args.timeout, args.variance_penalty)
    results.append(baseline)

    with tempfile.TemporaryDirectory(prefix="imc_tune_") as tmp:
        tmpdir = Path(tmp)
        for index, patch in enumerate(patches, 1):
            candidate = tmpdir / f"candidate_{index:03d}.py"
            candidate.write_text(patch_source(source, patch))
            results.append(
                evaluate(patch.name, candidate, patch.updates, args.backtester, args.dataset, args.timeout, args.variance_penalty)
            )

    results.sort(key=lambda r: r.score, reverse=True)
    write_results(args.output, results)

    best = results[0]
    print("NAME                         OK       SCORE      TOTAL_PNL    DAILY_STD      MIN_DAY")
    for result in results[:10]:
        print(
            f"{result.name[:28]:<28} {str(result.ok):>3} "
            f"{result.score:>11.2f} {result.total_pnl:>14.2f} {result.daily_std:>12.2f} {result.min_day:>12.2f}"
        )

    if args.materialize_best and best.updates:
        args.materialize_best.write_text(patch_source(source, Patch(best.name, best.updates)))
        print(f"\nBest patched trader written to {args.materialize_best}")
    print(f"\nFull results written to {args.output}")


if __name__ == "__main__":
    main()
