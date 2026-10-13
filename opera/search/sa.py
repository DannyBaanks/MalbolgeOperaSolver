#!/usr/bin/env python3
"""
Simulated Annealing Search — Stochastic optimization for Malbolge programs.

Provides:
1. Positional Opcode Annealing for discovering and optimizing Malbolge programs.
2. Stochastic vector optimization with Metropolis acceptance criterion.
"""
from __future__ import annotations
from typing import Iterator, List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
import random
import math
import time

from opera.evaluator import UnifiedEvaluator, EvalResult, run_malbolge_reference
from opera.search.exhaustive import opcodes_to_malbolge, malbolge_to_opcodes, VALID_OPCODES


@dataclass
class SAConfig:
    """Configuration for Simulated Annealing."""
    initial_temp: float = 5.0
    cooling_rate: float = 0.99975
    min_temp: float = 1e-12
    max_iterations: int = 20000
    neighbor_count: int = 1
    report_interval: int = 1000


@dataclass
class SAState:
    """Current state of SA search."""
    bits: List[int]
    fitness: float
    iteration: int = 0
    temperature: float = 5.0
    accepted: int = 0
    rejected: int = 0


class SimulatedAnnealingSearch:
    """
    Simulated Annealing search engine.
    Supports both discrete vector annealing and Malbolge opcode annealing.
    """

    def __init__(self, evaluator: Optional[UnifiedEvaluator] = None, config: Optional[SAConfig] = None):
        if isinstance(evaluator, SAConfig):
            self.config = evaluator
            self.evaluator = UnifiedEvaluator()
        else:
            self.evaluator = evaluator or UnifiedEvaluator()
            self.config = config or SAConfig()
        self.rng = random.Random(123)
        self.best_state = None
        self.best_fitness = float('inf')

    def random_initial_state(self, size: int = 512, density: float = 0.03) -> List[int]:
        """Generate initial sparse binary state."""
        bits = [0] * size
        for i in range(1, size):
            if self.rng.random() < density:
                bits[i] = 1
        return bits

    def mutate_bits(self, bits: List[int], count: int = 1) -> List[int]:
        """Flip random bits."""
        new_bits = bits[:]
        indices = self.rng.sample(range(1, len(bits)), min(count, len(bits) - 1))
        for i in indices:
            new_bits[i] ^= 1
        return new_bits

    def acceptance_probability(self, current_fitness: float, new_fitness: float, temperature: float) -> bool:
        """Metropolis acceptance criterion (minimization: lower fitness is better)."""
        if new_fitness <= current_fitness:
            return True
        if temperature <= 1e-12:
            return False
        delta = new_fitness - current_fitness
        prob = math.exp(-delta / temperature)
        return self.rng.random() < prob

    def run(self, fitness_fn: Callable[[List[int]], float],
            initial_bits: Optional[List[int]] = None,
            max_iterations: Optional[int] = None) -> Dict[str, Any]:
        """Run simulated annealing on a bit/vector fitness function."""
        t0 = time.perf_counter()
        iters = max_iterations or self.config.max_iterations

        current_bits = initial_bits[:] if initial_bits else self.random_initial_state()
        current_fit = fitness_fn(current_bits)

        best_bits = current_bits[:]
        best_fit = current_fit

        temp = self.config.initial_temp

        for it in range(iters):
            neighbor = self.mutate_bits(current_bits, count=self.config.neighbor_count)
            neighbor_fit = fitness_fn(neighbor)

            if self.acceptance_probability(current_fit, neighbor_fit, temp):
                current_bits = neighbor
                current_fit = neighbor_fit
                if neighbor_fit < best_fit:
                    best_bits = neighbor[:]
                    best_fit = neighbor_fit

            temp = max(self.config.min_temp, temp * self.config.cooling_rate)
            if best_fit == 0:
                break

        elapsed = time.perf_counter() - t0
        return {
            "best_bits": best_bits,
            "best_fitness": best_fit,
            "iterations": it + 1,
            "elapsed_sec": elapsed,
            "final_temp": temp,
            "converged": best_fit == 0,
        }

    def search_malbolge_program(
        self,
        target_output: str,
        initial_length: int = 24,
        max_iterations: int = 3000,
        alphabet: str = "vop*",
    ) -> Dict[str, Any]:
        """
        Positional simulated annealing directly over Malbolge opcode sequences.
        Guides stochastic mutations using in-process evaluation.
        """
        t0 = time.perf_counter()

        def eval_fitness(opcodes: str) -> tuple[float, str, int, bool]:
            prog = opcodes_to_malbolge(opcodes)
            res = self.evaluator.evaluate_reference(prog, max_steps=100)
            if not res.halted:
                return 10000.0, res.stdout, res.steps, False

            out = res.stdout
            # Distance from target
            matched = sum(1 for a, b in zip(out, target_output) if a == b)
            dist = len(target_output) - matched
            fit = dist * 100.0 + abs(len(out) - len(target_output)) * 20.0 + (res.steps / 500.0)
            if out == target_output:
                fit = 0.0
            return fit, out, res.steps, True

        # Initial candidate: random opcodes ending in 'v' (halt)
        current = "".join(self.rng.choice(alphabet) for _ in range(initial_length - 1)) + "v"
        current_fit, cur_out, cur_steps, cur_halt = eval_fitness(current)

        best_opcodes = current
        best_fit = current_fit
        best_out = cur_out
        best_steps = cur_steps

        temp = self.config.initial_temp

        for it in range(max_iterations):
            # Mutate 1 or 2 opcodes
            op_list = list(current)
            pos = self.rng.randint(0, len(op_list) - 1)
            op_list[pos] = self.rng.choice(alphabet)
            neighbor = "".join(op_list)

            neighbor_fit, n_out, n_steps, n_halt = eval_fitness(neighbor)

            if self.acceptance_probability(current_fit, neighbor_fit, temp):
                current = neighbor
                current_fit = neighbor_fit
                if neighbor_fit < best_fit:
                    best_opcodes = neighbor
                    best_fit = neighbor_fit
                    best_out = n_out
                    best_steps = n_steps

            temp = max(self.config.min_temp, temp * self.config.cooling_rate)
            if best_fit == 0:
                break

        elapsed = time.perf_counter() - t0
        best_prog = opcodes_to_malbolge(best_opcodes)

        return {
            "found": best_fit == 0,
            "best_program": best_prog,
            "best_opcodes": best_opcodes,
            "best_fitness": best_fit,
            "stdout": best_out,
            "steps": best_steps,
            "iterations": it + 1,
            "elapsed_sec": elapsed,
        }


def run_sa_search(
    fitness_fn: Callable[[List[int]], float],
    config: Optional[SAConfig] = None,
    seed: int = 123,
    initial_bits: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """High-level function to run SA search."""
    config = config or SAConfig()
    search = SimulatedAnnealingSearch(config)
    search.rng = random.Random(seed)
    return search.run(fitness_fn, initial_bits=initial_bits)


if __name__ == "__main__":
    result = run_sa_search(
        fitness_fn=lambda b: sum(b),
        config=SAConfig(max_iterations=1000),
        seed=42,
    )
    print(f"Best fitness: {result['best_fitness']}")
    print(f"Iterations: {result['iterations']}")
