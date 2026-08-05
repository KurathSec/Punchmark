"""The calibration corpus: manifest identity and the non-shipped modes.

PMK-COR-001 makes the manifest's content hash the corpus identity every ruling
pins, and PMK-COR-002 says the raw and features modes exist in code and are
exercised synthetically even though the reference corpus ships neither. These
tests are that exercise: without them the ruling's claim would be false.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from punchmark.canonical import sha256_file
from punchmark.corpus import (
    MANIFEST_NAME,
    MODES,
    build_manifest,
    read_manifest,
    verify_shipped,
    verify_sources,
    write_manifest,
)
from punchmark.errors import CorpusError


def _source_file(tmp_path: Path, name: str, text: str) -> dict:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return {"path": name, "sha256": sha256_file(path)}


def test_manifest_roundtrip_and_identity(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    sources = [_source_file(src, "a.jsonl.gz", "one"), _source_file(src, "b.jsonl.gz", "two")]
    corpus = tmp_path / "corpus"
    manifest = build_manifest(
        mode="manifest",
        checkout={"repo": "https://example.invalid/repo", "commit": "0" * 40},
        sources=sources,
        files=[],
        note="synthetic",
    )
    write_manifest(corpus, manifest)
    reread = read_manifest(corpus)
    assert reread.manifest_id == manifest.manifest_id
    assert reread.corpus_sha256 == manifest.manifest_id  # PMK-COR-001
    assert reread.mode == "manifest"
    lines = verify_shipped(corpus, reread)
    assert any("nothing shipped by design" in line for line in lines)


def test_manifest_id_is_a_content_address(tmp_path: Path) -> None:
    """An edited manifest fails its own hash (PMK-EMIT-002)."""
    corpus = tmp_path / "corpus"
    src = tmp_path / "src"
    src.mkdir()
    manifest = build_manifest(
        mode="manifest", checkout={"repo": "r", "commit": "c"},
        sources=[_source_file(src, "a.gz", "one")], files=[], note="n",
    )
    write_manifest(corpus, manifest)
    body = json.loads((corpus / MANIFEST_NAME).read_text())
    body["note"] = "edited after the fact"
    (corpus / MANIFEST_NAME).write_text(json.dumps(body, sort_keys=True, indent=2) + "\n")
    with pytest.raises(CorpusError, match="does not match content"):
        read_manifest(corpus)


@pytest.mark.parametrize("mode", ["raw", "features"])
def test_shipping_modes_verify_and_detect_tampering(tmp_path: Path, mode: str) -> None:
    """PMK-COR-002: raw and features are implemented and exercised, though the
    reference corpus ships neither."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    shipped = _source_file(corpus, "sets.jsonl.gz", "shipped payload")
    src = tmp_path / "src"
    src.mkdir()
    manifest = build_manifest(
        mode=mode, checkout={"repo": "r", "commit": "c"},
        sources=[_source_file(src, "a.gz", "one")], files=[shipped], note="n",
    )
    write_manifest(corpus, manifest)
    manifest = read_manifest(corpus)
    assert any("ok shipped sets.jsonl.gz" in line for line in verify_shipped(corpus, manifest))

    (corpus / "sets.jsonl.gz").write_text("tampered", encoding="utf-8")
    with pytest.raises(CorpusError, match="sha256"):
        verify_shipped(corpus, manifest)

    (corpus / "sets.jsonl.gz").unlink()
    with pytest.raises(CorpusError, match="shipped file missing"):
        verify_shipped(corpus, manifest)


def test_rebuild_verifies_local_sources_and_refuses_wrong_bytes(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    src = tmp_path / "checkout"
    src.mkdir()
    manifest = build_manifest(
        mode="manifest", checkout={"repo": "r", "commit": "c"},
        sources=[_source_file(src, "a.gz", "one")], files=[], note="n",
    )
    write_manifest(corpus, manifest)
    manifest = read_manifest(corpus)
    assert any("rebuild verified" in line for line in verify_sources(manifest, src))

    (src / "a.gz").write_text("different bytes", encoding="utf-8")
    with pytest.raises(CorpusError, match="wrong commit"):
        verify_sources(manifest, src)

    (src / "a.gz").unlink()
    with pytest.raises(CorpusError, match="missing from checkout"):
        verify_sources(manifest, src)

    with pytest.raises(CorpusError, match="does not exist"):
        verify_sources(manifest, tmp_path / "absent")


def test_build_manifest_refusals(tmp_path: Path) -> None:
    src = tmp_path / "s"
    src.mkdir()
    good = [_source_file(src, "a.gz", "one")]
    with pytest.raises(CorpusError, match="unknown corpus mode"):
        build_manifest(mode="nope", checkout={}, sources=good, files=[], note="")
    with pytest.raises(CorpusError, match="identifies nothing"):
        build_manifest(mode="manifest", checkout={}, sources=[], files=[], note="")
    with pytest.raises(CorpusError, match="ships no files"):
        build_manifest(
            mode="manifest", checkout={}, sources=good,
            files=[{"path": "x", "sha256": "sha256:0"}], note="",
        )
    assert set(MODES) == {"manifest", "raw", "features"}


def test_unknown_schema_and_unreadable_manifest(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / MANIFEST_NAME).write_text('{"punchmark_schema": "corpus/v99"}\n')
    with pytest.raises(CorpusError, match="not a corpus/v1"):
        read_manifest(corpus)
    (corpus / MANIFEST_NAME).write_text("not json\n")
    with pytest.raises(CorpusError, match="not JSON"):
        read_manifest(corpus)
    with pytest.raises(CorpusError, match="unreadable"):
        read_manifest(tmp_path / "nowhere")
