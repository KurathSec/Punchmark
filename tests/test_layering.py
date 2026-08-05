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
    """Every module name this file can reach: plain/relative/absolute imports, the
    submodule leg of `punchmark.X` forms, and dynamic __import__/import_module
    calls with constant arguments. Non-constant dynamic imports are banned
    outright below, so nothing can hide behind a variable."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()

    def add(dotted: str) -> None:
        parts = dotted.split(".")
        names.add(parts[0])
        if parts[0] == "punchmark" and len(parts) > 1:
            names.add(parts[1])  # absolute self-import: punchmark.cli -> cli

    for node in ast.walk(tree):  # ast.walk sees lazy imports inside functions too
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:  # relative: from .x import y
                if node.module:
                    add(node.module)
                else:  # from . import x, y
                    for alias in node.names:
                        add(alias.name)
            elif node.module:
                add(node.module)
                if node.module == "punchmark":
                    for alias in node.names:
                        names.add(alias.name)
        elif isinstance(node, ast.Call):
            func = node.func
            is_dunder = isinstance(func, ast.Name) and func.id == "__import__"
            is_im = isinstance(func, ast.Attribute) and func.attr == "import_module"
            if is_dunder or is_im:
                const = (
                    node.args[0].value
                    if node.args and isinstance(node.args[0], ast.Constant)
                    else None
                )
                assert isinstance(const, str), (
                    f"{path.name}: dynamic import with a non-constant argument; "
                    "the layering gate cannot see through it, so it is banned"
                )
                add(const)
    return names


def _module_files() -> dict[str, Path]:
    """Every module in the package, subpackages included, keyed by dotted name.
    A top-level glob would leave subpackage modules unchecked."""
    return {
        p.relative_to(SRC).with_suffix("").as_posix().replace("/", "."): p
        for p in SRC.rglob("*.py")
    }


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


# .replace is NOT in this set: str.replace is ubiquitous and AST cannot
# distinguish it from Path.replace; the open-mode check covers file replacement.
_WRITE_ATTRS = {
    "write_text", "write_bytes", "unlink", "remove", "rmtree", "rename",
    "mkdir", "makedirs", "touch", "rmdir",
}


def test_reader_modules_are_write_free() -> None:
    """archive.py and sidecar.py never write: no write-mode open of ANY flavor
    (builtin open, gzip.open, Path.open, os.open), no write/delete helpers."""
    for name in ("archive", "sidecar"):
        path = SRC / f"{name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_openish = (isinstance(func, ast.Name) and func.id == "open") or (
                isinstance(func, ast.Attribute) and func.attr == "open"
            )
            if is_openish:
                modes = [
                    a.value
                    for a in node.args[1:2]
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                ]
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        modes.append(kw.value.value)
                for mode in modes:
                    assert not set(mode) & {"w", "a", "x", "+"}, (
                        f"{name} opens a file for writing (mode {mode!r})"
                    )
            if isinstance(func, ast.Attribute):
                assert func.attr not in _WRITE_ATTRS, f"{name} calls .{func.attr}()"
            if isinstance(func, ast.Name):
                assert func.id not in {"remove", "rmtree"}, f"{name} calls {func.id}()"
        imported = _imports(path)
        assert "shutil" not in imported, f"{name} imports shutil"
