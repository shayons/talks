"""Validation boundaries must reject input before touching models or PostgreSQL."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app


class SearchApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_invalid_limits_and_filters_never_execute_search(self):
        cases = [
            {"query": " "}, {"query": "x" * 501},
            {"query": "coffee", "budget": -1},
            {"query": "coffee", "candidates": 0},
            {"query": "coffee", "candidates": 101},
            {"query": "coffee", "rrf_k": 0},
            {"query": "coffee", "min_cosine": 1.1},
            {"query": "coffee", "min_cosine": -1.1},
            {"query": "coffee", "roasts": ["burnt"]},
            {"query": "coffee", "origins": [""]},
            {"query": "coffee", "origins": ["a" * 101]},
        ]
        with patch('app.compare_search') as search:
            for body in cases:
                with self.subTest(body=body):
                    self.assertIn(self.client.post('/api/search', json=body).status_code, (400, 422))
            search.assert_not_called()

    def test_zero_budget_is_preserved_and_query_is_trimmed(self):
        with patch('app.compare_search', return_value={"results": []}) as search:
            response = self.client.post('/api/search', json={"query": " coffee ", "budget": 0})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(search.call_args.kwargs['budget'], 0)
            self.assertEqual(search.call_args.kwargs['query'], 'coffee')

    def test_optional_cosine_threshold_reaches_shared_search(self):
        with patch('app.compare_search', return_value={"results": []}) as search:
            self.assertEqual(self.client.post('/api/search', json={"query": "coffee", "min_cosine": 0}).status_code, 200)
            self.assertEqual(search.call_args.kwargs['min_cosine'], 0)

    def test_internal_error_details_are_not_returned(self):
        with patch('app.compare_search', side_effect=RuntimeError('private database connection detail')):
            with self.assertLogs('app', level='ERROR'):
                response = self.client.post('/api/search', json={"query": "coffee"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private database', response.text)

    def test_bad_session_id_does_not_reach_database(self):
        with patch('app.run_query') as query:
            response = self.client.post('/api/query', json={"query": "coffee", "customer_id": "u_marco", "session_id": "bad-id"})
            self.assertEqual(response.status_code, 422)
            query.assert_not_called()
