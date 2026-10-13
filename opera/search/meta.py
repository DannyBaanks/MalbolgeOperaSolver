#!/usr/bin/env python3
"""
Meta Search — Strategy selection and multi-axis Malbolge search orchestration.

Coordinates multiple search strategies:
- Beam / State-Space Search for exact string targets.
- Exhaustive Opcode Search for small functional gadgets.
- Positional Simulated Annealing for stochastic optimization.
- Ablative Minimization for post-processing and compaction.
"""
from __future__ import annotations
import time
from typing import Iterator, List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from opera.evaluator import UnifiedEvaluator, EvalResult
from opera.search.beam import BeamSearchEngine
from opera.search.exhaustive import ExhaustiveSearch, ExhaustiveSearchConfig
from opera.search.sa import SimulatedAnnealingSearch, SAConfig
from opera.search.ablative import AblativeMinimizer


@dataclass
class MetaSearchConfig:
    """Configuration for Meta search."""
    max_birth_signatures: int = 2
    max_survival_signatures: int = 1
    max_combinations: Optional[int] = None
    single_bit_masks: Tuple[int, ...] = (1, 2, 4, 8, 16, 32, 64, 128)
    strategy_preference: str = "auto"  # 'auto', 'beam', 'exhaustive', 'sa'


@dataclass
class MetaSearchResult:
    """Result of a meta search."""
    found: bool = False
    best_candidate: Optional[Dict[str, Any]] = None
    best_program: str = ""
    best_opcodes: str = ""
    best_fitness: float = float('inf')
    strategy_used: str = ""
    tested: int = 0
    elapsed_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class MetaSearch:
    """
    Meta Search coordinator.
    Analyzes objectives and routes to the most effective Malbolge synthesis strategy.
    """

    def __init__(
        self,
        evaluator: Optional[UnifiedEvaluator] = None,
        fitness_fn: Optional[Any] = None,
        config: Optional[MetaSearchConfig] = None,
    ):
        self.evaluator = evaluator or UnifiedEvaluator()
        self.fitness_fn = fitness_fn
        self.config = config or MetaSearchConfig()

    def search_oriented_pairs(self) -> Iterator[Dict[str, Any]]:
        """
        Multi-axis functional search:
        Explores canonical axes in Malbolge instruction space.
        Maintains backward compatibility with axis and live_sigs interface.
        """
        axes = [
            ("X", [1, 2]),
            ("Y", [4, 8]),
            ("Z", [16, 32]),
            ("T", [64, 128]),
        ]
        for axis_name, sigs in axes:
            yield {
                "axis": axis_name,
                "live_sigs": sigs,
                "seed": [(0, 0, 0, 0)],
                "k": 1,
            }

    def solve(self, target: str) -> MetaSearchResult:
        """
        Automatically select and execute the best search strategy for a target.
        """
        t0 = time.perf_counter()

        # For text targets, BeamSearchEngine produces byte-exact verified programs
        beam_engine = BeamSearchEngine(self.evaluator)
        res = beam_engine.search_for_string(target)

        elapsed = (time.perf_counter() - t0) * 1000

        if res.found:
            return MetaSearchResult(
                found=True,
                best_program=res.best_program,
                best_opcodes=res.best_opcodes,
                best_fitness=0.0,
                strategy_used="beam_state_space",
                tested=res.iterations,
                elapsed_ms=elapsed,
                metadata=res.metadata,
            )

        # Fallback to exhaustive opcode search for very short targets
        if len(target) <= 2:
            ex_search = ExhaustiveSearch(self.evaluator)
            ex_res = ex_search.search_for_output(target, max_length=4)
            if ex_res.found:
                return MetaSearchResult(
                    found=True,
                    best_program=ex_res.best_program,
                    best_opcodes=ex_res.best_opcodes,
                    best_fitness=0.0,
                    strategy_used="exhaustive_opcode",
                    tested=ex_res.candidates_tested,
                    elapsed_ms=(time.perf_counter() - t0) * 1000,
                )

        return MetaSearchResult(
            found=False,
            best_fitness=float('inf'),
            strategy_used="failed",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )


def run_meta_search(fitness_fn: Any, config: Optional[MetaSearchConfig] = None) -> Dict[str, Any]:
    """High-level runner for meta search."""
    search = MetaSearch(config=config, fitness_fn=fitness_fn)
    pairs = list(search.search_oriented_pairs())
    return {
        "found": True,
        "pairs_count": len(pairs),
        "candidates": pairs,
    }
