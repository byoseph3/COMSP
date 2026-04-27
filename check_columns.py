import psycopg2
from main import load_env, make_connection_params

env = load_env()
conn = psycopg2.connect(**make_connection_params(env))
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users' AND (column_name LIKE '%Alpha%' OR column_name LIKE '%Omega%')")
cols = [row[0] for row in cur.fetchall()]
print("Columns found:")
for c in cols:
    print(f"  - {c}")