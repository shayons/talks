"""Download and read BEIR benchmark datasets using only the standard library.

Every BEIR dataset ships the same way: corpus.jsonl (documents), queries.jsonl (questions
from all splits), and qrels/<split>.tsv (which documents answer which question).
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
import zipfile
from collections.abc import Iterator
from pathlib import Path

from hybrid_lab.db import LAB_ROOT

BASE_URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets"
DATA_DIR = LAB_ROOT / "data"

# Datasets the lab supports, with the SHA-256 of the archive we measured. FiQA is the
# paraphrase-heavy main example. The other three were chosen before any measurement by one
# rule: under 30,000 documents, and BM25 beat every dense retriever in the BEIR paper.
DATASETS = {
    "fiqa": "32c7df99ed21252fdfb2cf3f5673502a8d245ee0c44c4a133570d92ce2b3ad02",
    "scifact": "536e14446a0ba56ed1398ab1055f39fe852686ecad24a6306c80c490fa8e0165",
    "nfcorpus": "efe5be03f8c5b86a5870102d0599d227c8c6e2484328e68c6522560385671b0b",
    "scidocs": "96640201687767c9b1fcc5af7a80b90fb325b37fa25329c2586c25edcfa17ef1",
}


def download(name: str) -> Path:
    """Download a BEIR archive once and verify its checksum.

    Raises:
        KeyError: For a dataset the lab does not know.
        RuntimeError: If the file does not match the published archive.
    """
    expected = DATASETS[name]
    path = DATA_DIR / f"{name}.zip"
    if not path.exists() or _sha256(path) != expected:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".partial")
        urllib.request.urlretrieve(f"{BASE_URL}/{name}.zip", partial)  # noqa: S310 - fixed https
        partial.replace(path)
    if _sha256(path) != expected:
        raise RuntimeError(f"{path} does not match the BEIR {name} archive; delete it and retry.")
    return path


def corpus(archive: Path) -> Iterator[tuple[str, str]]:
    """Yield (doc_id, body). The body is the title and text joined, when there is a title."""
    for row in _jsonl(archive, "corpus.jsonl"):
        title, text = row.get("title") or "", row.get("text") or ""
        yield row["_id"], f"{title}\n\n{text}" if title else text


def questions(archive: Path) -> dict[str, str]:
    """Return every question's text by id, across all splits."""
    return {row["_id"]: row["text"] for row in _jsonl(archive, "queries.jsonl")}


def splits(archive: Path) -> list[str]:
    """Return the qrels splits present, for example ['dev', 'test', 'train']."""
    with zipfile.ZipFile(archive) as zf:
        return sorted(Path(n).stem for n in zf.namelist() if "/qrels/" in n and n.endswith(".tsv"))


def qrels(archive: Path, split: str) -> list[tuple[str, str, int]]:
    """Return (query_id, doc_id, relevance) for one split, keeping only relevance > 0.

    Some datasets list judged non-relevant pairs with relevance 0; NDCG gives them no credit,
    so they carry no information here.
    """
    with zipfile.ZipFile(archive) as zf:
        member = next(n for n in zf.namelist() if n.endswith(f"/qrels/{split}.tsv"))
        lines = zf.read(member).decode().splitlines()
    rows = [line.split("\t") for line in lines[1:] if line.strip()]
    return [(query_id, doc_id, int(score)) for query_id, doc_id, score in rows if int(score) > 0]


def _jsonl(archive: Path, filename: str) -> Iterator[dict]:
    with zipfile.ZipFile(archive) as zf:
        member = next(n for n in zf.namelist() if n.endswith(f"/{filename}"))
        with zf.open(member) as handle:
            for line in handle:
                yield json.loads(line)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
