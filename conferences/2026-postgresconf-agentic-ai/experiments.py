"""Bounded conference experiments. Synthetic vectors live outside the coffee catalog."""
from __future__ import annotations

import time
import numpy as np
from pgvector.psycopg import Vector
from db import conn

FIXTURE_ROWS = 12000
DIMENSIONS = 384
SEED = 2349
PRICE_BEAN = 'b_ethiopia_yirg'


class ExperimentConflict(ValueError):
    pass


def _schema(cur):
    cur.execute('CREATE SCHEMA IF NOT EXISTS search_lab_experiment')


def _price_table(cur):
    _schema(cur)
    cur.execute('''CREATE TABLE IF NOT EXISTS search_lab_experiment.price_demo (
        singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
        original_cents integer NOT NULL, changed_cents integer NOT NULL,
        changed_at timestamptz NOT NULL DEFAULT now()
    )''')


def price_status():
    with conn() as c, c.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute('SELECT price_cents FROM beans WHERE id=%s', (PRICE_BEAN,))
        bean = cur.fetchone()
        cur.execute("SELECT to_regclass('search_lab_experiment.price_demo')")
        saved = None
        if cur.fetchone()[0]:
            cur.execute('SELECT original_cents, changed_cents FROM search_lab_experiment.price_demo')
            saved = cur.fetchone()
    return {'active': saved is not None, 'current_cents': bean[0] if bean else None,
            'original_cents': saved[0] if saved else None, 'changed_cents': saved[1] if saved else None}


def change_price(action):
    """Durable, idempotent undo; refuse to overwrite an unrelated price edit."""
    with conn() as c, c.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '5s'")
        cur.execute('SELECT pg_advisory_xact_lock(2349, 1)')
        _price_table(cur)
        cur.execute('SELECT price_cents FROM beans WHERE id=%s FOR UPDATE', (PRICE_BEAN,))
        row = cur.fetchone()
        if row is None:
            raise ExperimentConflict('Yirgacheffe is missing from this catalog.')
        current = row[0]
        cur.execute('SELECT original_cents, changed_cents FROM search_lab_experiment.price_demo')
        saved = cur.fetchone()
        if action == 'raise':
            if saved:
                if current != saved[1]:
                    raise ExperimentConflict('The price changed outside this demo. Restore it manually before continuing.')
            else:
                if current != 1900:
                    raise ExperimentConflict('This example expects the original $19 price. No price was changed.')
                cur.execute('INSERT INTO search_lab_experiment.price_demo (original_cents,changed_cents) VALUES (%s,2400)', (current,))
                cur.execute('UPDATE beans SET price_cents=2400 WHERE id=%s', (PRICE_BEAN,))
        elif action == 'restore':
            if saved:
                if current != saved[1]:
                    raise ExperimentConflict('The price changed outside this demo. Undo stopped to preserve that edit.')
                cur.execute('UPDATE beans SET price_cents=%s WHERE id=%s', (saved[0], PRICE_BEAN))
                cur.execute('DELETE FROM search_lab_experiment.price_demo')
        else:
            raise ValueError('Unknown price action')
    return price_status()


def fixture_status():
    with conn() as c, c.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute("SELECT to_regclass('search_lab_experiment.points'), to_regclass('search_lab_experiment.points_hnsw')")
        table, index = cur.fetchone()
        count = 0
        if table:
            cur.execute('SELECT count(*) FROM search_lab_experiment.points')
            count = cur.fetchone()[0]
    return {'ready': bool(index) and count == FIXTURE_ROWS, 'rows': count,
            'target_rows': FIXTURE_ROWS, 'dimensions': DIMENSIONS, 'seed': SEED,
            'data_kind': 'Synthetic random vectors; not coffee embeddings or a relevance benchmark.'}


