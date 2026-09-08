from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

import agents


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.executed = (sql, params)

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class _Context:
    query = "bergamot under $20"

    def __init__(self):
        self.panels = []

    def emit_panel(self, **panel):
        self.panels.append(panel)


class HybridSearchTests(unittest.TestCase):
    def test_fuses_semantic_and_lexical_ranks(self) -> None:
        rows = [
            (
                "b_ethiopia_yirg",
                "Ethiopia Yirgacheffe",
                "medium-light",
                "washed",
                ["jasmine", "lemon", "bergamot", "honey"],
                1900,
                42,
                "Yirgacheffe, Ethiopia",
                0.72,
                3,
                0.41,
                1,
                0.18,
                0.0323,
                True,
                "Floral coffee with bergamot.",
            )
        ]
        cursor = _Cursor(rows)

        @contextmanager
        def fake_conn():
            yield _Connection(cursor)

        ctx = _Context()
        intent = {"brew_method": None, "budget_cents": 2000}
        with (
            patch.object(agents, "embed", return_value=[0.0] * 384),
            patch.object(agents, "conn", fake_conn),
        ):
            candidates = agents.FlavorProfilerAgent().profile(ctx, intent, [])

        sql, params = cursor.executed
        self.assertIn("websearch_to_tsquery", sql)
        self.assertIn("search_document", sql)
        self.assertIn("rrf_score", sql)
        self.assertEqual(params["query"], "bergamot")
        self.assertEqual(params["budget"], 2000)
        self.assertTrue(params["stock_only"])
        self.assertEqual(candidates[0]["semantic_rank"], 3)
        self.assertEqual(candidates[0]["lexical_rank"], 1)
        self.assertAlmostEqual(candidates[0]["hybrid_score"], 0.0323)
        self.assertTrue(candidates[0]["text_match"])
        self.assertEqual(ctx.panels[0]["tag"], "RETRIEVAL · HYBRID RRF")


if __name__ == "__main__":
    unittest.main()
