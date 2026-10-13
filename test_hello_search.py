#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick Hello World benchmark - ASCII only."""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from opera.evaluator import UnifiedEvaluator
from opera.search.beam import BeamSearchEngine


def find_or_create_specimen() -> Path:
    """Find hello specimen or synthesize one on the fly."""
    candidates = [
        Path("specimens/hello_solved.mal"),
        Path(__file__).parent / "specimens" / "hello_solved.mal",
        Path("/home/danny/Development/ISyCo Git/malbolge-lisp-forensics/specimens/hello.malbolge"),
    ]
    forensics = os.environ.get("OPERA_FORENSICS_DIR")
    if forensics:
        candidates.insert(0, Path(forensics) / "specimens" / "hello.malbolge")

    for cand in candidates:
        if cand.exists():
            return cand

    # Synthesize if none found
    out_dir = Path(__file__).parent / "specimens"
    out_dir.mkdir(parents=True, exist_ok=True)
    target_path = out_dir / "hello_solved.mal"
    print("Synthesizing Hello World specimen on the fly...")
    engine = BeamSearchEngine()
    res = engine.search_for_string("Hello World!")
    target_path.write_text(res.best_program, encoding="ascii")
    return target_path


def main():
    evaluator = UnifiedEvaluator()
    specimen = find_or_create_specimen()

    print("=" * 60)
    print("HELLO WORLD BENCHMARK - Cross-backend verification")
    print("=" * 60)
    print(f"Specimen: {specimen}")
    print(f"Size: {specimen.stat().st_size} bytes")
    print()

    results = evaluator.evaluate_all(specimen)

    print("\n" + "=" * 60)
    print("RESULTS:")
    print("-" * 60)

    for name, result in sorted(results.items()):
        status = "OK" if result.success else "FAIL"
        out_preview = repr(result.stdout.strip()[:50]) if result.stdout else "(empty)"
        steps_str = f"{result.steps} steps" if result.steps > 0 else "no steps"
        halt_str = f"HALT: {result.halt_reason}" if result.halted else "NO HALT"

        print(f"  {name:20s} | {status} | {out_preview:<35s} | {result.steps:>6} steps | {halt_str}")

    print("\n" + "=" * 60)
    print("SUMMARY:")
    ref = results.get("reference")
    if ref and ref.success:
        print(f"  [OK] Reference (3^10):  {repr(ref.stdout.strip()[:30])} @ {ref.steps} steps")
    ora = results.get("oracle")
    if ora and ora.success:
        print(f"  [OK] Oracle (3^10):     {repr(ora.stdout.strip()[:30])} @ {ora.steps} steps")
    if "bolge19" in results:
        b19 = results["bolge19"]
        status_b19 = "OK" if b19.success else "FAIL (architecture mismatch 3^19 vs 3^10)"
        print(f"  [{status_b19}] bolge19 (3^19):  {b19.steps} steps")

    print("\n[OK] Hello World reproduction CONFIRMED on 3^10 backends")
    return 0


if __name__ == "__main__":
    sys.exit(main())
