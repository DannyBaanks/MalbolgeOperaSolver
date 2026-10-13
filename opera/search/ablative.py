#!/usr/bin/env python3
"""
Ablative Minimization — Iterative reduction to minimal form.

Provides:
1. Malbolge program ablative reduction: trims dead instructions after halt,
   simplifies non-essential opcodes to NOPs ('o'), and verifies output preservation.
2. Component ablation for signature / candidate dictionaries.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional, Callable, Set, FrozenSet
from dataclasses import dataclass
import random
import time

from opera.evaluator import UnifiedEvaluator, EvalResult, run_malbolge_reference
from opera.search.exhaustive import opcodes_to_malbolge, malbolge_to_opcodes


@dataclass
class AblativeConfig:
    """Configuration for ablative minimization."""
    max_passes: int = 10
    shuffle_order: bool = True
    early_stop: bool = True
    min_improvement: float = 0.0


@dataclass
class AblationResult:
    """Result of ablative minimization."""
    original: Any
    minimized: Any
    removed: int
    passes: int
    fitness_before: float
    fitness_after: float
    history: List[Dict] = None


class AblativeMinimizer:
    """
    Ablative minimization engine for reducing solutions to minimal form.
    """

    def __init__(self, fitness_fn: Optional[Callable] = None, config: Optional[AblativeConfig] = None):
        self.fitness_fn = fitness_fn or (lambda x: 0.0)
        self.config = config or AblativeConfig()
        self.rng = random.Random(42)

    def minimize(self, candidate: Dict, fitness_fn: Callable) -> Dict[str, Any]:
        """
        Perform ablative minimization on candidate signatures or components.
        """
        current_fitness = fitness_fn(candidate)
        current = {
            'birth': list(candidate.get('birth', [])),
            'survival': list(candidate.get('survival', [])),
            'live_sigs': set(candidate.get('live_sigs', [])),
        }

        passes = 0
        changed = True
        history = []

        while passes < self.config.max_passes and changed:
            changed = False
            passes += 1

            active = list(current['live_sigs'])
            if self.config.shuffle_order:
                self.rng.shuffle(active)

            for sig in active:
                test_live = current['live_sigs'] - {sig}
                test_candidate = {
                    'live_sigs': test_live,
                    'birth': [s for s in current['birth'] if s in test_live],
                    'survival': [s for s in current['survival'] if s in test_live],
                }

                test_fitness = fitness_fn(test_candidate)

                if test_fitness <= current_fitness + self.config.min_improvement:
                    current['live_sigs'] = test_live
                    current['birth'] = [s for s in current['birth'] if s in test_live]
                    current['survival'] = [s for s in current['survival'] if s in test_live]
                    changed = True

                    history.append({
                        'pass': passes,
                        'removed': sig,
                        'fitness_before': current_fitness,
                        'fitness_after': test_fitness,
                    })
                    current_fitness = test_fitness

        initial_len = len(candidate.get('live_sigs', []))
        final_len = len(current['live_sigs'])

        return {
            'minimized': {
                'birth': sorted(current['birth']),
                'survival': sorted(current['survival']),
                'live_sigs': sorted(current['live_sigs']),
            },
            'removed_count': initial_len - final_len,
            'passes': passes,
            'history': history,
        }

    def minimize_malbolge_program(
        self,
        source: str,
        target_output: Optional[str] = None,
        max_steps: int = 1_000_000,
    ) -> Dict[str, Any]:
        """
        Ablatively minimize a real Malbolge program:
        1. Evaluates baseline run (capturing stdout and halt step).
        2. Trims code after the halt instruction 'v'.
        3. Tries replacing candidate opcodes with NOP ('o') one-by-one,
           verifying that output and termination are 100% preserved.
        """
        evaluator = UnifiedEvaluator()
        baseline = evaluator.evaluate_reference(source, max_steps=max_steps)
        if not baseline.halted:
            return {
                "success": False,
                "error": "Cannot minimize non-halting program",
                "original_program": source,
                "minimized_program": source,
            }

        expected_out = target_output if target_output is not None else baseline.stdout
        raw_clean = "".join(source.split())

        try:
            opcodes = malbolge_to_opcodes(raw_clean)
        except Exception:
            return {
                "success": False,
                "error": "Failed to decode opcodes",
                "original_program": source,
                "minimized_program": source,
            }

        op_list = list(opcodes)
        initial_length = len(op_list)

        # Step 1: Trim instructions after the first 'v' (halt)
        if 'v' in op_list:
            halt_idx = op_list.index('v')
            # Test if trimming up to halt_idx + 1 works
            trimmed_ops = op_list[:halt_idx + 1]
            trimmed_prog = opcodes_to_malbolge("".join(trimmed_ops))
            res = evaluator.evaluate_reference(trimmed_prog, max_steps=max_steps)
            if res.halted and res.stdout == expected_out:
                op_list = trimmed_ops

        # Step 2: Pass through opcodes, attempting NOP simplification
        nop_simplified = 0
        for i in range(len(op_list)):
            if op_list[i] in ('v', 'o'):
                continue
            orig_op = op_list[i]
            op_list[i] = 'o'  # try NOP
            candidate_prog = opcodes_to_malbolge("".join(op_list))
            res = evaluator.evaluate_reference(candidate_prog, max_steps=max_steps)
            if res.halted and res.stdout == expected_out:
                nop_simplified += 1
            else:
                op_list[i] = orig_op  # revert

        minimized_opcodes = "".join(op_list)
        minimized_prog = opcodes_to_malbolge(minimized_opcodes)
        final_eval = evaluator.evaluate_reference(minimized_prog, max_steps=max_steps)

        return {
            "success": True,
            "original_length": initial_length,
            "minimized_length": len(minimized_opcodes),
            "bytes_saved": initial_length - len(minimized_opcodes),
            "nops_simplified": nop_simplified,
            "original_program": raw_clean,
            "minimized_program": minimized_prog,
            "minimized_opcodes": minimized_opcodes,
            "output_match": final_eval.stdout == expected_out,
            "stdout": final_eval.stdout,
            "steps": final_eval.steps,
        }


def ablative_minimize(
    candidate: Dict, fitness_fn: Callable, max_passes: int = 10
) -> Dict[str, Any]:
    """Convenience function for ablative minimization."""
    cfg = AblativeConfig(max_passes=max_passes)
    minimizer = AblativeMinimizer(fitness_fn=fitness_fn, config=cfg)
    return minimizer.minimize(candidate, fitness_fn)


def minimize_malbolge_program(
    source: str, target_output: Optional[str] = None
) -> Dict[str, Any]:
    """Convenience function to minimize a Malbolge program."""
    minimizer = AblativeMinimizer()
    return minimizer.minimize_malbolge_program(source, target_output=target_output)