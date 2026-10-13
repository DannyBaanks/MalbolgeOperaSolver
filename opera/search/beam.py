#!/usr/bin/env python3
"""
Beam Search / State-Space Synthesis for Malbolge Programs.

Synthesizes Malbolge programs for arbitrary target text outputs using
state-space search and trie pruning over normalized Malbolge opcodes.
Leverages malbolge_toolkit ProgramGenerator when available.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from opera.evaluator import UnifiedEvaluator, EvalResult, run_malbolge_reference


@dataclass
class SearchResult:
    """Result of a Malbolge search operation."""
    found: bool
    best_program: str = ""
    best_opcodes: str = ""
    target: str = ""
    iterations: int = 0
    elapsed_ms: float = 0.0
    steps: int = 0
    halted: bool = False
    stdout: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class BeamSearchEngine:
    """
    State-space synthesis engine for Malbolge programs.
    Generates exact programs for target strings.
    """

    def __init__(self, evaluator: Optional[UnifiedEvaluator] = None):
        self.evaluator = evaluator or UnifiedEvaluator()

    def search_for_string(
        self,
        target: str,
        opcode_choices: str = "op*",
        max_search_depth: int = 5,
        max_program_length: int = 59049,
    ) -> SearchResult:
        """Synthesize a Malbolge program that prints the exact target string."""
        t0 = time.perf_counter()

        try:
            from malbolge import GenerationConfig, ProgramGenerator
            cfg = GenerationConfig(
                opcode_choices=opcode_choices,
                max_search_depth=max_search_depth,
                max_program_length=max_program_length,
            )
            gen = ProgramGenerator()
            res = gen.generate_for_string(target, config=cfg)
            prog = res.malbolge_program

            # Verify in evaluator
            eval_res = self.evaluator.evaluate_reference(prog)
            elapsed = (time.perf_counter() - t0) * 1000

            return SearchResult(
                found=eval_res.stdout == target,
                best_program=prog,
                best_opcodes=res.opcodes,
                target=target,
                iterations=res.stats.get("evaluations", 0),
                elapsed_ms=elapsed,
                steps=eval_res.steps,
                halted=eval_res.halted,
                stdout=eval_res.stdout,
                metadata=res.stats,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return SearchResult(
                found=False,
                target=target,
                elapsed_ms=elapsed,
                metadata={"error": str(e)},
            )
