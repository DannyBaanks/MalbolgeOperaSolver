#!/usr/bin/env python3
"""Test all backends with quijote specimen."""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from opera.evaluator import UnifiedEvaluator


def find_quijote_specimen() -> Path:
    candidates = [
        Path("/home/danny/Development/ISyCo Git/Malbolge-Translator/artifacts/quijote/chapter_001/quijote_ch001_full.mal"),
        Path(__file__).parent / "specimens" / "quijote" / "chapter_001" / "quijote_ch001_full.mal",
    ]
    forensics = os.environ.get("OPERA_FORENSICS_DIR")
    if forensics:
        candidates.insert(0, Path(forensics) / "specimens" / "quijote" / "chapter_001" / "quijote_ch001_full.mal")

    for cand in candidates:
        if cand.exists():
            return cand
    return candidates[0]


def main():
    evaluator = UnifiedEvaluator()
    specimen = find_quijote_specimen()

    print(f"Testing with: {specimen}")
    print(f"Exists: {specimen.exists()}")

    if not specimen.exists():
        print("Quijote specimen not found.")
        return 1

    results = evaluator.evaluate_all(specimen)

    for name, result in sorted(results.items()):
        print(f"\n  {name}:")
        print(f"  success: {result.success}")
        print(f"  returncode: {result.returncode}")
        stdout_preview = repr(result.stdout[:80]) if result.stdout else "(empty)"
        print(f"  stdout: {stdout_preview}")
        print(f"  steps: {result.steps}")
        print(f"  halted: {result.halted}")
        print(f"  halt_reason: {result.halt_reason}")


if __name__ == "__main__":
    main()
