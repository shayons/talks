"""Initialize an empty take-home database; never reseed an existing catalog."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import psycopg
from db import database_url, close_pool
from seed import main as seed_demo


def initialize():
    # The ordinary pool registers vector types, which do not exist before setup.
    with psycopg.connect(database_url()) as c:
        tables = c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()
        if tables:
            if not any(row[0] == 'beans' for row in tables):
                raise RuntimeError('Database is not empty and has no coffee catalog. Initialization stopped.')
            count = c.execute('SELECT count(*) FROM beans').fetchone()[0]
            if count:
                print(f'Keeping the existing {count}-bean catalog and conversation history.')
                return
            # Recover only a fully empty schema left after interrupted first-time setup.
            from psycopg import sql
            for (name,) in tables:
                if c.execute(sql.SQL('SELECT EXISTS (SELECT 1 FROM public.{})').format(sql.Identifier(name))).fetchone()[0]:
                    raise RuntimeError('The database contains data. Initialization will not reseed it.')
        else:
            c.execute((ROOT/'schema.sql').read_text())
    seed_demo()


if __name__ == '__main__':
    try:
        initialize()
    finally:
        close_pool()
