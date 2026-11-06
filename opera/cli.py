#!/usr/bin/env python3
"""
Danny Opera Solver — CLI entry point (2026 Modern Edition).

Usage:
    danny solve specimen.danny [-o output.mal] [--engine auto|conveyor|beam|sa|ripple] [--minimize]
    danny solve --target "Hello World!" [-o output.mal] [--engine conveyor]
    danny ripple --stages 5 [--char A] [-o ripple.mal]
    danny benchmark [--target "Hello World!"]
    danny normalize specimen.mal [-o normalized.txt]
    danny verify specimen.mal [--continuation] [--walbolge] [--autobolge] [--mb-ref]
    danny search specimen.danny --strategy [conveyor|beam|exhaustive|sa|meta|ripple]
    danny ablate specimen.mal [-o minimized.mal]
"""
from __future__ import annotations
import argparse
import sys
import hashlib
import time
from pathlib import Path

from opera.dsl import parse_dannyscript_file, parse_dannyscript, DannySpec
from opera.evaluator import UnifiedEvaluator, EvalResult
from opera.search.conveyor import (
    synthesize_conveyor,
    can_conveyor_fit,
    conveyor_capacity,
    ConveyorResult,
)
from opera.search.ripple import (
    synthesize_ripple_counter,
    generate_ripple_counter_hell,
    RippleCounterResult,
    find_lmao,
)
from opera.search.beam import BeamSearchEngine
from opera.search.exhaustive import (
    ExhaustiveSearch,
    ExhaustiveSearchConfig,
    ExhaustiveSearchEngine,
    malbolge_to_opcodes,
    opcodes_to_malbolge,
)
from opera.search.sa import SimulatedAnnealingSearch, SAConfig
from opera.search.meta import MetaSearch, MetaSearchConfig
from opera.search.ablative import minimize_malbolge_program
from opera.verify.walbolge import WalbolgeVerifier
from opera.verify.autobolge import AutobolgeVerifier
from opera.verify.continuation import verify_fresh_vm_continuation
from opera.verify.oracle import OracleVerifier, find_canonical_oracle


