from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

import agents


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executed: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True


def _conn_factory(cursor):
    @contextmanager
    def _conn():
        yield _Connection(cursor)

    return _conn


class SessionBoundaryTests(unittest.TestCase):
    def test_rejects_session_owned_by_another_customer(self) -> None:
        cursor = _Cursor([("session-1", "u_marco")])
        with patch.object(agents, "conn", _conn_factory(cursor)):
            with self.assertRaises(agents.SessionCustomerMismatchError):
                agents.ensure_session("session-1", "u_ana")
        self.assertEqual(len(cursor.executed), 1)

    def test_rejects_unknown_customer_before_insert(self) -> None:
        cursor = _Cursor([None])
        with patch.object(agents, "conn", _conn_factory(cursor)):
            with self.assertRaises(agents.UnknownCustomerError):
                agents.ensure_session(None, "u_missing")
        self.assertEqual(len(cursor.executed), 1)


if __name__ == "__main__":
    unittest.main()
