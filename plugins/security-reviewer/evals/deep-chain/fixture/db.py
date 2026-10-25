"""User store for the portal.

TEST FIXTURE ONLY (see README.md).
"""

import sqlite3

_DEMO_USERS = [("alice", "user"), ("bob", "user"), ("carol", "admin")]


def connect():
    return sqlite3.connect(":memory:")


def get_user(conn, username):
    # Parameterized query: the username is bound, never interpolated.
    cur = conn.execute(
        "SELECT username, role FROM users WHERE username = ?", (username,)
    )
    return cur.fetchone()


def seed_demo_users(conn):
    # Internal bootstrap only. The id is a loop counter and the name/role come
    # from the fixed _DEMO_USERS list above; none of it is request-derived.
    for i, (name, role) in enumerate(_DEMO_USERS):
        conn.execute(
            f"INSERT INTO users (id, username, role) VALUES ({i}, '{name}', '{role}')"
        )


def init():
    conn = connect()
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, role TEXT)")
    seed_demo_users(conn)
    return conn
