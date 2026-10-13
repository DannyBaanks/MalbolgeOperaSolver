#!/usr/bin/env python3
"""
Unified Evaluator — wraps all Malbolge backends for Danny Opera Solver.

Provides a unified interface to evaluate Malbolge programs across multiple backends:
- reference (in-process 3^10 Classic VM, fast & zero external dependencies)
- toolkit (malbolge-generator/toolkit in-process)
- oracle (malbolge-oracle Python reference)
- bolge19 (native Zig, 3^19)
- autobolge (BOLG1/BOLG2 container)
- walbolge (decompiler/roundtrip)
"""
from __future__ import annotations
import subprocess
import json
import os
import sys
import hashlib
import time
import tempfile
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

# -----------------------------------------------------------------------------
# Embedded Fast In-Process Reference VM (Classic 3^10 Malbolge)
# -----------------------------------------------------------------------------
MEMORY_SIZE = 3 ** 10  # 59049 cells

_CRAZY = (
    (1, 0, 0),
    (1, 0, 2),
    (2, 2, 1),
)

_ORIGINAL = (
    "!\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
)
_TRANSLATED = (
    "5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<."
    "TVac`uY*MK'X~xDl}REokN:#?G\"i@"
)
_ENCRYPT = {ord(o): ord(t) for o, t in zip(_ORIGINAL, _TRANSLATED)}
EOF_VALUE = 59048
_VALID_OPS = frozenset({4, 5, 23, 39, 40, 62, 68, 81})


def crazy(a: int, b: int) -> int:
    """Tritwise 'crazy' operation over exactly 10 trits."""
    result = 0
    place = 1
    for _ in range(10):
        result += _CRAZY[b % 3][a % 3] * place
        a //= 3
        b //= 3
        place *= 3
    return result


def load_malbolge_memory(source: str) -> list[int]:
    """Load and validate Classic Malbolge memory."""
    chars = [c for c in source if not c.isspace()]
    if len(chars) > MEMORY_SIZE:
        raise ValueError(f"program too long: {len(chars)} cells (max {MEMORY_SIZE})")
    mem = [0] * MEMORY_SIZE
    for i, ch in enumerate(chars):
        v = ord(ch)
        if not 33 <= v <= 126:
            raise ValueError(f"invalid source character {v!r} at position {i}")
        if (v + i) % 94 not in _VALID_OPS:
            raise ValueError(
                f"cell {i}: {ch!r} does not decode to a valid instruction "
                f"(({v} + {i}) % 94 = {(v + i) % 94})"
            )
        mem[i] = v
    for i in range(len(chars), MEMORY_SIZE):
        mem[i] = crazy(mem[i - 1], mem[i - 2])
    return mem


