"""Mechanical gate 3: the import DAG, enforced by AST.

Rules (ARCHITECTURE.md section 2):
- no module in src/ imports the foreign checkout's packages (src, bench, eval) or
  the numeric stack (numpy, scipy, sklearn, pandas) -- at module level OR lazily;
- nothing imports cli;
- readers (archive, sidecar, synth) never import the analysis stack;
- the detector never imports a reader (it sees ResponseSets, not files);
- the gate consumes serialized artifacts only;
- the reader modules are write-free.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "punchmark"

FOREIGN = {"src", "bench", "eval", "numpy", "scipy", "sklearn", "pandas"}
ANALYSIS = {"features", "views", "detector", "calibrate", "power", "score", "modelfile"}
READERS = {"archive", "sidecar", "synth"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):  # ast.walk sees lazy imports inside functions too
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:  # relative: from .x import y
                if node.module:
                    names.add(node.module.split(".")[0])
            elif node.module:
                names.add(node.module.split(".")[0])
    return names


def _module_files() -> dict[str, Path]:
    files = {p.stem: p for p in SRC.glob("*.py")}
    files["spec"] = SRC / "spec" / "registry.py"
    return files


def test_no_foreign_imports_anywhere_even_lazy() -> None:
    for name, path in _module_files().items():
        bad = _imports(path) & FOREIGN
        assert not bad, f"{name} imports foreign module(s) {bad}"


def test_nothing_imports_cli() -> None:
    for name, path in _module_files().items():
        if name == "cli":
            continue
        assert "cli" not in _imports(path), f"{name} imports cli"


def test_readers_do_not_import_the_analysis_stack() -> None:
    for name in READERS:
        deps = _imports(SRC / f"{name}.py")
        bad = deps & ANALYSIS
        assert not bad, f"reader {name} imports analysis module(s) {bad}"


def test_detector_never_imports_a_reader() -> None:
    deps = _imports(SRC / "detector.py")
    bad = deps & READERS
    assert not bad, f"detector imports reader(s) {bad} -- it must only see ResponseSets"


def test_gate_is_artifact_only() -> None:
    deps = _imports(SRC / "gate.py")
    banned = READERS | {"features", "views", "detector", "calibrate", "power", "score"}
    bad = deps & banned
    assert not bad, f"gate imports {bad}; the gate consumes serialized artifacts only"


def test_reader_modules_are_write_free() -> None:
    """archive.py and sidecar.py never write: no write-mode open, no write helpers."""
    for name in ("archive", "sidecar"):
        path = SRC / f"{name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "open":
                    modes = [
                        a.value
                        for a in node.args[1:2]
                        if isinstance(a, ast.Constant) and isinstance(a.value, str)
                    ]
                    for kw in node.keywords:
                        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                            modes.append(kw.value.value)
                    for mode in modes:
                        assert not set(mode) & {"w", "a", "x"}, (
                            f"{name} opens a file for writing"
                        )
                if isinstance(func, ast.Attribute):
                    assert func.attr not in {"write_text", "write_bytes", "unlink"}, (
                        f"{name} calls {func.attr}"
                    )
        imported = _imports(path)
        assert "shutil" not in imported, f"{name} imports shutil"
