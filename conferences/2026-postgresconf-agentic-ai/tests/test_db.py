from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import db


class _SecretsClient:
    def get_secret_value(self, **_kwargs):
        return {
            "SecretString": (
                '{"username":"coffee user","password":"p@ss/word+with space"}'
            )
        }


class DatabaseConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        db.database_url.cache_clear()

    def test_local_database_url_does_not_contact_secrets_manager(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "DEMO_MODE": "local",
                    "DATABASE_URL": "postgresql://local/demo",
                },
                clear=False,
            ),
            patch("boto3.client") as boto_client,
        ):
            db.database_url.cache_clear()
            self.assertEqual(db.database_url(), "postgresql://local/demo")
            boto_client.assert_not_called()

    def test_aurora_database_url_is_lazy_and_percent_encodes_credentials(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "DEMO_MODE": "aurora",
                    "AWS_REGION": "us-east-1",
                    "AURORA_CLUSTER_ENDPOINT": "coffee.example.com",
                    "AURORA_SECRET_ARN": "arn:aws:secretsmanager:region:acct:secret:x",
                    "AURORA_DATABASE": "coffee",
                    "AURORA_PORT": "5432",
                },
                clear=False,
            ),
            patch("boto3.client", return_value=_SecretsClient()),
        ):
            db.database_url.cache_clear()
            self.assertEqual(
                db.database_url(),
                "postgresql://coffee%20user:p%40ss%2Fword%2Bwith%20space"
                "@coffee.example.com:5432/coffee?sslmode=require",
            )

    def test_invalid_demo_mode_fails_closed(self) -> None:
        with patch.dict(os.environ, {"DEMO_MODE": "maybe"}, clear=False):
            with self.assertRaisesRegex(ValueError, "DEMO_MODE"):
                db.demo_mode()


if __name__ == "__main__":
    unittest.main()
