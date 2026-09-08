"""Conference boundaries; optional write tests require a dedicated disposable DB."""
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import psycopg
from pgvector.psycopg import register_vector
from fastapi.testclient import TestClient
from app import app
from search import headline_parts
import experiments


class ConferenceBoundaryTests(unittest.TestCase):
    def test_highlight_tokens_preserve_text_without_trusting_markup(self):
        parts = headline_parts('<img src=x onerror=bad()> \x01bergamot\x02 & honey')
        self.assertEqual(''.join(p['text'] for p in parts), '<img src=x onerror=bad()> bergamot & honey')
        self.assertEqual([p['text'] for p in parts if p['highlight']], ['bergamot'])
        self.assertEqual(headline_parts(None), [])

    def test_stage_mutations_are_disabled_by_default(self):
        with patch.dict(os.environ, {'ENABLE_STAGE_CONTROLS':'0'}), patch('app.change_price') as change:
            response=TestClient(app).post('/api/experiments/price',json={'action':'raise'})
        self.assertEqual(response.status_code,403)
        change.assert_not_called()

    def test_cross_origin_and_invalid_requests_never_mutate(self):
        client=TestClient(app)
        with patch.dict(os.environ, {'ENABLE_STAGE_CONTROLS':'1'}), patch('app.change_price') as change:
            self.assertEqual(client.post('/api/experiments/price',json={'action':'raise'},headers={'Origin':'https://elsewhere.test'}).status_code,403)
            self.assertEqual(client.post('/api/experiments/price',json={'action':'delete'}).status_code,422)
            self.assertEqual(client.post('/api/experiments/price',content='{"action":"raise"}',headers={'Content-Type':'text/plain'}).status_code,422)
            change.assert_not_called()
        with patch('app.compare_indexes') as compare:
            for ef in [0,19,401]:
                self.assertEqual(client.post('/api/experiments/index/compare',json={'ef_search':ef}).status_code,422)
            compare.assert_not_called()


@unittest.skipUnless(os.getenv('EXPERIMENT_TEST_DATABASE_URL'), 'requires a disposable seeded database, never the rehearsal DB')
class ConferencePostgresTests(unittest.TestCase):
    @contextmanager
    def connection(self):
        with psycopg.connect(os.environ['EXPERIMENT_TEST_DATABASE_URL']) as c:
            register_vector(c)
            yield c

    def setUp(self):
        self.patch=patch('experiments.conn',self.connection)
        self.patch.start(); self.addCleanup(self.patch.stop)
        with self.connection() as c:
            c.execute("UPDATE beans SET price_cents=1900 WHERE id='b_ethiopia_yirg'")
        # Owned, disposable test DB only; repair the test's deliberately external edit.
        experiments.change_price('restore')

    def test_price_change_is_idempotent_and_survives_new_connections(self):
        with self.connection() as c:
            before=c.execute("SELECT embedding::text, in_stock FROM beans WHERE id='b_ethiopia_yirg'").fetchone()
        self.assertEqual(experiments.change_price('raise')['current_cents'],2400)
        self.assertEqual(experiments.change_price('raise')['original_cents'],1900)
        self.assertTrue(experiments.price_status()['active'])
        self.assertEqual(experiments.change_price('restore')['current_cents'],1900)
        self.assertFalse(experiments.change_price('restore')['active'])
        with self.connection() as c:
            self.assertEqual(c.execute("SELECT embedding::text, in_stock FROM beans WHERE id='b_ethiopia_yirg'").fetchone(),before)

    def test_undo_refuses_to_overwrite_an_unrelated_price_edit(self):
        experiments.change_price('raise')
        try:
            with self.connection() as c:
                c.execute("UPDATE beans SET price_cents=2600 WHERE id='b_ethiopia_yirg'")
            with self.assertRaises(experiments.ExperimentConflict):
                experiments.change_price('restore')
            self.assertEqual(experiments.price_status()['current_cents'],2600)
        finally:
            with self.connection() as c:
                c.execute("UPDATE beans SET price_cents=2400 WHERE id='b_ethiopia_yirg'")
            experiments.change_price('restore')

    def test_index_fixture_is_separate_and_recall_matches_neighbor_intersection(self):
        with self.connection() as c:
            before=c.execute('SELECT id,price_cents,embedding::text FROM beans ORDER BY id').fetchall()
        self.assertTrue(experiments.prepare_fixture()['ready'])
        self.assertTrue(experiments.prepare_fixture()['ready'])
        result=experiments.compare_indexes(filtered=True,ef_search=100,iterative=True)
        self.assertTrue(result['hnsw_used'])
        exact={r['id'] for r in result['exact']['rows']}
        approximate={r['id'] for r in result['hnsw']['rows']}
        self.assertEqual(len(exact),20)
        self.assertEqual(result['recovered'],len(exact & approximate))
        self.assertEqual(result['recall'],len(exact & approximate)/20)
        self.assertLessEqual(len(approximate),20)
        with self.connection() as c:
            self.assertEqual(c.execute('SELECT id,price_cents,embedding::text FROM beans ORDER BY id').fetchall(),before)
