"""Real SQL regressions using an isolated temporary table; no catalog writes.

TEST_DATABASE_URL=postgresql://... python -m unittest discover -s tests -v
The configured database needs vector and pg_trgm installed.
"""
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import psycopg
from pgvector.psycopg import register_vector

from search import SEARCH_SQL, EXCLUDED_SQL, result_from_row, search_params, excluded_from_row
import agents


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'set TEST_DATABASE_URL for PostgreSQL integration tests')
class PostgresSearchTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(os.environ['TEST_DATABASE_URL'])
        self.addCleanup(self.connection.close)
        register_vector(self.connection)
        self.connection.execute("""CREATE TEMP TABLE beans (
            id text PRIMARY KEY, name text, roast_level text, process text,
            flavor_notes text[], price_cents int, in_stock int, origin text,
            embedding vector(384), description text,
            search_document tsvector GENERATED ALWAYS AS (
              to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))
            ) STORED
        ) ON COMMIT DROP""")
        self.vector = [1.0] + [0.0] * 383
        for i in range(20):
            self.add_bean(f'expensive_{i:02}', 'Bergamot luxury', 5800, self.vector)
        self.add_bean('affordable', 'Ethiopia Yirgacheffe', 1900, [0.8, 0.2] + [0.0]*382)

    def add_bean(self, id, name, price, vector, stock=5, origin='Ethiopia'):
        self.connection.execute("""INSERT INTO beans
            (id,name,roast_level,process,flavor_notes,price_cents,in_stock,origin,embedding,description)
            VALUES (%s,%s,'medium-light','washed',ARRAY['bergamot'],%s,%s,%s,%s,'Floral bergamot coffee')""",
            (id,name,price,stock,origin,vector))

    def search(self, query='bergamot', **options):
        params = search_params(self.vector, query, **options)
        return [result_from_row(row) for row in self.connection.execute(SEARCH_SQL, params).fetchall()]

    def test_budget_is_applied_before_top_k_not_after(self):
        rows = self.search(budget=2000, candidates=1)
        self.assertEqual([row['id'] for row in rows], ['affordable'])
        self.assertEqual(rows[0]['semantic_rank'], 1)
        self.assertEqual(rows[0]['lexical_rank'], 1)

    def test_zero_budget_is_not_ignored(self):
        self.assertEqual(self.search(budget=0), [])

    def test_cosine_threshold_removes_only_vector_contribution(self):
        row, = self.search(budget=2000, min_cosine=0.99)
        self.assertEqual(row['id'], 'affordable')
        self.assertIsNone(row['semantic_rank'])
        self.assertEqual(row['lexical_rank'], 1)
        self.assertAlmostEqual(row['hybrid_score'], 1 / 61)
        self.assertEqual(self.search('no-word-match', budget=2000, min_cosine=0.99), [])
        self.assertEqual(self.search('no-word-match', budget=2000, min_cosine=0.9)[0]['semantic_rank'], 1)

    def test_word_match_exclusions_are_disjoint_from_eligible_results(self):
        params = search_params(self.vector, 'bergamot', budget=2000)
        rows = self.connection.execute(EXCLUDED_SQL, params).fetchall()
        excluded = [excluded_from_row(row, params) for row in rows]
        eligible = {row['id'] for row in self.search(budget=2000)}
        self.assertEqual(len(excluded),20)
        self.assertTrue(eligible.isdisjoint(row['id'] for row in excluded))
        self.assertTrue(all('$58.00 exceeds the $20.00 maximum' in row['reasons'] for row in excluded))

    def test_postgres_highlights_query_terms_and_strips_literal_markers(self):
        self.connection.execute("UPDATE beans SET description=%s WHERE id='affordable'", ('Floral bergamot \x01fake\x02 <img src=x onerror=bad()>',))
        row = next(row for row in self.search(budget=2000) if row['id']=='affordable')
        self.assertIn('bergamot', [part['text'].lower() for part in row['match_excerpt'] if part['highlight']])
        self.assertNotIn('fake', [part['text'] for part in row['match_excerpt'] if part['highlight']])

    def test_origin_miss_and_roast_miss_are_empty(self):
        self.assertEqual(self.search(origins=['Japan']), [])
        self.assertEqual(self.search(roasts=['dark']), [])
        self.assertEqual(self.search(origins=['%']), [])

    def test_out_of_stock_candidates_cannot_crowd_out_valid_rows(self):
        self.connection.execute("UPDATE beans SET in_stock=0 WHERE id <> 'affordable'")
        rows = self.search(candidates=1)
        self.assertEqual([row['id'] for row in rows], ['affordable'])
        self.assertTrue(any(row['in_stock'] == 0 for row in self.search(stock_only=False)))

    def test_fusion_matches_independent_rank_oracle_and_keeps_single_branch_rows(self):
        for k in (1, 60, 200):
            rows = self.search('Yirgacheffe', candidates=1, rrf_k=k)
            self.assertEqual(len(rows), 2)
            for row in rows:
                expected = sum(1 / (k + rank) for rank in (row['semantic_rank'],row['lexical_rank']) if rank is not None)
                self.assertAlmostEqual(row['hybrid_score'], expected)
            self.assertEqual(len({row['id'] for row in rows}), len(rows))

    def test_fuzzy_evidence_is_not_reported_as_full_text(self):
        self.connection.execute("SET LOCAL pg_trgm.similarity_threshold = 0.3")
        literal = self.search('Yirgachefe', budget=2000)
        fuzzy = self.search('Yirgachefe', budget=2000, fuzzy=True)
        self.assertIsNone(literal[0]['lexical_rank'])
        self.assertEqual(fuzzy[0]['lexical_rank'], 1)
        self.assertFalse(fuzzy[0]['text_match'])

    def test_parameter_values_cannot_change_sql_shape(self):
        rows = self.search("'; DROP TABLE beans; --", origins=["Ethiopia' OR true --"])
        self.assertEqual(rows, [])
        self.assertEqual(self.connection.execute('SELECT count(*) FROM beans').fetchone()[0], 21)

    @contextmanager
    def temporary_connection(self):
        yield self.connection

    def test_order_referent_rehydration_checks_current_eligibility(self):
        coordinator = agents.CoordinatorAgent()
        with patch.object(agents, 'conn', self.temporary_connection):
            self.assertIsNotNone(coordinator._hydrate_bean('affordable', {'budget_cents': 2000}))
            self.assertIsNone(coordinator._hydrate_bean('affordable', {'budget_cents': 1800}))
            self.connection.execute("UPDATE beans SET in_stock=0 WHERE id='affordable'")
            self.assertIsNone(coordinator._hydrate_bean('affordable'))

    def test_fact_check_drops_a_candidate_whose_price_changed(self):
        picks = self.search(budget=2000)
        self.connection.execute("UPDATE beans SET price_cents=2500 WHERE id='affordable'")
        context = agents.AgentContext('test-session', 'test-customer', 'bergamot')
        coordinator = agents.CoordinatorAgent()
        with patch.object(agents, 'conn', self.temporary_connection), patch.object(coordinator, '_synthesize', return_value='No eligible picks.'):
            coordinator._respond(context, {'budget_cents': 2000}, [], picks)
        response = next(event for event in context.events if event['type'] == 'response')
        self.assertEqual(response['citations'], [])
        self.assertEqual(response['products'], [])

    def test_product_cards_use_reverified_rows_even_when_prose_disagrees(self):
        picks = self.search(budget=2000)
        self.connection.execute("""UPDATE beans SET name='Current catalog name',
            price_cents=1950, in_stock=3, roast_level='dark' WHERE id='affordable'""")
        context = agents.AgentContext('test-session', 'test-customer', 'bergamot')
        coordinator = agents.CoordinatorAgent()
        with patch.object(agents, 'conn', self.temporary_connection), patch.object(
            coordinator, '_synthesize', return_value='Invented name, $1, light roast, 900 in stock.'
        ):
            coordinator._respond(context, {'budget_cents': 2000}, [], picks)
        response = next(event for event in context.events if event['type'] == 'response')
        self.assertEqual(len(response['products']), 1)
        product = response['products'][0]
        self.assertEqual(product['name'], 'Current catalog name')
        self.assertEqual(product['price_cents'], 1950)
        self.assertEqual(product['in_stock'], 3)
        self.assertEqual(product['image_url'], '/static/products/coffee-dark.webp')
        self.assertNotIn('embedding', product)
        self.assertEqual(response['citations'][0]['label'], product['name'])

    def test_sold_out_products_do_not_get_cards_or_citations(self):
        picks = self.search(budget=2000)
        self.connection.execute("UPDATE beans SET in_stock=0 WHERE id='affordable'")
        context = agents.AgentContext('test-session', 'test-customer', 'bergamot')
        coordinator = agents.CoordinatorAgent()
        with patch.object(agents, 'conn', self.temporary_connection), patch.object(
            coordinator, '_synthesize', return_value='No eligible picks.'
        ):
            coordinator._respond(context, {'budget_cents': 2000}, [], picks)
        response = next(event for event in context.events if event['type'] == 'response')
        self.assertEqual(response['products'], [])
        self.assertEqual(response['citations'], [])

    def test_order_card_matches_the_single_bean_queued_for_approval(self):
        picks = self.search(candidates=30)
        self.assertGreater(len(picks), 1)
        context = agents.AgentContext('test-session', 'test-customer', 'order that')
        coordinator = agents.CoordinatorAgent()
        with patch.object(agents, 'conn', self.temporary_connection), patch.object(
            coordinator, '_synthesize', return_value='Pending approval.'
        ) as synthesize, patch.object(agents, 'request_approval', return_value=42) as approve:
            coordinator._respond(context, {
                'wants_order': True, 'order_referent_bean_id': 'affordable',
            }, [], picks)
        response = next(event for event in context.events if event['type'] == 'response')
        self.assertEqual([product['id'] for product in response['products']], ['affordable'])
        self.assertEqual([cite['key'] for cite in response['citations']], ['beans.affordable'])
        self.assertEqual(approve.call_args.kwargs['args']['bean_id'], 'affordable')
        self.assertEqual(approve.call_args.kwargs['args']['qty'], 1)
        self.assertEqual([product['id'] for product in synthesize.call_args.args[3]], ['affordable'])