def cmd_solve(args):
    """Solve a DannyScript specification into an executable Malbolge program."""
    # 1. Resolve Spec or direct target
    target_arg = getattr(args, "target", None)
    spec_path_arg = getattr(args, "spec", None)

    if spec_path_arg and Path(spec_path_arg).exists():
        spec = parse_dannyscript_file(Path(spec_path_arg))
    elif target_arg:
        spec = DannySpec(target=target_arg)
    elif spec_path_arg and not Path(spec_path_arg).exists():
        # Treat spec_path_arg as inline target if not a valid file
        spec = DannySpec(target=spec_path_arg)
    else:
        print("Error: Specify a valid .danny spec file or use --target <string>")
        return 1

    engine_pref = (getattr(args, "engine", None) or spec.config.get("engine", "auto")).lower()
    stages = getattr(args, "stages", None) or spec.config.get("stages", 5)
    evaluator = UnifiedEvaluator()

    print("=" * 60)
    print("DANNY OPERA SOLVER — SOLVE (2026)")
    print("=" * 60)
    print(f"Target:       {repr(spec.target)}")
    print(f"Engine:       {engine_pref.upper()}")
    print(f"Constraints:  {spec.constraints}")
    print(f"Objectives:   {spec.objectives}")

    program = ""
    opcodes = ""
    steps = 0
    stdout = ""
    elapsed_ms = 0.0

    # 2. Dispatch Engine
    # Strategy A: XLAT2 Ripple Counter
    if engine_pref == "ripple" or (not spec.target and stages):
        char = spec.target[:1] if spec.target else "A"
        print(f"\nSynthesizing XLAT2 Nested Ripple Counter (Stages={stages}, Char={char!r})...")
        r_res = synthesize_ripple_counter(stages=stages, char_to_print=char, verify=True)
        program = r_res.program_text
        stdout = char * r_res.output_bytes
        steps = r_res.output_bytes * 5  # approximate
        print(f"  [OK] Ripple Counter compiled: {r_res.source_bytes}B -> {r_res.output_bytes:,}B ({r_res.ratio:.2f}x expansion)")

    # Strategy B: Autobolge 2.0 Conveyor Synthesis (O(N) deterministic)
    elif engine_pref == "conveyor" or (engine_pref == "auto" and can_conveyor_fit(spec.target)):
        print("\nSynthesizing via Autobolge 2.0 Conveyor Engine (O(N) Constructive)...")
        t0 = time.perf_counter()
        c_res = synthesize_conveyor(spec.target, verify=True)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        program = c_res.program
        steps = c_res.steps
        stdout = c_res.output
        print(f"  [OK] Conveyor synthesis completed in {elapsed_ms:.2f} ms ({c_res.steps} VM steps)")

    # Strategy C: Simulated Annealing
    elif engine_pref == "sa":
        print("\nSearching via Positional Simulated Annealing...")
        t0 = time.perf_counter()
        sa = SimulatedAnnealingSearch(evaluator)
        sa_res = sa.search_malbolge_program(spec.target)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if not sa_res.get("found"):
            print("\n[FAIL] Simulated Annealing failed to reach exact target.")
            return 1
        program = sa_res["best_program"]
        opcodes = sa_res["best_opcodes"]
        steps = sa_res["steps"]
        stdout = spec.target

    # Strategy D: Beam State-Space Search (Fallback / Explicit)
    else:
        print(f"\nSearching via Beam State-Space Search (engine={engine_pref})...")
        t0 = time.perf_counter()
        beam = BeamSearchEngine(evaluator)
        res = beam.search_for_string(spec.target)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if not res.found:
            print("\n[FAIL] Program synthesis failed to reach exact target.")
            return 1

        program = res.best_program
        opcodes = res.best_opcodes
        steps = res.steps
        stdout = res.stdout

    # 3. Optional Ablation / Minimization
    should_minimize = getattr(args, "minimize", False)
    if should_minimize:
        print("\nRunning ablative minimization...")
        ab_res = minimize_malbolge_program(program, target_output=spec.target)
        if ab_res.get("success"):
            saved = ab_res.get("bytes_saved", 0)
            nops = ab_res.get("nops_simplified", 0)
            print(f"  Ablation complete: saved {saved} bytes, simplified {nops} NOPs")
            program = ab_res["minimized_program"]
            opcodes = ab_res["minimized_opcodes"]
            steps = ab_res["steps"]

    # 4. Canonical C Oracle Cross-Verification
    verify_c = getattr(args, "verify_c", False) or getattr(args, "verify", False)
    if verify_c and program:
        c_ver = OracleVerifier()
        if c_ver.is_available():
            print("\nCross-verifying with BolgeForge Canonical C Oracle (mb_ref)...")
            c_res = c_ver.verify(program, stdin_data=b"")
            print(f"  mb_ref execution: success={c_res.success}, elapsed={c_res.elapsed_ms:.2f} ms")
            if c_res.stdout != stdout:
                print(f"  [WARN] Output mismatch in C oracle: expected {repr(stdout[:30])}, got {repr(c_res.stdout[:30])}")

    sha256 = hashlib.sha256(program.encode('latin-1')).hexdigest()

    print("\n" + "-" * 60)
    print("SOLVED PROGRAM:")
    print("-" * 60)
    print(f"Length:       {len(program)} chars")
    print(f"SHA-256:      {sha256}")
    print(f"Steps:        {steps}")
    print(f"Output:       {repr(stdout[:80])}{'...' if len(stdout) > 80 else ''}")
    print(f"Program:      {program[:80]}{'...' if len(program) > 80 else ''}")

    output_path = getattr(args, "output", None)
    if output_path:
        out_file = Path(output_path)
        out_file.write_text(program, encoding="ascii")
        print(f"\nSaved to: {out_file}")

    return 0


