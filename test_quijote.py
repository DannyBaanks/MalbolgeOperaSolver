#!/usr/bin/env python3
"""Test all backends with quijote specimen."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from opera.evaluator import UnifiedEvaluator

def main():
    evaluator = UnifiedEvaluator()

    forensics = os.environ.get("OPERA_FORENSICS_DIR")
    if not forensics:
        print("Set OPERA_FORENSICS_DIR to the malbolge-lisp-forensics repo "
              "to run this demo")
        return
    specimen = (Path(forensics) / "specimens" / "quijote" / "chapter_001"
                / "quijote_ch001_full.mal")
    print(f"Testing with: {specimen}")
    print(f"Exists: {specimen.exists()}")

    results = evaluator.evaluate_all(specimen)
    
    for name, result in results.items():
        print(f"\n  {name}:")
        print(f"  success: {result.success}")
        print(f"  returncode: {result.returncode}")
        stdout_preview = result.stdout[:80] if result.stdout else "(empty)"
        print(f"  stdout: {stdout_preview}")
        print(f"  steps: {result.steps}")
        print(f"  halted: {result.halted}")
        print(f"  halt_reason: {result.halt_reason}")

if __name__ == "__main__":
    main()
