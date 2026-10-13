#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fast SA & Beam Search for Hello World."""

import sys
import time
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from opera.evaluator import UnifiedEvaluator
from opera.search.sa import SimulatedAnnealingSearch, SAConfig
from opera.search.beam import BeamSearchEngine
from opera.search.ablative import minimize_malbolge_program


def find_or_create_specimen() -> Path:
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

    out_dir = Path(__file__).parent / "specimens"
    out_dir.mkdir(parents=True, exist_ok=True)
    target_path = out_dir / "hello_solved.mal"
    engine = BeamSearchEngine()
    res = engine.search_for_string("Hello World!")
    target_path.write_text(res.best_program, encoding="ascii")
    return target_path


def main():
    print("=" * 60)
    print("FAST MALBOLGE SEARCH & ANNEALING — HELLO WORLD")
    print("=" * 60)

    evaluator = UnifiedEvaluator()
    print("Available backends:", list(evaluator.registry.backends.keys()))

    # 1. Baseline verification with specimen
    specimen = find_or_create_specimen()
    print(f"\n[1] Verifying baseline specimen: {specimen}")
    results = evaluator.evaluate_all(specimen)
    for n, v in sorted(results.items()):
        print(f"  {n:15s}: ok={v.success}, steps={v.steps}, out={repr(v.stdout[:30] if v.stdout else '')}")

    # 2. Fast Positional SA Search (50 iterations in-process)
    print("\n[2] Running in-process Positional Opcode Annealing (50 iterations)...")
    sa_engine = SimulatedAnnealingSearch(evaluator, SAConfig(initial_temp=5.0, cooling_rate=0.995))
    sa_res = sa_engine.search_malbolge_program(target_output="Hello", initial_length=24, max_iterations=50)
    print(f"  SA completed in {sa_res['elapsed_sec']:.3f}s")
    print(f"  Iterations: {sa_res['iterations']}, Best fitness: {sa_res['best_fitness']:.1f}")
    print(f"  Output observed: {repr(sa_res['stdout'])}")

    # 3. Exact State-Space Beam Synthesis
    print("\n[3] Synthesizing exact 'Hello World!' via State-Space Beam Search...")
    t0 = time.time()
    beam = BeamSearchEngine(evaluator)
    beam_res = beam.search_for_string("Hello World!")
    print(f"  Beam search finished in {time.time() - t0:.3f}s: found={beam_res.found}")
    print(f"  Program length: {len(beam_res.best_program)} chars, steps: {beam_res.steps}")
    print(f"  Output: {repr(beam_res.stdout)}")

    # 4. Ablative Minimization
    print("\n[4] Running Ablative Minimization on synthesized program...")
    ab_res = minimize_malbolge_program(beam_res.best_program, target_output="Hello World!")
    if ab_res.get("success"):
        print(f"  Ablation complete: NOPs simplified={ab_res['nops_simplified']}, output_match={ab_res['output_match']}")

    print("\n" + "=" * 60)
    print("MALBOLGE OPERA SOLVER PIPELINE COMPLETE")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
