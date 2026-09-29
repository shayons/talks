"""Check everything the talk uses: the four datasets, the UI's stage questions, and Bedrock.

Run through scripts/preflight.sh, which first starts the database and the UI. Prints one line
per check and exits 1 if anything the stage depends on is broken. Bedrock is only needed for
questions typed live, so a Bedrock failure is a warning, not an error.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

from hybrid_lab import bedrock, questions
from hybrid_lab.db import connect

UI = "http://127.0.0.1:8018"
DATASETS = ("fiqa", "scifact", "nfcorpus", "scidocs")
STAGE_DATASETS = DATASETS
VS_CODE_QUESTION = ("fiqa", "4641")

DATASET_SQL = """
SELECT (SELECT count(*) FROM docs),
       (SELECT count(embedding) FROM docs),
       (SELECT count(embedding_local) FROM docs),
       (SELECT count(*) FROM docs WHERE body ~ '^\\s*$'),
       (SELECT count(*) FROM queries WHERE split = 'test'),
       (SELECT count(*) FROM scoreboard),
       (SELECT count(*) FROM demo_questions)
"""


def report(ok: bool, label: str, detail: str) -> bool:
    """Print one check's result and return whether it passed."""
    print(f"  {'✓' if ok else '✗'} {label}: {detail}")
    return ok


def check_dataset(name: str) -> bool:
    """Every document with text is embedded by both models, and results are in place."""
    try:
        with connect(name) as conn:
            docs, v4, local, empty, tests, methods, stage = conn.execute(DATASET_SQL).fetchone()
    except Exception as exc:  # noqa: BLE001 - any failure here is reported, not raised
        return report(False, name, f"cannot read it ({exc}); run scripts/setup.sh")
    with_text = docs - empty
    problems = []
    if v4 != with_text or local != with_text:
        problems.append(f"embeddings incomplete (Embed v4 {v4:,}, bge-small {local:,} of "
                        f"{with_text:,}); run py/2_embed.py and py/2b_embed_local.py")
    if not methods:
        problems.append("no scoreboard; run scripts/evaluate_all.sh")
    if name in STAGE_DATASETS and stage < 4:
        problems.append(f"{stage} stage questions; run sql/demo_questions.sql")
    detail = "; ".join(problems) or (
        f"{with_text:,} documents embedded, {tests:,} test questions, {methods} methods scored"
        + (f", {stage} stage questions" if name in STAGE_DATASETS else ""))
    return report(not problems, name, detail)


def _get(path: str) -> object:
    with urllib.request.urlopen(UI + path, timeout=30) as response:
        return json.load(response)


def _post(path: str, body: dict) -> dict:
    request = urllib.request.Request(UI + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def check_stage_questions(name: str) -> bool:
    """Run every stage question through the UI with its default methods, as on stage."""
    try:
        methods = [arm["stage"] for arm in _get(f"/api/arms?dataset={name}")
                   if arm["default_on"] and arm["available"]]
        demo = _get(f"/api/questions?dataset={name}")["demo"]
        started = time.perf_counter()
        for item in demo:
            result = _post("/api/search", {"question_id": item["id"], "arms": methods,
                                           "dataset": name})
            graded = [card for card in result["arms"] if card["ndcg10"] is not None]
            if len(graded) != len(methods):
                return report(False, f"UI ({name})", f"'{item['label']}' came back incomplete")
    except (urllib.error.URLError, KeyError, TimeoutError) as exc:
        return report(False, f"UI ({name})", f"{exc}; is `uv run hybrid-lab` running?")
    seconds = time.perf_counter() - started
    labels = ", ".join(item["label"] for item in demo)
    detail = f"{len(demo)} stage questions in {seconds:.1f} s ({labels})"
    return report(True, f"UI ({name})", detail)


def check_bedrock() -> None:
    """One small embedding call; a failure only matters for questions typed live."""
    try:
        bedrock.embed_query("preflight check")
        report(True, "Bedrock", "Embed v4 answered; typed questions will work")
    except bedrock.BedrockError as exc:
        print(f"  ! Bedrock: {exc}\n    Stage questions still work. Typed questions will not.")


def set_vs_code_question() -> bool:
    """Make the rainy-day question active, so the SQL files run as soon as VS Code opens."""
    name, question_id = VS_CODE_QUESTION
    try:
        with connect(name) as conn:
            questions.use(conn, question_id)
            _, body = questions.active(conn)
    except Exception as exc:  # noqa: BLE001 - reported to the presenter
        return report(False, "VS Code question", str(exc))
    return report(True, "VS Code question", f"{name} {question_id}: {body}")


def main() -> int:
    """Run every check; return 1 if anything the stage depends on failed."""
    print("Datasets")
    ok = all([check_dataset(name) for name in DATASETS])
    print("UI")
    ok = all([check_stage_questions(name) for name in STAGE_DATASETS]) and ok
    print("VS Code")
    ok = set_vs_code_question() and ok
    print("Bedrock (typed questions only)")
    check_bedrock()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
