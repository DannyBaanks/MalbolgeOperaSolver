#!/usr/bin/env python3
"""Test the evaluator with all backends."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from opera.evaluator import UnifiedEvaluator

def main():
    evaluator = UnifiedEvaluator()
    print("Backends:", evaluator.registry.list_backends())

    # Test hello.malbolge (from the malbolge-lisp-forensics repo)
    forensics = os.environ.get("OPERA_FORENSICS_DIR")
    if not forensics:
        print("Set OPERA_FORENSICS_DIR to the malbolge-lisp-forensics repo "
              "to run this demo")
        return
    specimen = Path(forensics) / "specimens" / "hello.malbolge"
    results = evaluator.evaluate_all(specimen)
    
    for name, result in results.items():
        print(f"\n{name}:")
        print(f"  success: {result.success}")
        print(f"  rc: {result.returncode}")
        print(f"  stdout: {repr(result.stdout[:50])}")
        print(f"  steps: {result.steps}")
        print(f"  halted: {result.halted}")
        print(f"  reason: {result.halt_reason}")

if __name__ == "__main__":
    main()
