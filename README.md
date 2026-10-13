# Malbolge Opera Solver

![Malbolge Opera Solver pipeline](malbolge_opera_solver.gif)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Status: Verified](https://img.shields.io/badge/status-verified%20pass-brightgreen.svg)](#verificación-y-benchmarks)

**Malbolge Opera Solver** — framework integral de síntesis por espacio de estados, búsqueda posicional estocástica, normalización y verificación multi-backend de programas Malbolge.

Autor: **Danny Banks** · Licencia: MIT

---

## Qué es

Un framework avanzado diseñado para dominar la complejidad auto-modificante de Malbolge (3^10 Classic y 3^19 Unshackled):

- **Síntesis por Espacio de Estados (Beam Search)**: Genera programas de Malbolge puro que imprimen texto arbitrario de forma exacta en milisegundos.
- **Búsqueda Posicional Guiada (Simulated Annealing)**: Optimización estocástica sobre el espacio de opcodes canónicos (`v`, `o`, `p`, `*`, `<`, `/`, `i`, `j`) mapeados posicionalmente módulo 94.
- **Minimización Ablativa Real**: Compresión y simplificación de programas Malbolge: poda instrucciones muertas tras halt (`v`) y reemplaza opcodes no esenciales con NOPs (`o`) preservando el 100% de la salida y el comportamiento de parada.
- **Verificación de Continuidad Cross-VM (Primitiva E0)**: Demuestra que un programa puede dividirse, capturar su snapshot (`a, c, d, memoria`) y reanudarse en una VM fresca produciendo salida y SHA-256 idénticos.
- **Evaluador In-Process de Ultra-Alto Rendimiento**: Intérprete canónico en memoria que ejecuta miles de pasos por segundo con soporte para backends externos (malbolge-oracle, Walbolge, Autobolge, bolge19).

---

## Quick Start

### 1. Sintetizar un programa desde DannyScript

Crea un archivo de especificación `hello.danny`:
```text
target "Hello World!"
constraint max_steps = 1000000
objective minimize size
```

Ejecuta el solver con minimización ablativa automática:
```bash
python3 opera.py solve hello.danny -o hello.mal --minimize
```

Salida esperada:
```text
============================================================
DANNY OPERA SOLVER — SOLVE
============================================================
Target:       'Hello World!'
Constraints:  {'max_steps': 1000000}
Objectives:   [('minimize', 'size')]

Running ablative minimization...
  Ablation complete: saved 0 bytes, simplified 91 NOPs

------------------------------------------------------------
SOLVED PROGRAM:
------------------------------------------------------------
Length:       324 chars
SHA-256:      5fe6a3f7d1444eba50a207a793f25b5362b4ffd31005065b0a2b152eed7a4e4e
Steps:        226
Output:       'Hello World!'
Saved to: hello.mal
```

---

### 2. Normalizar una cinta Malbolge a mnemónicos

Decodifica cualquier programa binario/ASCII a sus opcodes normalizados según su desplazamiento posicional:
```bash
python3 opera.py normalize hello.mal
```

Salida:
```text
============================================================
NORMALIZATION: hello.mal
============================================================
Raw length:     324
Opcodes:        iooooooooooooooooooooooooooooooooo...

POS   CHAR  OPCODE
------------------
0000  'b'   i
0001  'C'   o
0002  'B'   o
0003  'A'   o
...
```

---

### 3. Verificar Continuidad Cross-VM (Primitiva E0)

Verifica que el programa cumple la propiedad formal de continuidad multi-época:
```bash
python3 opera.py verify hello.mal --continuation
```

Salida:
```text
============================================================
VERIFY SPECIMEN: hello.mal
============================================================
Reference VM (3^10):
  Success:     True
  Halted:      True (halt_opcode)
  Steps:       226
  Stdout:      'Hello World!'

--- Fresh-VM Continuation (Primitive E0) ---
  Continuation Pass:  True
  Split Step:         113
  Concatenated Match: True
  SHA-256 Match:      True
```

---

### 4. Minimización Ablativa de un Programa Existente

Reduce programas eliminando opcodes redundantes y sustituyendo operaciones complejas por NOPs:
```bash
python3 opera.py ablate specimen.mal -o minimized.mal
```

---

## Arquitectura

```
opera/
├── dsl.py              # Parser para DannyScript / OperaScript DSL
├── evaluator.py        # Evaluador unificado (VM Reference in-process + multi-backend)
├── objectives.py       # Evaluación multi-objetivo y restricciones
├── search/
│   ├── beam.py         # Síntesis por espacio de estados (Beam Search)
│   ├── exhaustive.py   # Enumeración exhaustiva de opcodes y mapeo posicional
│   ├── sa.py           # Simulated Annealing posicional guiado
│   ├── meta.py         # Coordinador y orquestador de estrategias de búsqueda
│   └── ablative.py     # Minimizador ablativo y compresor de opcodes
├── verify/
│   ├── continuation.py # Verificación formal Fresh-VM Continuation (E0)
│   ├── walbolge.py     # Decompilación inversa y roundtrip con Walbolge
│   └── autobolge.py    # Contenedores BOLG1/BOLG2
└── cli.py              # CLI principal (solve, normalize, verify, search, ablate)
```

---

## Backends Soportados

| Backend | Tipo | Rol |
|---|---|---|
| `reference` | In-process Python | VM canónica 3^10 Classic, microsegundos de latencia, 0 dependencias externas |
| `toolkit` | In-process Python | Adaptador de generación y síntesis `malbolge-generator` |
| `oracle` | Python | Intérprete de referencia de control (`malbolge-oracle`) |
| `Autobolge` | Nativo / Contenedor | Contenedor binario BOLG1/BOLG2 (Zig) |
| `Walbolge` | Python | Decompilador estructural inverso del Translator |
| `bolge19` | Nativo Zig | VM 3^19 Unshackled para MalbolgeLISP |

---

## Verificación y Benchmarks

El repositorio incluye suites de pruebas que validan todas las estrategias y backends:

```bash
# 1. Pipeline completo (Exhaustive, SA, Meta, Ablative)
python3 test_pipeline_final.py

# 2. Benchmark cruzado de Hello World (Reference + Oracle)
python3 test_hello_search.py

# 3. Verificación de espécimen largo (Capítulo 1 de Don Quijote)
python3 test_quijote.py

# 4. Demostración integral de SA posicional y síntesis Beam
python3 sa_search_final.py
```

---

### Atribución

Este proyecto es trabajo original de **Danny Banks** dentro de **ISyCo (Interactive System for Coevolution)**.

Los backends referenciados (`malbolge-oracle`, `Walbolge`, `Autobolge`, `bolge19`, `fast20`) pertenecen al ecosistema ISyCo y a sus autores respectivos.

---

## Licencia

MIT — ver [`LICENSE`](LICENSE).