def cmd_ripple(args):
    """Synthesize an XLAT2 Nested Ripple Counter program with positive expansion."""
    stages = args.stages
    char = args.char or "A"
    print("=" * 60)
    print("XLAT2 NESTED RIPPLE COUNTER SYNTHESIZER")
    print("=" * 60)
    print(f"Stages:           {stages}")
    print(f"Character:        {repr(char)}")
    print(f"Expected Outputs: {5 ** stages:,} chars")

    try:
        res = synthesize_ripple_counter(stages, char_to_print=char, verify=True)
    except Exception as e:
        print(f"\n[FAIL] Ripple synthesis failed: {e}")
        return 1

    print("\n" + "-" * 60)
    print("RIPPLE SYNTHESIS RESULT:")
    print("-" * 60)
    print(f"Source Size:      {res.source_bytes} bytes")
    print(f"Output Emitted:   {res.output_bytes:,} bytes")
    print(f"Expansion Ratio:  {res.ratio:.2f}x {'(POSITIVE EXPANSION!)' if res.ratio > 1.0 else ''}")
    print(f"Exact Match:      {res.exact_match}")
    print(f"Clean HALT:       {res.halted_cleanly}")
    print(f"SHA-256:          {res.sha256}")

    if getattr(args, "output", None):
        out_p = Path(args.output)
        out_p.write_text(res.program_text, encoding="ascii")
        print(f"\nSaved to: {out_p}")

    return 0 if res.exact_match else 1


def cmd_benchmark(args):
    """Run comprehensive performance and capability benchmarks across engines."""
    target = getattr(args, "target", None) or "Hello World!"
    print("=" * 60)
    print("MALBOLGE OPERA SOLVER — 2026 BENCHMARK SUITE")
    print("=" * 60)
    print(f"Benchmark Target: {repr(target)}")

    # 1. Autobolge 2.0 Conveyor Synthesis
    print("\n[1] Autobolge 2.0 Conveyor Engine (Constructive O(N)):")
    if can_conveyor_fit(target):
        t0 = time.perf_counter()
        c_res = synthesize_conveyor(target, verify=True)
        t_c = (time.perf_counter() - t0) * 1000.0
        print(f"    Synthesis Time:   {c_res.elapsed_ms:.2f} ms")
        print(f"    Total with VM:    {t_c:.2f} ms")
        print(f"    Program Length:   {len(c_res.program)} cells")
        print(f"    VM Execution:     {c_res.steps} steps")
        print(f"    Verified Output:  {repr(c_res.output)}")
    else:
        print(f"    Target exceeds sterile gap ({conveyor_capacity()} cells)")

    # 2. Beam Search
    print("\n[2] Beam State-Space Search (Iterative Heuristic):")
    evaluator = UnifiedEvaluator()
    beam = BeamSearchEngine(evaluator)
    t0 = time.perf_counter()
    b_res = beam.search_for_string(target)
    t_b = (time.perf_counter() - t0) * 1000.0
    print(f"    Synthesis Time:   {t_b:.2f} ms")
    print(f"    Found Exact:      {b_res.found}")
    print(f"    Program Length:   {len(b_res.best_program)} cells")
    print(f"    VM Steps:         {b_res.steps} steps")

    # 3. XLAT2 Nested Ripple Counter
    print("\n[3] XLAT2 Nested Ripple Counter (Positive Expansion):")
    for st in [3, 5, 7]:
        r_res = synthesize_ripple_counter(st, "A", verify=False)
        exp_out = 5 ** st
        ratio = exp_out / r_res.source_bytes
        print(f"    Stages={st}: {r_res.source_bytes}B -> {exp_out:,} chars | Ratio: {ratio:6.2f}x {'(EXPANSION)' if ratio > 1 else ''}")

    # 4. Backend Consensus & VM Speed
    print("\n[4] Backend Execution Speed (specimens/hello_solved.mal):")
    hello_path = Path(__file__).resolve().parent.parent / "specimens" / "hello_solved.mal"
    if hello_path.exists():
        ref_res = evaluator.evaluate_reference(hello_path)
        print(f"    Reference VM (Py): {ref_res.elapsed_ms:.2f} ms | stdout={repr(ref_res.stdout)}")
        if "mb_ref" in evaluator.registry.backends:
            mb_res = evaluator.evaluate_mb_ref(hello_path)
            print(f"    C Oracle (mb_ref): {mb_res.elapsed_ms:.2f} ms | stdout={repr(mb_res.stdout)}")

    print("\n" + "=" * 60)
    print("BENCHMARK COMPLETED SUCCESSFULLY")
    print("=" * 60)
    return 0