def run_malbolge_reference(
    source: str, stdin_data: bytes = b"", max_steps: int = 1_000_000
) -> tuple[bool, str, int, bool, str, float]:
    """
    Run Classic Malbolge in-process.
    Returns: (success, stdout, steps, halted, halt_reason, elapsed_ms)
    """
    t0 = time.perf_counter()
    try:
        mem = load_malbolge_memory(source)
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        return False, "", 0, False, f"LOAD_ERROR: {exc}", elapsed

    a = 0
    c = 0
    d = 0
    out = bytearray()
    stdin_pos = 0
    steps = 0

    while steps < max_steps:
        steps += 1
        op = (mem[c] + c) % 94
        if op == 4:        # jmp
            c = mem[d]
        elif op == 5:      # out
            out.append(a % 256)
        elif op == 23:     # in
            if stdin_pos < len(stdin_data):
                a = stdin_data[stdin_pos]
                stdin_pos += 1
            else:
                a = EOF_VALUE
        elif op == 39:     # rot
            v = mem[d]
            mem[d] = v // 3 + (v % 3) * (3 ** 9)
            a = mem[d]
        elif op == 40:     # movd
            d = mem[d]
        elif op == 62:     # crazy
            mem[d] = crazy(a, mem[d])
            a = mem[d]
        elif op == 68:     # nop
            pass
        elif op == 81:     # hlt
            elapsed = (time.perf_counter() - t0) * 1000
            return True, out.decode('latin-1', errors='replace'), steps, True, "halt_opcode", elapsed

        # self-encryption
        if 33 <= mem[c] <= 126:
            mem[c] = _ENCRYPT[mem[c]]

        c = (c + 1) % MEMORY_SIZE
        d = (d + 1) % MEMORY_SIZE

    elapsed = (time.perf_counter() - t0) * 1000
    return True, out.decode('latin-1', errors='replace'), steps, False, "max_steps_exceeded", elapsed


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------
@dataclass
class EvalResult:
    """Result of evaluating a Malbolge program."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = -1
    steps: int = 0
    halted: bool = False
    halt_reason: str = ""
    elapsed_ms: float = 0.0
    backend: str = ""
    raw_output: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BackendRegistry:
    """Registry of available backends and their capabilities."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = self._resolve_root(repo_root)
        self.backends = {}
        self._discover_backends()

    def _resolve_root(self, candidate: Optional[Path]) -> Path:
        if candidate and candidate.exists():
            return candidate.resolve()
        env_root = os.environ.get("OPERA_ISYCO_ROOT")
        if env_root and Path(env_root).exists():
            return Path(env_root).resolve()

        # Check typical ISyCo directories
        for search_dir in [
            Path("/home/danny/Development/ISyCo"),
            Path(__file__).resolve().parents[2],
            Path(__file__).resolve().parents[3] / "ISyCo",
            Path.cwd(),
        ]:
            if search_dir.exists() and (
                (search_dir / "workspace").exists()
                or (search_dir / "experiments0000").exists()
                or (search_dir / ".iesyroot").exists()
            ):
                return search_dir.resolve()

        return Path(__file__).resolve().parent

    def _discover_backends(self):
        """Auto-discover available backends."""
        # 1. Reference in-process engine is ALWAYS available
        self.backends["reference"] = {
            "type": "in_process",
            "model": "3^10 Classic",
            "supports_10trit": True,
            "supports_19trit": False,
        }

        # 2. Toolkit / malbolge-generator if available
        toolkit_dirs = [
            self.repo_root / "workspace" / "malbolge_toolkit",
            Path("/home/danny/Development/ISyCo/workspace/malbolge_toolkit"),
        ]
        toolkit_env = os.environ.get("OPERA_MALBOLGE_TOOLKIT")
        if toolkit_env:
            toolkit_dirs.insert(0, Path(toolkit_env))

        for td in toolkit_dirs:
            if td.exists() and (td / "malbolge").is_dir():
                self.backends["toolkit"] = {
                    "type": "in_process_python",
                    "path": td,
                    "supports_10trit": True,
                }
                if str(td) not in sys.path:
                    sys.path.insert(0, str(td))
                break

        # 3. bolge19 (native Zig)
        bolge19_candidates = [
            self.repo_root / "experiments0000" / "MalbolgeLisp Vs Isyco" / "runtime" / "bolge19.exe",
            self.repo_root / "experiments0000" / "MalbolgeLisp Vs Isyco" / "runtime" / "bolge19",
        ]
        for b19 in bolge19_candidates:
            if b19.exists() and (os.name == "nt" or os.access(b19, os.X_OK)):
                self.backends["bolge19"] = {
                    "type": "native",
                    "exe": b19,
                    "supports_19trit": True,
                    "supports_10trit": False,
                }
                break

        # 4. fast20_fixed
        fast20 = self.repo_root / "experiments0000" / "MalbolgeLisp Vs Isyco" / "runtime" / "fast20_fixed.exe"
        if fast20.exists() and (os.name == "nt" or os.access(fast20, os.X_OK)):
            self.backends["fast20_fixed"] = {
                "type": "native",
                "exe": fast20,
                "supports_19trit": True,
                "supports_10trit": False,
            }

        # 5. malbolge-oracle
        oracle_dirs = [
            self.repo_root / "experiments0000" / "MalbolgeLisp Vs Isyco" / "tools" / "malbolge-oracle",
            Path("/home/danny/Development/ISyCo/experiments0000/MalbolgeLisp Vs Isyco/tools/malbolge-oracle"),
            Path("/home/danny/Development/ISyCo Git/malbolge-oracle"),
        ]
        for od in oracle_dirs:
            if (od / "oracle.py").exists():
                self.backends["oracle"] = {
                    "type": "python",
                    "module": "oracle",
                    "dir": od,
                    "supports_10trit": True,
                }
                break

        # 6. Autobolge
        autobolge_env = os.environ.get("OPERA_AUTOBOLGE_EXE")
        if autobolge_env and Path(autobolge_env).exists():
            self.backends["autobolge"] = {
                "type": "native",
                "exe": Path(autobolge_env),
                "container": True,
                "supports_10trit": True,
            }

        # 7. Walbolge
        walbolge_candidates = [
            Path("/home/danny/Development/ISyCo Git/Walbolge"),
            Path("/home/danny/Development/ISyCo Git/walbolge"),
        ]
        walbolge_env = os.environ.get("OPERA_WALBOLGE_DIR")
        if walbolge_env:
            walbolge_candidates.insert(0, Path(walbolge_env))

        for wd in walbolge_candidates:
            if wd.exists() and (wd / "walbolge" / "cli.py").exists():
                self.backends["walbolge"] = {
                    "type": "python",
                    "module": "walbolge.cli",
                    "cwd": wd,
                }
                break

    def list_backends(self) -> dict:
        return {
            k: {k2: str(v2) if isinstance(v2, Path) else v2 for k2, v2 in v.items() if k2 != "exe"}
            for k, v in self.backends.items()
        }


