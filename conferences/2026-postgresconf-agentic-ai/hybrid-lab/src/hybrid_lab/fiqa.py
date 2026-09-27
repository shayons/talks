"""Download and read BEIR's FiQA-2018 distribution using only the standard library."""

from __future__ import annotations

import hashlib
import json
import urllib.request
import zipfile
from collections.abc import Iterator
from pathlib import Path

from hybrid_lab.db import LAB_ROOT

URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/fiqa.zip"
SHA256 = "32c7df99ed21252fdfb2cf3f5673502a8d245ee0c44c4a133570d92ce2b3ad02"
DATA_DIR = LAB_ROOT / "data"


def download(path: Path = DATA_DIR / "fiqa.zip") -> Path:
    """Download the FiQA archive once and verify its checksum.

    Raises:
        RuntimeError: If the downloaded file does not match the published archive.
    """
    if not path.exists() or _sha256(path) != SHA256:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".partial")
        urllib.request.urlretrieve(URL, partial)  # noqa: S310 - fixed https URL
        partial.replace(path)
    if _sha256(path) != SHA256:
        raise RuntimeError(f"{path} does not match the BEIR FiQA archive; delete it and retry.")
    return path


def corpus(archive: Path) -> Iterator[tuple[str, str]]:
    """Yield (doc_id, body) for every FiQA post. FiQA titles are always empty."""
    for row in _jsonl(archive, "fiqa/corpus.jsonl"):
        yield row["_id"], row["text"]


def questions(archive: Path) -> dict[str, str]:
    """Return every FiQA question text by id (train, dev, and test)."""
    return {row["_id"]: row["text"] for row in _jsonl(archive, "fiqa/queries.jsonl")}


def test_qrels(archive: Path) -> list[tuple[str, str, int]]:
    """Return (query_id, doc_id, relevance) for the 648-question test split."""
    with zipfile.ZipFile(archive) as zf:
        lines = zf.read("fiqa/qrels/test.tsv").decode().splitlines()
    rows = [line.split("\t") for line in lines[1:] if line.strip()]
    return [(query_id, doc_id, int(score)) for query_id, doc_id, score in rows]


def _jsonl(archive: Path, member: str) -> Iterator[dict]:
    with zipfile.ZipFile(archive) as zf, zf.open(member) as handle:
        for line in handle:
            yield json.loads(line)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
