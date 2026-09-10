"""Public catalog boundaries, with optional read-only PostgreSQL verification."""
import os
import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import psycopg
import numpy as np
from fastapi.testclient import TestClient
from pgvector.psycopg import register_vector
from app import app
import catalog


class CatalogApiTests(unittest.TestCase):
    def test_walkthrough_validates_query_and_hides_internal_errors(self):
        client = TestClient(app)
        with patch('app.embedding_snapshot', return_value={'products': [], 'query': 'coffee'}) as snapshot:
            response = client.post('/api/search/walkthrough', json={'query': ' coffee '})
            self.assertEqual(response.status_code, 200)
            snapshot.assert_called_once_with('coffee')
            for query in ['', '   ', 'q' * 501]:
                self.assertIn(client.post('/api/search/walkthrough', json={'query': query}).status_code, [400, 422])
        with patch('app.embedding_snapshot', side_effect=RuntimeError('private connection')):
            with self.assertLogs('app', level='ERROR'):
                response = client.post('/api/search/walkthrough', json={'query': 'coffee'})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private connection', response.text)

    def test_unknown_coffee_is_a_404_and_errors_hide_internal_details(self):
        client = TestClient(app)
        with patch('app.read_catalog', return_value=None):
            self.assertEqual(client.get('/api/catalog/missing').status_code, 404)
        with patch('app.read_catalog', side_effect=RuntimeError('private connection details')):
            with self.assertLogs('app', level='ERROR'):
                response = client.get('/api/catalog')
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private connection', response.text)

    def test_all_four_page_paths_serve_the_app(self):
        client = TestClient(app)
        for path in ['/', '/catalog', '/experiments', '/concierge']:
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('/static/site.js', response.text)


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'set TEST_DATABASE_URL for read-only catalog tests')
class CatalogPostgresTests(unittest.TestCase):
    @contextmanager
    def connection(self):
        with psycopg.connect(os.environ['TEST_DATABASE_URL']) as connection:
            register_vector(connection)
            yield connection

    def test_list_and_detail_agree_with_canonical_rows_and_keep_context_private(self):
        with patch.object(catalog, 'conn', self.connection):
            result = catalog.read_catalog()
            self.assertLessEqual(len(result['products']), 200)
            for product in result['products']:
                self.assertNotIn('embedding', product)
                detail = catalog.read_catalog(product['id'])
                for field in catalog.PRODUCT_FIELDS:
                    self.assertEqual(detail[field], product[field])
                self.assertEqual(len(detail['embedding'] or []), product['embedding_dimensions'] or 0)
                self.assertEqual(set(detail), set(catalog.PRODUCT_FIELDS) | {
                    'currency', 'image_url', 'description', 'search_document', 'weighted_fields', 'embedding', 'embedding_model'})
            self.assertIsNone(catalog.read_catalog("x' OR true --"))

    def test_walkthrough_reads_bounded_canonical_vectors(self):
        query = [np.float32(1)] + [np.float32(0)] * 383
        with patch.object(catalog, 'conn', self.connection), patch.object(catalog, 'embed', return_value=query):
            result = catalog.embedding_snapshot('bergamot')
            self.assertEqual(result['query_embedding'], query)
            json.dumps(result)  # FastEmbed's numpy scalars must become JSON numbers.
            self.assertLessEqual(len(result['products']), 48)
            for product in result['products']:
                detail = catalog.read_catalog(product['id'])
                self.assertEqual(set(product), {'id', 'name', 'embedding'})
                self.assertEqual(product['embedding'], detail['embedding'])
                self.assertEqual(product['name'], detail['name'])