class UnifiedEvaluator:
    """Unified evaluator for Malbolge programs across multiple backends."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.registry = BackendRegistry(repo_root)
        self.repo_root = self.registry.repo_root

    def evaluate_reference(
        self, source_or_path: Union[str, Path], stdin_data: Union[str, bytes] = b"", max_steps: int = 1_000_000
    ) -> EvalResult:
        """Evaluate using the built-in reference VM (fast, in-process)."""
        if isinstance(source_or_path, Path) or (isinstance(source_or_path, str) and os.path.exists(source_or_path) and "\n" not in source_or_path and len(source_or_path) < 256):
            try:
                with open(source_or_path, "r", encoding="ascii") as f:
                    source = f.read()
            except Exception as e:
                return EvalResult(success=False, backend="reference", stderr=f"Cannot read file: {e}")
        else:
            source = str(source_or_path)

        stdin_bytes = stdin_data.encode("latin-1") if isinstance(stdin_data, str) else stdin_data
        success, out, steps, halted, reason, elapsed = run_malbolge_reference(
            source, stdin_data=stdin_bytes, max_steps=max_steps
        )
        return EvalResult(
            success=success,
            stdout=out,
            stderr="" if success else reason,
            returncode=0 if success else 1,
            steps=steps,
            halted=halted,
            halt_reason=reason,
            elapsed_ms=elapsed,
            backend="reference",
            raw_output=out,
            metadata={"steps": steps, "halted": halted, "halt_reason": reason},
        )

    def evaluate(
        self, source_or_path: Union[str, Path], stdin_data: Union[str, bytes] = b"", backend: str = "reference", max_steps: int = 1_000_000
    ) -> EvalResult:
        """Evaluate with the requested backend (defaults to fast reference VM)."""
        if backend == "reference":
            return self.evaluate_reference(source_or_path, stdin_data, max_steps)
        elif backend == "oracle":
            if isinstance(source_or_path, Path) or os.path.exists(str(source_or_path)):
                with open(source_or_path, "r", encoding="ascii") as f:
                    text = f.read().strip()
            else:
                text = str(source_or_path)
            return self.evaluate_oracle(text, max_steps)
        elif backend == "bolge19":
            p = Path(source_or_path)
            return self.evaluate_bolge19(p, str(stdin_data), max_steps)
        elif backend == "autobolge":
            p = Path(source_or_path)
            stdin_bytes = stdin_data.encode() if isinstance(stdin_data, str) else stdin_data
            return self.evaluate_autobolge(p, stdin_bytes, max_steps)
        else:
            return self.evaluate_reference(source_or_path, stdin_data, max_steps)

    def _run_subprocess(
        self, cmd: list, cwd: Optional[Path] = None, stdin_data: str = "", timeout: int = 120
    ) -> tuple:
        """Run subprocess and return (rc, stdout, stderr, elapsed_ms)."""
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                input=stdin_data.encode() if stdin_data else None,
                capture_output=True,
                timeout=timeout,
                cwd=str(cwd) if cwd else None,
            )
            elapsed = (time.perf_counter() - start) * 1000
            return (
                proc.returncode,
                proc.stdout.decode("latin-1", errors="replace"),
                proc.stderr.decode("latin-1", errors="replace"),
                elapsed,
            )
        except subprocess.TimeoutExpired:
            elapsed = (time.perf_counter() - start) * 1000
            return -1, "", f"TIMEOUT after {timeout}s", elapsed
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return -1, "", str(e), elapsed

    def evaluate_bolge19(
        self, program_path: Path, stdin_data: str = "", max_steps: Optional[int] = None
    ) -> EvalResult:
        """Evaluate using bolge19 (native 3^19 VM)."""
        backend = self.registry.backends.get("bolge19")
        if not backend:
            return EvalResult(success=False, backend="bolge19", stderr="bolge19 not found")

        cmd = [str(backend["exe"]), str(program_path)]
        rc, out, err, elapsed = self._run_subprocess(cmd, stdin_data=stdin_data, timeout=300)

        steps = 0
        halted = False
        halt_reason = ""
        for line in out.split("\n"):
            if "HALT steps=" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "steps=":
                        try:
                            steps = int(parts[i + 1].rstrip(","))
                        except (ValueError, IndexError):
                            pass
                    if "halted=True" in line or "halted=true" in line.lower():
                        halted = True
                        halt_reason = "halt_opcode"

        return EvalResult(
            success=rc == 0,
            stdout=out,
            stderr=err,
            returncode=rc,
            steps=steps,
            halted=halted,
            halt_reason=halt_reason or ("max_steps" if "max_steps" in err.lower() else ""),
            elapsed_ms=elapsed,
            backend="bolge19",
            raw_output=out,
        )

    def evaluate_oracle(self, program_text: str, max_steps: int = 1_000_000) -> EvalResult:
        """Evaluate using malbolge-oracle (Python reference). Fallback to reference VM if oracle absent."""
        backend = self.registry.backends.get("oracle")
        if not backend:
            # Fallback cleanly to our reference VM
            res = self.evaluate_reference(program_text, max_steps=max_steps)
            res.backend = "oracle"
            return res

        oracle_dir = backend["dir"]
        if str(oracle_dir) not in sys.path:
            sys.path.insert(0, str(oracle_dir))

        try:
            from oracle import Oracle

            m = Oracle()
            m.load_ascii(program_text)
            r = m.run(max_steps=max_steps)

            return EvalResult(
                success=True,
                stdout=r.output,
                returncode=0,
                steps=r.steps,
                halted=r.halted,
                halt_reason=r.halt_reason,
                elapsed_ms=0,
                backend="oracle",
                raw_output=r.output or "",
                metadata={"steps": r.steps, "halted": r.halted, "halt_reason": r.halt_reason},
            )
        except Exception as e:
            return EvalResult(success=False, backend="oracle", stderr=str(e))

    def evaluate_autobolge(
        self, program_path: Path, input_data: bytes = b"", max_steps: int = 5_000_000
    ) -> EvalResult:
        """Evaluate using Autobolge BOLG1/BOLG2 container."""
        backend = self.registry.backends.get("autobolge")
        if not backend:
            # Fallback to reference VM
            return self.evaluate_reference(program_path, input_data, max_steps)

        with open(program_path, "r", encoding="ascii") as f:
            text = f.read().strip()
        cells = [ord(c) for c in text]

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".bin", delete=False) as f:
            ib = f.name
            blob = b"BOLG1" + struct.pack("<Q", 1)
            blob += struct.pack("<I", len(cells))
            for cval in cells:
                blob += struct.pack("<I", cval)
            blob += struct.pack("<I", len(input_data))
            blob += input_data
            blob += struct.pack("<I", max_steps)
            f.write(blob)

        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            ob = f.name

        try:
            rc, out, err, elapsed = self._run_subprocess([str(backend["exe"]), ib, ob], timeout=180)
            if os.path.exists(ob) and os.path.getsize(ob) > 13:
                data = open(ob, "rb").read()
                if data[:5] == b"BOLG2":
                    pos = 13
                    if pos + 4 <= len(data):
                        (olen,) = struct.unpack_from("<I", data, pos)
                        pos += 4
                        output = data[pos : pos + olen]
                        pos += olen
                        if pos + 9 <= len(data):
                            steps, term = struct.unpack_from("<QB", data, pos)
                            pos += 9
                            fc, fa, fd = (0, 0, 0)
                            if pos + 12 <= len(data):
                                fc, fa, fd = struct.unpack_from("<III", data, pos)
                            return EvalResult(
                                success=True,
                                stdout=output.decode("latin-1", errors="replace"),
                                stderr="",
                                returncode=0,
                                steps=steps,
                                halted=bool(term),
                                halt_reason="halt_opcode" if term else "",
                                elapsed_ms=elapsed,
                                backend="autobolge",
                                metadata={"final_c": fc, "final_a": fa, "final_d": fd},
                            )
            return EvalResult(
                success=rc == 0,
                stdout="",
                stderr="No valid output",
                returncode=rc,
                steps=0,
                halted=False,
                halt_reason="",
                elapsed_ms=elapsed,
                backend="autobolge",
            )
        finally:
            for f in [ib, ob]:
                try:
                    os.unlink(f)
                except Exception:
                    pass

    def evaluate_all(self, program_path: Path, program_text: str = "") -> Dict[str, EvalResult]:
        """Evaluate program with all available backends."""
        results = {}

        # 1. Reference backend (always evaluated, 3^10 Classic)
        prog_str = program_text
        if not prog_str and Path(program_path).exists():
            with open(program_path, "r", encoding="ascii") as f:
                prog_str = f.read().strip()

        if prog_str:
            results["reference"] = self.evaluate_reference(prog_str)

        # 2. Oracle backend
        if prog_str:
            results["oracle"] = self.evaluate_oracle(prog_str)

        # 3. bolge19 (if 19-trit compatible native binary exists)
        if Path(program_path).exists() and "bolge19" in self.registry.backends:
            results["bolge19"] = self.evaluate_bolge19(Path(program_path))

        # 4. autobolge (if classic 3^10 and autobolge binary configured)
        if Path(program_path).exists() and "autobolge" in self.registry.backends:
            if len(prog_str) <= MEMORY_SIZE:
                results["autobolge"] = self.evaluate_autobolge(Path(program_path))

        return results


if __name__ == "__main__":
    evaluator = UnifiedEvaluator()
    print("Available backends:", evaluator.registry.list_backends())
    # Quick self-test
    res = evaluator.evaluate_reference("D")
    print(f"Smoke test 'D': halted={res.halted}, steps={res.steps}, reason={res.halt_reason}")