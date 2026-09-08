from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import mcp_server


class _DataApiClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def begin_transaction(self, **kwargs):
        self.calls.append(("begin", kwargs))
        return {"transactionId": "tx-1"}

    def execute_statement(self, **kwargs):
        self.calls.append(("execute", kwargs))
        if kwargs["sql"] == "SET TRANSACTION READ ONLY":
            return {}
        return {
            "columnMetadata": [{"name": "id"}, {"name": "notes"}],
            "records": [
                [
                    {"longValue": 7},
                    {"arrayValue": {"stringValues": ["floral", "citrus"]}},
                ]
            ],
        }

    def rollback_transaction(self, **kwargs):
        self.calls.append(("rollback", kwargs))
        return {}


class QuerySafetyTests(unittest.TestCase):
    def test_rejects_relations_hidden_in_comma_joins_and_subqueries(self):
        for sql in (
            "SELECT b.id FROM beans b, pg_authid a",
            "SELECT * FROM beans b, (SELECT * FROM pg_authid) a",
            "SELECT (SELECT count(*) FROM pg_catalog.pg_authid) FROM beans",
            "SELECT * FROM beans UNION ALL SELECT * FROM pg_authid",
        ):
            with self.subTest(sql=sql):
                self.assertIsNone(mcp_server._normalized_select(sql)[0])

    def test_rejects_unapproved_functions_and_invalid_input(self):
        for sql in (
            "SELECT pg_ls_logdir() FROM beans",
            "SELECT set_config('search_path','public',false) FROM beans",
            "SELECT public.custom_side_effect() FROM beans",
            "SELECT pg_sleep(1000)", None, 42,
        ):
            with self.subTest(sql=sql):
                self.assertIsNone(mcp_server._normalized_select(sql)[0])

    def test_parameters_and_allowed_comma_joins_still_work(self):
        sql = "SELECT b.name FROM beans b, orders o WHERE o.bean_id=b.id AND b.price_cents <= %s"
        self.assertEqual(mcp_server._normalized_select(sql), (sql, "ok"))

    def test_allows_single_select_over_allowlisted_tables(self) -> None:
        sql, reason = mcp_server._normalized_select(
            "SELECT b.id FROM public.beans b JOIN orders o ON o.bean_id=b.id;"
        )
        self.assertEqual(reason, "ok")
        self.assertTrue(sql.startswith("SELECT"))

    def test_ignores_keywords_and_semicolons_inside_string_literals(self) -> None:
        sql, reason = mcp_server._normalized_select(
            "SELECT 'delete; still text' AS message FROM beans"
        )
        self.assertEqual(reason, "ok")
        self.assertIsNotNone(sql)

    def test_rejects_non_allowlisted_table(self) -> None:
        sql, reason = mcp_server._normalized_select(
            "SELECT * FROM pg_catalog.pg_authid"
        )
        self.assertIsNone(sql)
        self.assertIn("allowlist", reason)

    def test_rejects_write_keywords_comments_and_unsafe_functions(self) -> None:
        cases = [
            "SELECT * INTO copied_beans FROM beans",
            "SELECT * FROM beans -- hide a second statement",
            "SELECT pg_read_file('/etc/passwd')",
            "DELETE FROM beans",
        ]
        for candidate in cases:
            with self.subTest(candidate=candidate):
                sql, _reason = mcp_server._normalized_select(candidate)
                self.assertIsNone(sql)


class DataApiTests(unittest.TestCase):
    def test_rewrites_only_real_positional_parameters(self) -> None:
        sql, params = mcp_server._rewrite_positional_params(
            "SELECT '%s literal', id FROM beans WHERE id=%s AND price_cents>%s",
            ["b_1", 1000],
        )
        self.assertEqual(
            sql,
            "SELECT '%s literal', id FROM beans WHERE id=:p0 AND price_cents>:p1",
        )
        self.assertEqual(params[0]["value"], {"stringValue": "b_1"})
        self.assertEqual(params[1]["value"], {"longValue": 1000})

    def test_rejects_parameter_count_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected 1"):
            mcp_server._rewrite_positional_params(
                "SELECT id FROM beans WHERE id=%s",
                [],
            )

    def test_rejects_array_parameters_in_data_api_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not support array"):
            mcp_server._to_data_api_param("p0", ["a", "b"])

    def test_data_api_query_runs_in_rolled_back_read_only_transaction(self) -> None:
        client = _DataApiClient()
        with (
            patch.dict(
                os.environ,
                {
                    "AURORA_CLUSTER_ARN": "arn:cluster",
                    "AURORA_SECRET_ARN": "arn:secret",
                    "AURORA_DATABASE": "coffee",
                },
                clear=False,
            ),
            patch.object(mcp_server, "_data_api_client", return_value=client),
        ):
            result = mcp_server._run_query_data_api(
                "SELECT id, flavor_notes FROM beans WHERE id=%s",
                ["b_1"],
            )

        self.assertEqual(result["columns"], ["id", "notes"])
        self.assertEqual(result["rows"], [[7, ["floral", "citrus"]]])
        self.assertEqual([name for name, _ in client.calls], [
            "begin",
            "execute",
            "execute",
            "rollback",
        ])
        self.assertEqual(
            client.calls[1][1]["sql"],
            "SET TRANSACTION READ ONLY",
        )
        self.assertEqual(client.calls[-1][1]["transactionId"], "tx-1")

    def test_run_query_caps_rows_and_reports_truncation(self) -> None:
        rows = [[index] for index in range(mcp_server.MAX_ROWS + 1)]
        with patch.object(
            mcp_server,
            "_execute_select",
            return_value={"columns": ["id"], "rows": rows},
        ) as execute:
            result = mcp_server.tool_run_query(
                {"sql": "SELECT id FROM beans ORDER BY id"}
            )

        self.assertEqual(len(result["rows"]), mcp_server.MAX_ROWS)
        self.assertTrue(result["truncated"])
        self.assertIn("LIMIT 101", execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
