#!/usr/bin/env python3
"""
Fresh-VM Continuation Verification (Primitive E0).

Verifies cross-VM continuation:
A program is split at split_at, run on VM1 until the boundary, state captured,
and resumed in a fresh VM. The concatenation of outputs must match monolithic run.
"""
from __future__ import annotations
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, Union

from opera.evaluator import (
    load_malbolge_memory,
    crazy,
    _ENCRYPT,
    _VALID_OPS,
    EOF_VALUE,
    MEMORY_SIZE,
    run_malbolge_reference,
)


@dataclass
class ContinuationEvidence:
    """Evidence of fresh VM continuation."""
    program_length: int
    split_step: int
    full_output: str
    full_steps: int
    full_halted: bool
    prefix_output: str
    prefix_steps: int
    suffix_output: str
    suffix_steps: int
    suffix_halted: bool
    concatenated_output: str
    concatenation_match: bool
    full_sha256: str
    continuation_sha256: str
    continuation_pass: bool
    elapsed_ms: float = 0.0
    error: Optional[str] = None


def verify_fresh_vm_continuation(
    source: str, split_step: Optional[int] = None, max_steps: int = 1_000_000
) -> ContinuationEvidence:
    """
    Run monolithic Malbolge execution, split at step N, capture state (a, c, d, memory),
    resume in fresh VM, and verify exact output and SHA-256 equivalence.
    """
    t0 = time.perf_counter()

    # 1. Monolithic run
    ok, full_out, full_steps, full_halted, full_reason, _ = run_malbolge_reference(
        source, max_steps=max_steps
    )
    if not ok:
        elapsed = (time.perf_counter() - t0) * 1000
        return ContinuationEvidence(
            program_length=len(source.strip()),
            split_step=0,
            full_output="",
            full_steps=0,
            full_halted=False,
            prefix_output="",
            prefix_steps=0,
            suffix_output="",
            suffix_steps=0,
            suffix_halted=False,
            concatenated_output="",
            concatenation_match=False,
            full_sha256="",
            continuation_sha256="",
            continuation_pass=False,
            elapsed_ms=elapsed,
            error=full_reason,
        )

    # Determine split point in steps
    target_split = split_step if split_step is not None else max(1, full_steps // 2)

    # 2. VM 1: Run until target_split steps
    try:
        mem1 = load_malbolge_memory(source)
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return ContinuationEvidence(
            program_length=len(source.strip()),
            split_step=target_split,
            full_output=full_out,
            full_steps=full_steps,
            full_halted=full_halted,
            prefix_output="",
            prefix_steps=0,
            suffix_output="",
            suffix_steps=0,
            suffix_halted=False,
            concatenated_output="",
            concatenation_match=False,
            full_sha256=hashlib.sha256(full_out.encode()).hexdigest(),
            continuation_sha256="",
            continuation_pass=False,
            elapsed_ms=elapsed,
            error=f"Load error: {e}",
        )

    a1 = 0
    c1 = 0
    d1 = 0
    out1 = bytearray()
    steps1 = 0

    while steps1 < target_split:
        steps1 += 1
        op = (mem1[c1] + c1) % 94
        if op == 4:
            c1 = mem1[d1]
        elif op == 5:
            out1.append(a1 % 256)
        elif op == 23:
            a1 = EOF_VALUE
        elif op == 39:
            v = mem1[d1]
            mem1[d1] = v // 3 + (v % 3) * (3 ** 9)
            a1 = mem1[d1]
        elif op == 40:
            d1 = mem1[d1]
        elif op == 62:
            mem1[d1] = crazy(a1, mem1[d1])
            a1 = mem1[d1]
        elif op == 68:
            pass
        elif op == 81:
            # Halted before split
            break

        if 33 <= mem1[c1] <= 126:
            mem1[c1] = _ENCRYPT[mem1[c1]]

        c1 = (c1 + 1) % MEMORY_SIZE
        d1 = (d1 + 1) % MEMORY_SIZE

    # Capture snapshot state
    snap_a = a1
    snap_c = c1
    snap_d = d1
    snap_mem = list(mem1)  # full clone

    # 3. VM 2 (Fresh VM resuming from snapshot state)
    mem2 = list(snap_mem)
    a2 = snap_a
    c2 = snap_c
    d2 = snap_d
    out2 = bytearray()
    steps2 = 0
    halted2 = False

    while (steps1 + steps2) < max_steps:
        steps2 += 1
        op = (mem2[c2] + c2) % 94
        if op == 4:
            c2 = mem2[d2]
        elif op == 5:
            out2.append(a2 % 256)
        elif op == 23:
            a2 = EOF_VALUE
        elif op == 39:
            v = mem2[d2]
            mem2[d2] = v // 3 + (v % 3) * (3 ** 9)
            a2 = mem2[d2]
        elif op == 40:
            d2 = mem2[d2]
        elif op == 62:
            mem2[d2] = crazy(a2, mem2[d2])
            a2 = mem2[d2]
        elif op == 68:
            pass
        elif op == 81:
            halted2 = True
            break

        if 33 <= mem2[c2] <= 126:
            mem2[c2] = _ENCRYPT[mem2[c2]]

        c2 = (c2 + 1) % MEMORY_SIZE
        d2 = (d2 + 1) % MEMORY_SIZE

    prefix_str = out1.decode('latin-1', errors='replace')
    suffix_str = out2.decode('latin-1', errors='replace')
    concat_str = prefix_str + suffix_str

    full_sha = hashlib.sha256(full_out.encode('latin-1')).hexdigest()
    cont_sha = hashlib.sha256(concat_str.encode('latin-1')).hexdigest()
    match = (full_out == concat_str)
    cont_pass = match and (full_sha == cont_sha)

    elapsed = (time.perf_counter() - t0) * 1000

    return ContinuationEvidence(
        program_length=len(source.strip()),
        split_step=steps1,
        full_output=full_out,
        full_steps=full_steps,
        full_halted=full_halted,
        prefix_output=prefix_str,
        prefix_steps=steps1,
        suffix_output=suffix_str,
        suffix_steps=steps2,
        suffix_halted=halted2,
        concatenated_output=concat_str,
        concatenation_match=match,
        full_sha256=full_sha,
        continuation_sha256=cont_sha,
        continuation_pass=cont_pass,
        elapsed_ms=elapsed,
        error=None,
    )