def prepare_fixture():
    start = time.perf_counter()
    with conn() as c, c.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '120s'")
        cur.execute('SELECT pg_advisory_xact_lock(2349, 2)')
        _schema(cur)
        cur.execute('''CREATE TABLE IF NOT EXISTS search_lab_experiment.points (
            id integer PRIMARY KEY, category integer NOT NULL, embedding vector(384) NOT NULL
        )''')
        cur.execute('SELECT count(*) FROM search_lab_experiment.points')
        count = cur.fetchone()[0]
        if count not in (0, FIXTURE_ROWS):
            raise ExperimentConflict('The experiment fixture has unexpected rows; no data was replaced.')
        if count == 0:
            rng = np.random.default_rng(SEED)
            vectors = rng.standard_normal((FIXTURE_ROWS, DIMENSIONS)).astype(np.float32)
            vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
            with cur.copy('COPY search_lab_experiment.points (id, category, embedding) FROM STDIN') as copy:
                for i, vector in enumerate(vectors):
                    copy.write_row((i + 1, i % 20, Vector(vector)))
        cur.execute('''CREATE INDEX IF NOT EXISTS points_hnsw ON search_lab_experiment.points
            USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)''')
        cur.execute('ANALYZE search_lab_experiment.points')
    return {**fixture_status(), 'prepare_ms': round((time.perf_counter()-start)*1000, 2)}


def _index_names(plan):
    names = [plan['Index Name']] if 'Index Name' in plan else []
    for child in plan.get('Plans', []):
        names.extend(_index_names(child))
    return names


def compare_indexes(*, filtered=True, ef_search=40, iterative=False):
    if not fixture_status()['ready']:
        raise ExperimentConflict('Prepare the separate indexing fixture first.')
    # A different seed keeps the query independent of every indexed vector.
    vector = np.random.default_rng(SEED + 1).standard_normal(DIMENSIONS).astype(np.float32)
    vector /= np.linalg.norm(vector)
    sql = '''SELECT id, embedding <=> %(vector)s::vector AS distance
FROM search_lab_experiment.points
WHERE TRUE''' + (' AND category = 7' if filtered else '') + '''
ORDER BY embedding <=> %(vector)s::vector
LIMIT 20'''
    params = {'vector': Vector(vector)}
    methods = {}
    with conn() as c, c.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        cur.execute("SET LOCAL statement_timeout = '15s'")
        cur.execute('SET LOCAL max_parallel_workers_per_gather = 0')
        # Explicitly compare execution strategies; these are not planner defaults.
        for name in ('exact', 'hnsw'):
            cur.execute('SET LOCAL enable_indexscan = ' + ('off' if name == 'exact' else 'on'))
            cur.execute('SET LOCAL enable_bitmapscan = off')
            cur.execute('SET LOCAL enable_seqscan = ' + ('on' if name == 'exact' else 'off'))
            if name == 'hnsw':
                cur.execute("SELECT set_config('hnsw.ef_search', %s, true)", (str(ef_search),))
                cur.execute("SELECT set_config('hnsw.iterative_scan', %s, true)", ('strict_order' if iterative else 'off',))
            start = time.perf_counter()
            cur.execute(sql, params)
            rows = [{'id': row[0], 'distance': float(row[1])} for row in cur.fetchall()]
            elapsed = (time.perf_counter()-start)*1000
            cur.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + sql, params)
            plan = cur.fetchone()[0][0]
            methods[name] = {'rows': rows, 'query_ms': round(elapsed, 2), 'plan': plan,
                             'indexes': _index_names(plan['Plan'])}
    actual_hnsw = 'points_hnsw' in methods['hnsw']['indexes']
    exact_ids = {row['id'] for row in methods['exact']['rows']}
    ann_ids = {row['id'] for row in methods['hnsw']['rows']}
    return {**methods, 'recovered': len(exact_ids & ann_ids), 'reference_count': len(exact_ids),
            'recall': len(exact_ids & ann_ids)/len(exact_ids) if exact_ids else None,
            'hnsw_used': actual_hnsw, 'sql': sql, 'fixture_rows': FIXTURE_ROWS,
            'eligible_rows': FIXTURE_ROWS // 20 if filtered else FIXTURE_ROWS,
            'settings': {'ef_search': ef_search, 'iterative': iterative, 'filtered': filtered, 'top_k': 20},
            'measurement_note': 'One exact execution followed by one HNSW execution; warm-cache/order effects apply. SQL times include execution and fetch. Each plan is a separate second execution. Recall measures neighbor recovery, not human relevance.'}
