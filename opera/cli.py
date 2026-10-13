#!/usr/bin/env python3
"""
Danny Opera Solver — CLI entry point.

Usage:
    danny solve specimen.danny [-o output.mal] [--minimize]
    danny normalize specimen.mal [-o normalized.txt]
    danny verify specimen.mal [--continuation] [--walbolge] [--autobolge]
    danny search specimen.danny --strategy [beam|exhaustive|sa|meta]
    danny ablate specimen.mal [-o minimized.mal]
"""
from __future__ import annotations
import argparse
import sys
import hashlib
from pathlib import Path

from opera.dsl import parse_dannyscript_file, DannySpec
from opera.evaluator import UnifiedEvaluator, EvalResult
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


def cmd_solve(args):
    """Solve a DannyScript specification into an executable Malbolge program."""
    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"Error: Spec file not found: {spec_path}")
        return 1

    spec = parse_dannyscript_file(spec_path)
    evaluator = UnifiedEvaluator()

    print("=" * 60)
    print("DANNY OPERA SOLVER — SOLVE")
    print("=" * 60)
    print(f"Target:       {repr(spec.target)}")
    print(f"Constraints:  {spec.constraints}")
    print(f"Objectives:   {spec.objectives}")

    # Solve using Beam Search
    beam = BeamSearchEngine(evaluator)
    res = beam.search_for_string(spec.target)

    if not res.found:
        print("\n[FAIL] Program synthesis failed to reach exact target.")
        return 1

    program = res.best_program
    opcodes = res.best_opcodes
    steps = res.steps
    stdout = res.stdout

    # Optional ablation / minimization
    should_minimize = getattr(args, "minimize", False) or any(
        obj[1] == "size" and obj[0] == "minimize" for obj in spec.objectives
    )
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

    sha256 = hashlib.sha256(program.encode('ascii')).hexdigest()

    print("\n" + "-" * 60)
    print("SOLVED PROGRAM:")
    print("-" * 60)
    print(f"Length:       {len(program)} chars")
    print(f"SHA-256:      {sha256}")
    print(f"Steps:        {steps}")
    print(f"Output:       {repr(stdout)}")
    print(f"Program:      {program[:80]}{'...' if len(program) > 80 else ''}")

    output_path = getattr(args, "output", None)
    if output_path:
        out_file = Path(output_path)
        out_file.write_text(program, encoding="ascii")
        print(f"\nSaved to: {out_file}")

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

    # 2. Fresh-VM Continuation (E0)
    if getattr(args, "continuation", False):
        print("\n--- Fresh-VM Continuation (Primitive E0) ---")
        text = specimen.read_text(encoding="ascii").strip()
        ev = verify_fresh_vm_continuation(text)
        print(f"  Continuation Pass:  {ev.continuation_pass}")
        print(f"  Split Step:         {ev.split_step}")
        print(f"  Concatenated Match: {ev.concatenation_match}")
        print(f"  SHA-256 Match:      {ev.full_sha256 == ev.continuation_sha256}")

    # 3. Walbolge
    if getattr(args, "walbolge", False):
        print("\n--- Walbolge Roundtrip ---")
        try:
            walbolge = WalbolgeVerifier()
            wb_res = walbolge.verify_roundtrip(str(specimen))
            print(f"  Roundtrip: {wb_res.roundtrip_perfect}")
            print(f"  Reconstructed text: {repr(wb_res.reconstructed_text[:50])}")
        except Exception as e:
            print(f"  Walbolge skipped/error: {e}")

    # 4. Autobolge
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

    if args.strategy == "beam":
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
        print(f"Result: found={res.found}, strategy={res.strategy_used}, len={len(res.best_program)}")

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
        description="Danny Opera Solver — Malbolge program search & verification",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # solve
    p_solve = subparsers.add_parser("solve", help="Solve a DannyScript specification")
    p_solve.add_argument("spec", help="Path to .danny spec file")
    p_solve.add_argument("-o", "--output", help="Path to output .mal file")
    p_solve.add_argument("--minimize", action="store_true", help="Apply ablative minimization to generated program")
    p_solve.set_defaults(func=cmd_solve)

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
    p_verify.set_defaults(func=cmd_verify)

    # search
    p_search = subparsers.add_parser("search", help="Search for Malbolge programs")
    p_search.add_argument("spec", help="Path to .danny spec file")
    p_search.add_argument("--strategy", choices=["beam", "exhaustive", "sa", "meta"], default="beam")
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