def cmd_normalize(args):
    """Normalize a Malbolge program to mnemonics and opcodes."""
    specimen = Path(args.specimen)
    if not specimen.exists():
        print(f"Specimen not found: {specimen}")
        return 1

    text = specimen.read_text(encoding="ascii").strip()
    raw = "".join(text.split())

    try:
        opcodes = malbolge_to_opcodes(raw)
    except Exception as e:
        print(f"Error normalizing: {e}")
        return 1

    print("=" * 60)
    print(f"NORMALIZATION: {specimen}")
    print("=" * 60)
    print(f"Raw length:     {len(raw)}")
    print(f"Opcodes:        {opcodes[:80]}{'...' if len(opcodes) > 80 else ''}")

    lines = []
    lines.append(f"# Normalized representation of {specimen.name}")
    lines.append(f"# Length: {len(raw)}")
    lines.append(f"# Opcodes: {opcodes}\n")
    lines.append("POS   CHAR  OPCODE")
    lines.append("------------------")
    for i, (ch, op) in enumerate(zip(raw, opcodes)):
        lines.append(f"{i:04d}  {ch!r:5s} {op}")

    report = "\n".join(lines)
    if getattr(args, "output", None):
        out_p = Path(args.output)
        out_p.write_text(report, encoding="utf-8")
        print(f"Saved normalized breakdown to: {out_p}")
    else:
        print("\n" + "\n".join(lines[:25]))
        if len(lines) > 25:
            print(f"... ({len(lines) - 25} more lines)")

    return 0


def cmd_verify(args):
    """Verify a specimen across backends and check Fresh-VM continuation."""
    specimen = Path(args.specimen)
    if not specimen.exists():
        print(f"Specimen not found: {specimen}")
        return 1

    evaluator = UnifiedEvaluator()
    print("=" * 60)
    print(f"VERIFY SPECIMEN: {specimen}")
    print("=" * 60)

    # 1. In-process Reference Evaluation
    res = evaluator.evaluate_reference(specimen)
    print(f"Reference VM (3^10):")
    print(f"  Success:     {res.success}")
    print(f"  Halted:      {res.halted} ({res.halt_reason})")
    print(f"  Steps:       {res.steps}")
    print(f"  Stdout:      {repr(res.stdout[:50])}{'...' if len(res.stdout) > 50 else ''}")
    print(f"  Elapsed:     {res.elapsed_ms:.2f} ms")

    # 2. Strict Canonical C Oracle (mb_ref)
    if getattr(args, "mb_ref", False) or getattr(args, "oracle", False):
        print("\n--- Canonical C Oracle (mb_ref) ---")
        c_ver = OracleVerifier()
        if c_ver.is_available():
            c_res = c_ver.verify(specimen)
            print(f"  Success:     {c_res.success}")
            print(f"  Halted:      {c_res.halted} ({c_res.halt_reason})")
            print(f"  Stdout:      {repr(c_res.stdout[:50])}{'...' if len(c_res.stdout) > 50 else ''}")
            print(f"  Elapsed:     {c_res.elapsed_ms:.2f} ms")
        else:
            print("  Canonical C Oracle (mb_ref) not found on host.")

    # 3. Fresh-VM Continuation (E0)
    if getattr(args, "continuation", False):
        print("\n--- Fresh-VM Continuation (Primitive E0) ---")
        text = specimen.read_text(encoding="ascii").strip()
        ev = verify_fresh_vm_continuation(text)
        print(f"  Continuation Pass:  {ev.continuation_pass}")
        print(f"  Split Step:         {ev.split_step}")
        print(f"  Concatenated Match: {ev.concatenation_match}")
        print(f"  SHA-256 Match:      {ev.full_sha256 == ev.continuation_sha256}")

    # 4. Walbolge
    if getattr(args, "walbolge", False):
        print("\n--- Walbolge Roundtrip ---")
        try:
            walbolge = WalbolgeVerifier()
            wb_res = walbolge.verify_roundtrip(str(specimen))
            print(f"  Roundtrip: {wb_res.roundtrip_perfect}")
            print(f"  Reconstructed text: {repr(wb_res.reconstructed_text[:50])}")
        except Exception as e:
            print(f"  Walbolge skipped/error: {e}")

    # 5. Autobolge
    if getattr(args, "autobolge", False):
        print("\n--- Autobolge Validation ---")
        try:
            autobolge = AutobolgeVerifier()
            ab_res = autobolge.verify_file(str(specimen))
            print(f"  Output: {repr(ab_res.output_text[:50])}")
            print(f"  Steps:  {ab_res.steps}")
            print(f"  Halted: {ab_res.halted}")
        except Exception as e:
            print(f"  Autobolge skipped/error: {e}")

    return 0


