"""opera/verify/oracle.py — Strict Canonical C Oracle Verification.

Verifies Malbolge programs using BolgeForge / PureEpoch strict canonical C oracle (mb_ref)
and classic reference interpreter binaries.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union


ORACLE_CANDIDATES = [
    Path("/home/danny/Development/ISyCo Git/BolgeForge/mb_ref"),
    Path("/home/danny/Development/ISyCo/workspace/assembly/malbolge/reference_interpreter_classic"),
    Path("/home/danny/Development/ISyCo Git/Malbolge-PureEpoch/vendor/mb_ref"),
]


def find_canonical_oracle() -> Optional[Path]:
    """Finds the best canonical C oracle binary."""
    env_p = os.environ.get("OPERA_MB_REF")
    if env_p and Path(env_p).exists():
        return Path(env_p)
    for c in ORACLE_CANDIDATES:
        if c.exists() and c.is_file() and os.access(c, os.X_OK):
            return c
    return None


@dataclass
class OracleVerificationResult:
    """Result of canonical C oracle verification."""
    success: bool
    stdout: str
    stderr: str
    returncode: int
    elapsed_ms: float
    halted: bool
    halt_reason: str
    oracle_path: Optional[Path] = None


class OracleVerifier:
    """Verifier for Malbolge programs against strict canonical C reference."""

    def __init__(self, oracle_path: Optional[Path] = None):
        self.oracle_path = oracle_path or find_canonical_oracle()

    def is_available(self) -> bool:
        return self.oracle_path is not None and self.oracle_path.exists()

    def verify(
        self,
        program_or_path: Union[str, Path],
        stdin_data: Union[str, bytes] = b"",
        max_steps: int = 100_000_000,
        timeout: int = 60,
    ) -> OracleVerificationResult:
        if not self.is_available():
            return OracleVerificationResult(
                success=False,
                stdout="",
                stderr="Canonical C oracle (mb_ref) not found",
                returncode=-1,
                elapsed_ms=0.0,
                halted=False,
                halt_reason="ORACLE_NOT_FOUND",
            )

        tmp_path = None
        if isinstance(program_or_path, Path) or (
            isinstance(program_or_path, str)
            and os.path.exists(program_or_path)
            and "\n" not in program_or_path
            and len(program_or_path) < 256
        ):
            file_path = str(program_or_path)
        else:
            with tempfile.NamedTemporaryFile("w", suffix=".mal", delete=False) as f:
                f.write(str(program_or_path))
                tmp_path = f.name
            file_path = tmp_path

        cmd = [str(self.oracle_path), file_path]
        if "mb_ref" in self.oracle_path.name:
            cmd.append(str(max_steps))

        stdin_bytes = stdin_data.encode("latin-1") if isinstance(stdin_data, str) else stdin_data
        t0 = time.perf_counter()

        try:
            proc = subprocess.run(
                cmd,
                input=stdin_bytes,
                capture_output=True,
                timeout=timeout,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            stdout = proc.stdout.decode("latin-1", errors="replace")
            stderr = proc.stderr.decode("latin-1", errors="replace")
            halted = (proc.returncode == 0)
            return OracleVerificationResult(
                success=halted,
                stdout=stdout,
                stderr=stderr,
                returncode=proc.returncode,
                elapsed_ms=elapsed,
                halted=halted,
                halt_reason="halt_opcode" if halted else f"exit_code_{proc.returncode}",
                oracle_path=self.oracle_path,
            )
        except subprocess.TimeoutExpired:
            elapsed = (time.perf_counter() - t0) * 1000
            return OracleVerificationResult(
                success=False,
                stdout="",
                stderr=f"TIMEOUT after {timeout}s",
                returncode=-1,
                elapsed_ms=elapsed,
                halted=False,
                halt_reason="TIMEOUT",
                oracle_path=self.oracle_path,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return OracleVerificationResult(
                success=False,
                stdout="",
                stderr=str(e),
                returncode=-1,
                elapsed_ms=elapsed,
                halted=False,
                halt_reason=str(e),
                oracle_path=self.oracle_path,
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
