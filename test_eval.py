#!/usr/bin/env python3
"""Test the evaluator with real backends."""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from opera.evaluator import UnifiedEvaluator


def main():
    evaluator = UnifiedEvaluator()
    print("Backends:", evaluator.registry.list_backends())

    # Auto-detect specimen
    candidates = [
        Path("specimens/hello_solved.mal"),
        Path("/home/danny/Development/ISyCo Git/malbolge-lisp-forensics/specimens/hello.malbolge"),
    ]
    forensics = os.environ.get("OPERA_FORENSICS_DIR")
    if forensics:
        candidates.insert(0, Path(forensics) / "specimens" / "hello.malbolge")

    specimen = None
    for cand in candidates:
        if cand.exists():
            specimen = cand
            break

    if specimen:
        print(f"\nTesting with {specimen}")
        results = evaluator.evaluate_all(specimen)

        for name, result in sorted(results.items()):
            print(f"\n  {name}:")
            print(f"  success: {result.success}")
            print(f"  returncode: {result.returncode}")
            print(f"  stdout: {result.stdout[:100] if result.stdout else '(empty)'}")
            print(f"  stderr: {result.stderr[:100] if result.stderr else '(empty)'}")
            print(f"  steps: {result.steps}")
            print(f"  halted: {result.halted}")
            print(f"  halt_reason: {result.halt_reason}")
            print(f"  elapsed_ms: {result.elapsed_ms:.2f} ms")
            print(f"  backend: {result.backend}")


if __name__ == "__main__":
    main()