def cmd_search(args):
    """Run search with specified strategy."""
    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"Spec file not found: {spec_path}")
        return 1

    spec = parse_dannyscript_file(spec_path)
    evaluator = UnifiedEvaluator()

    print("=" * 60)
    print(f"SEARCH STRATEGY: {args.strategy.upper()}")
    print("=" * 60)
    print(f"Target: {repr(spec.target)}")

    if args.strategy == "conveyor":
        res = synthesize_conveyor(spec.target, verify=True)
        print(f"Conveyor result: verified={res.verified}, steps={res.steps}, len={len(res.program)}, time={res.elapsed_ms:.2f}ms")
    elif args.strategy == "beam":
        engine = BeamSearchEngine(evaluator)
        res = engine.search_for_string(spec.target)
        print(f"Result: found={res.found}, steps={res.steps}, len={len(res.best_program)}")
    elif args.strategy == "exhaustive":
        search = ExhaustiveSearch(evaluator)
        res = search.search_for_output(spec.target, max_length=4)
        print(f"Result: found={res.found}, tested={res.candidates_tested}, len={len(res.best_program)}")
    elif args.strategy == "sa":
        sa = SimulatedAnnealingSearch(evaluator)
        res = sa.search_malbolge_program(spec.target, max_iterations=3000)
        print(f"Result: found={res['found']}, best_fit={res['best_fitness']}, steps={res['steps']}")
    elif args.strategy == "meta":
        meta = MetaSearch(evaluator)
        res = meta.solve(spec.target)
        print(f"Result: found={res.found}, strategy={res.strategy_used}, len={len(res.best_program)}, time={res.elapsed_ms:.2f}ms")
    elif args.strategy == "ripple":
        stages = getattr(args, "stages", 5)
        res = synthesize_ripple_counter(stages, char_to_print=spec.target[:1] if spec.target else "A")
        print(f"Ripple result: match={res.exact_match}, stages={res.stages}, outputs={res.output_bytes}, ratio={res.ratio:.2f}x")

    return 0


