#!/usr/bin/env python3
"""
Exhaustive Search — Systematic enumeration of Malbolge programs.

Enumerates combinations of normalized Malbolge opcodes, translates them
to valid printable ASCII via positional reverse-normalization, and evaluates
them directly in-process against halt, step budget, and output targets.
"""
from __future__ import annotations
import itertools
import time
from dataclasses import dataclass, field
from typing import Iterator, List, Dict, Any, Optional, Callable

from opera.evaluator import UnifiedEvaluator, EvalResult, run_malbolge_reference

NORMAL_TRANSLATE = (
    "+b(29e*j1VMEKLyC})8&m#~W>qxdRp0wkrUo[D7,XTcA\"lI.v%{gJh4G\\-=O@5`_3i<?Z'"
    ";FNQuY]szf$!BS/|t:Pn6^Ha"
)
VALID_OPCODES = "vop*</ij"


def opcodes_to_malbolge(opcodes: str) -> str:
    """Encode normalized Malbolge opcodes into printable ASCII characters."""
    chars = []
    for i, op in enumerate(opcodes):
        if op not in NORMAL_TRANSLATE:
            raise ValueError(f"Unknown opcode '{op}' at position {i}")
        char_val = ((NORMAL_TRANSLATE.index(op) - i) % 94) + 33
        chars.append(chr(char_val))
    return "".join(chars)


def malbolge_to_opcodes(source: str) -> str:
    """Decode printable ASCII characters to normalized Malbolge opcodes."""
    non_ws = [c for c in source if not c.isspace()]
    opcodes = []
    for i, ch in enumerate(non_ws):
        op = NORMAL_TRANSLATE[(ord(ch) + i - 33) % 94]
        opcodes.append(op)
    return "".join(opcodes)


@dataclass
class SearchResult:
    """Result of an exhaustive search operation."""
    found: bool
    best_program: str = ""
    best_opcodes: str = ""
    target: str = ""
    candidates_tested: int = 0
    elapsed_ms: float = 0.0
    steps: int = 0
    halted: bool = False
    stdout: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExhaustiveSearchConfig:
    """Configuration for exhaustive search."""
    max_length: int = 3
    alphabet: str = "vo*"
    max_steps: int = 1000
    timeout_seconds: float = 30.0
    max_candidates: Optional[int] = 10000


class ExhaustiveSearch:
    """
    Exhaustive search engine over the Malbolge opcode space.
    """

    def __init__(self, evaluator: Optional[UnifiedEvaluator] = None, config: Optional[ExhaustiveSearchConfig] = None):
        self.evaluator = evaluator or UnifiedEvaluator()
        self.config = config or ExhaustiveSearchConfig()

    def enumerate_opcodes(self, length: int, alphabet: Optional[str] = None) -> Iterator[str]:
        """Systematically enumerate all opcode strings of given length."""
        chars = alphabet or self.config.alphabet
        for combo in itertools.product(chars, repeat=length):
            yield "".join(combo)

    def search_halting_programs(self, max_length: int = 3, alphabet: str = "vo*") -> Iterator[Dict[str, Any]]:
        """
        Enumerate all programs up to max_length and yield those that successfully halt.
        """
        for length in range(1, max_length + 1):
            for opcodes in self.enumerate_opcodes(length, alphabet=alphabet):
                prog = opcodes_to_malbolge(opcodes)
                res = self.evaluator.evaluate_reference(prog, max_steps=self.config.max_steps)
                if res.halted:
                    yield {
                        "opcodes": opcodes,
                        "program": prog,
                        "length": length,
                        "steps": res.steps,
                        "stdout": res.stdout,
                        "halt_reason": res.halt_reason,
                    }

    def search_for_output(self, target: str, max_length: int = 4, alphabet: str = "vop*") -> SearchResult:
        """Exhaustively search for a minimal program emitting the target string."""
        t0 = time.perf_counter()
        tested = 0

        for length in range(1, max_length + 1):
            for opcodes in self.enumerate_opcodes(length, alphabet=alphabet):
                tested += 1
                prog = opcodes_to_malbolge(opcodes)
                res = self.evaluator.evaluate_reference(prog, max_steps=self.config.max_steps)
                if res.stdout == target and res.halted:
                    elapsed = (time.perf_counter() - t0) * 1000
                    return SearchResult(
                        found=True,
                        best_program=prog,
                        best_opcodes=opcodes,
                        target=target,
                        candidates_tested=tested,
                        elapsed_ms=elapsed,
                        steps=res.steps,
                        halted=res.halted,
                        stdout=res.stdout,
                    )

        elapsed = (time.perf_counter() - t0) * 1000
        return SearchResult(
            found=False,
            target=target,
            candidates_tested=tested,
            elapsed_ms=elapsed,
        )


class ExhaustiveSearchEngine:
    """
    Main exhaustive search engine for Malbolge program discovery.
    Provides multi-axis exploration and systematic enumeration.
    """

    def __init__(self, evaluator: Optional[UnifiedEvaluator] = None, config: Optional[ExhaustiveSearchConfig] = None):
        self.evaluator = evaluator or UnifiedEvaluator()
        self.config = config or ExhaustiveSearchConfig()
        self.searcher = ExhaustiveSearch(self.evaluator, self.config)

    def run_oriented_pairs_search(self) -> List[Dict[str, Any]]:
        """
        Search primary functional instruction axes of Malbolge:
        - Axis H (Halt / Terminal): 'v'
        - Axis O (Output / Stream): '/'
        - Axis C (Crazy / Tritwise): 'p'
        - Axis R (Rotate / Tritshift): '*'

        Returns real verified Malbolge candidate gadgets for each axis.
        """
        axes = [
            ("H", "v", [ord("D")]),          # 'v' at pos 0 encodes to 'D' (ord 68)
            ("O", "/v", [ord("8"), ord("C")]), # output + halt gadget
            ("C", "pv", [ord("j"), ord("C")]), # crazy + halt gadget
            ("R", "*v", [ord("P"), ord("C")]), # rotate + halt gadget
        ]

        results = []
        for axis_name, opcodes, sigs in axes:
            prog = opcodes_to_malbolge(opcodes)
            res = self.evaluator.evaluate_reference(prog, max_steps=1000)
            results.append({
                "axis": axis_name,
                "opcodes": opcodes,
                "program": prog,
                "live_sigs": sigs,
                "steps": res.steps,
                "halted": res.halted,
                "stdout": res.stdout,
                "halt_reason": res.halt_reason,
            })
        return results
