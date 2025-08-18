
# database/db.py

import sqlite3 as sqlite
import psycopg2
from psycopg2 import OperationalError
import oracledb
import sys
import os
import datetime


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


# Database file path updated
DB_FILE = resource_path("databases/hierarchy.db")

# --- Database Connection Functions ---


def create_sqlite_connection(path):
    """Establishes a connection to a SQLite database."""
    try:
        conn = sqlite.connect(path)
        print("SQLite database connection established.")
        return conn
    except sqlite.Error as e:
        print(f"SQLite connection error: {e}")
        return None


def create_postgres_connection(host, port, database, user, password):
    """Establishes a connection to a PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        print("PostgreSQL database connection established.")
        return conn
    except OperationalError as e:
        print(f"PostgreSQL connection error: {e}")
        return None


def create_oracle_connection(host, port, service_name, user, password):
    """Establishes a connection to an Oracle database."""
    try:
        dsn = f"{host}:{port}/{service_name}"
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
        print("Oracle database connection established.")
        return conn
    except oracledb.DatabaseError as e:
        print(f"Oracle connection error: {e}")
        return None

# --- Data Retrieval Functions (No Changes) ---


def get_all_connections_from_db():
    """Returns a list of dicts with full hierarchical connection info from items table."""
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT 
                i.id, c.name, sc.name, i.name, i.host, i.port, 
                i."database", i.db_path, i.user, i.password
            FROM items i
            LEFT JOIN subcategories sc ON i.subcategory_id = sc.id
            LEFT JOIN categories c ON sc.category_id = c.id
            ORDER BY i.usage_count DESC, c.name, sc.name, i.name
        """)
        rows = c.fetchall()

    connections = []
    for row in rows:
        (item_id, cat_name, subcat_name, item_name, host,
         port, dbname, db_path, user, password) = row
        full_name = f"{cat_name} -> {subcat_name} -> {item_name}"
        connections.append({
            "id": item_id,
            "display_name": full_name,
            "name": item_name,
            "host": host,
            "port": port,
            "database": dbname,
            "db_path": db_path,
            "user": user,
            "password": password
        })
    return connections


def get_hierarchy_data():
    """Returns all categories, subcategories, and items for the main tree view."""
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, name FROM categories")
        categories = c.fetchall()

        data = []
        for cat_id, cat_name in categories:
            cat_data = {'id': cat_id, 'name': cat_name, 'subcategories': []}
            c.execute(
                "SELECT id, name FROM subcategories WHERE category_id=?", (cat_id,))
            subcats = c.fetchall()

            for subcat_id, subcat_name in subcats:
                subcat_data = {'id': subcat_id,
                               'name': subcat_name, 'items': []}
                c.execute(
                    "SELECT id, name, host, \"database\", \"user\", password, port, db_path FROM items WHERE subcategory_id=?", (subcat_id,))
                items = c.fetchall()
                for item_row in items:
                    item_id, name, host, db, user, pwd, port, db_path = item_row
                    conn_data = {"id": item_id, "name": name, "host": host, "database": db,
                                 "user": user, "password": pwd, "port": port, "db_path": db_path}
                    subcat_data['items'].append(conn_data)
                cat_data['subcategories'].append(subcat_data)
            data.append(cat_data)
    return data

# --- Data Modification Functions (No Changes) ---


def add_subcategory(name, parent_id):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO subcategories (name, category_id) VALUES (?, ?)", (name, parent_id))
        conn.commit()


def add_item(data, subcat_id):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        if "db_path" in data:  # SQLite
            c.execute("INSERT INTO items (name, subcategory_id, db_path) VALUES (?, ?, ?)",
                      (data["name"], subcat_id, data["db_path"]))
        else:  # Postgres/Oracle
            c.execute("INSERT INTO items (name, subcategory_id, host, \"database\", \"user\", password, port) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (data["name"], subcat_id, data["host"], data["database"], data["user"], data["password"], data["port"]))
        conn.commit()


def update_item(data):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        if "db_path" in data:  # SQLite
            c.execute("UPDATE items SET name = ?, db_path = ? WHERE id = ?",
                      (data["name"], data["db_path"], data["id"]))
        else:  # Postgres/Oracle
            c.execute("UPDATE items SET name = ?, host = ?, database = ?, user = ?, password = ?, port = ? WHERE id = ?",
                      (data["name"], data["host"], data["database"], data["user"], data["password"], data["port"], data["id"]))
        conn.commit()


def delete_item(item_id):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM items WHERE id = ?", (item_id,))
        c.execute(
            "DELETE FROM query_history WHERE connection_item_id = ?", (item_id,))
        conn.commit()

# --- History Functions (No Changes) ---


def save_query_history(conn_id, query, status, rows, duration):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO query_history 
            (connection_item_id, query_text, status, rows_affected, execution_time_sec, timestamp) 
            VALUES (?, ?, ?, ?, ?, ?)""",
                  (conn_id, query, status, rows, duration, datetime.datetime.now().isoformat()))
        conn.commit()


def get_query_history(conn_id):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, query_text, timestamp, status, rows_affected, execution_time_sec 
            FROM query_history WHERE connection_item_id = ? ORDER BY timestamp DESC""",
                  (conn_id,))
        return c.fetchall()


def delete_history_item(history_id):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM query_history WHERE id = ?", (history_id,))
        conn.commit()


def delete_all_history_for_connection(conn_id):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "DELETE FROM query_history WHERE connection_item_id = ?", (conn_id,))
        conn.commit()

# --- Database Initialization ---


def initialize_database():
    """Creates and sets up the database schema if it doesn't exist."""
    # 'database' Creating the folder if it does not exist
    db_dir = os.path.dirname(DB_FILE)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)

    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        # --- Schema Setup and Migration ---
        c.execute(
            "CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
        c.execute("CREATE TABLE IF NOT EXISTS subcategories (id INTEGER PRIMARY KEY, name TEXT, category_id INTEGER, FOREIGN KEY (category_id) REFERENCES categories (id))")
        c.execute("CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name TEXT, subcategory_id INTEGER, host TEXT, \"database\" TEXT, \"user\" TEXT, password TEXT, port INTEGER, db_path TEXT, FOREIGN KEY (subcategory_id) REFERENCES subcategories (id))")

        c.execute("SELECT COUNT(*) FROM categories")
        if c.fetchone()[0] == 0:
            c.execute(
                "INSERT OR IGNORE INTO categories (name) VALUES ('PostgreSQL Connections'), ('SQLite Connections'), ('Oracle Connections')")

        c.execute("PRAGMA table_info(items)")
        columns = [col[1] for col in c.fetchall()]
        if 'usage_count' not in columns:
            c.execute(
                "ALTER TABLE items ADD COLUMN usage_count INTEGER NOT NULL DEFAULT 0")

        c.execute("CREATE TABLE IF NOT EXISTS query_history (id INTEGER PRIMARY KEY, connection_item_id INTEGER, query_text TEXT, status TEXT, rows_affected INTEGER, execution_time_sec REAL, timestamp TEXT)")
        conn.commit()