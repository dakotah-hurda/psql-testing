import os
import psycopg

PG_USER = os.environ.get("PG_USER")
PG_PASS = os.environ.get("PG_PASS")
HOSTNAME = "localhost"
PORT = "5432"
DB_NAME = "routers"
SEED_IP = "172.16.1.3"

with psycopg.connect(f"postgresql://{PG_USER}:{PG_PASS}@{HOSTNAME}:{PORT}/{DB_NAME}") as conn:

    # Open a cursor to perform database operations
    with conn.cursor() as cur:

        # Execute a command: this creates a new table
        cur.execute("SELECT (ip, discovered_state) FROM inventory;")

        rows = cur.fetchall()

        for row in rows:
            if row[0][1] != 't':
                print(f"Row isn't discovered yet: {row[0]}")        
            else:
                print(f"Row HAS been discovered: {row[0]}")