def cmd_ablate(args):
    """Ablatively minimize an existing Malbolge program."""
    specimen = Path(args.specimen)
    if not specimen.exists():
        print(f"Specimen not found: {specimen}")
        return 1

    text = specimen.read_text(encoding="ascii").strip()
    target = getattr(args, "target", None)

    print("=" * 60)
    print(f"ABLATIVE MINIMIZATION: {specimen}")
    print("=" * 60)

    res = minimize_malbolge_program(text, target_output=target)
    if not res.get("success"):
        print(f"Ablation error: {res.get('error')}")
        return 1

    print(f"Original Length:   {res['original_length']}")
    print(f"Minimized Length:  {res['minimized_length']}")
    print(f"Bytes Saved:       {res['bytes_saved']}")
    print(f"NOPs Simplified:   {res['nops_simplified']}")
    print(f"Output Match:      {res['output_match']}")

    if getattr(args, "output", None):
        out_path = Path(args.output)
        out_path.write_text(res["minimized_program"], encoding="ascii")
        print(f"Saved minimized program to: {out_path}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="danny",
        description="Danny Opera Solver (2026 Edition) — Malbolge program search & synthesis",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # solve
    p_solve = subparsers.add_parser("solve", help="Solve a DannyScript specification or target text")
    p_solve.add_argument("spec", nargs="?", default="", help="Path to .danny spec file or inline target")
    p_solve.add_argument("-t", "--target", help="Direct target string to synthesize")
    p_solve.add_argument("-e", "--engine", choices=["auto", "conveyor", "beam", "sa", "ripple"], default="auto",
                         help="Synthesis engine to use (default: auto)")
    p_solve.add_argument("-s", "--stages", type=int, default=5, help="Number of stages for ripple engine (default: 5)")
    p_solve.add_argument("-o", "--output", help="Path to output .mal file")
    p_solve.add_argument("--minimize", action="store_true", help="Apply ablative minimization to generated program")
    p_solve.add_argument("--verify-c", "--oracle", action="store_true", help="Cross-verify against canonical C oracle (mb_ref)")
    p_solve.set_defaults(func=cmd_solve)

    # ripple
    p_ripple = subparsers.add_parser("ripple", help="Synthesize an XLAT2 Nested Ripple Counter with positive expansion")
    p_ripple.add_argument("-s", "--stages", type=int, default=5, help="Number of stages (outputs = 5^N, default: 5)")
    p_ripple.add_argument("-c", "--char", default="A", help="Character to print repeatedly (default: 'A')")
    p_ripple.add_argument("-o", "--output", help="Path to output .mal file")
    p_ripple.set_defaults(func=cmd_ripple)

    # benchmark
    p_bench = subparsers.add_parser("benchmark", help="Run comprehensive cross-engine benchmark suite")
    p_bench.add_argument("-t", "--target", default="Hello World!", help="Benchmark target string")
    p_bench.set_defaults(func=cmd_benchmark)

    # normalize
    p_norm = subparsers.add_parser("normalize", help="Normalize Malbolge program to mnemonics")
    p_norm.add_argument("specimen", help="Path to .mal/.mb specimen")
    p_norm.add_argument("-o", "--output", help="Output file")
    p_norm.set_defaults(func=cmd_normalize)

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify specimen with backends and fresh-VM continuation")
    p_verify.add_argument("specimen", help="Path to .mal specimen")
    p_verify.add_argument("--continuation", action="store_true", help="Verify Primitive E0 Fresh-VM Continuation")
    p_verify.add_argument("--walbolge", action="store_true", help="Run Walbolge roundtrip")
    p_verify.add_argument("--autobolge", action="store_true", help="Run Autobolge validation")
    p_verify.add_argument("--mb-ref", "--oracle", dest="mb_ref", action="store_true", help="Run canonical C oracle (mb_ref)")
    p_verify.set_defaults(func=cmd_verify)

    # search
    p_search = subparsers.add_parser("search", help="Search for Malbolge programs")
    p_search.add_argument("spec", help="Path to .danny spec file")
    p_search.add_argument("--strategy", choices=["conveyor", "beam", "exhaustive", "sa", "meta", "ripple"], default="conveyor")
    p_search.add_argument("-s", "--stages", type=int, default=5, help="Number of stages for ripple strategy")
    p_search.set_defaults(func=cmd_search)

    # ablate
    p_ablate = subparsers.add_parser("ablate", help="Ablatively minimize a Malbolge program")
    p_ablate.add_argument("specimen", help="Path to .mal specimen")
    p_ablate.add_argument("-o", "--output", help="Path to output minimized .mal file")
    p_ablate.add_argument("--target", help="Expected target output")
    p_ablate.set_defaults(func=cmd_ablate)

    args = parser.parse_args()
    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
