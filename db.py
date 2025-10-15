
# database/db.py

import sqlite3 as sqlite
import psycopg2
from psycopg2 import OperationalError
import oracledb
import sys
import os
import datetime
from sqlalchemy import create_engine



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

# pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested
# def create_postgres_connection(host, port, database, user, password):
#     """Establishes a SQLAlchemy engine connection to a PostgreSQL database."""
#     try:
#         url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
#         engine = create_engine(url)
#         # Test connection
#         with engine.connect() as conn:
#             print("PostgreSQL database connection (SQLAlchemy engine) established.")
#         return engine
#     except Exception as e:
#         print(f"PostgreSQL connection error: {e}")
#         return None



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
    """Returns a list of dicts with full hierarchical connection info from usf_connections table."""
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT 
                i.id, c.name, sc.name, i.name, i.short_name, i.host, i.port, 
                i."database", i.db_path, i.user, i.password
            FROM usf_connections i
            LEFT JOIN usf_connection_groups sc ON i.connection_group_id = sc.id
            LEFT JOIN usf_connection_types c ON sc.connection_type_id = c.id
            ORDER BY i.usage_count DESC, c.name, sc.name, i.name
        """)
        rows = c.fetchall()

    connections = []
    for row in rows:
        (connection_id, connection_type_name, connection_group_name, connection_name, short_name, host,
         port, dbname, db_path, user, password) = row
        full_name = f"{connection_type_name} -> {connection_group_name} -> {connection_name} ({short_name})"
        connections.append({
            "id": connection_id,
            "display_name": full_name,
            "name": connection_name,
            "short_name": short_name,
            "host": host,
            "port": port,
            "database": dbname,
            "db_path": db_path,
            "user": user,
            "password": password
        })
    return connections


def get_hierarchy_data():
    """Returns all usf_connection_types, usf_connection_groups, and usf_connections for the main tree view."""
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, name FROM usf_connection_types")
        usf_connection_types = c.fetchall()

        data = []
        for connection_type_id, connection_type_name in usf_connection_types:
            connection_type_data = {'id': connection_type_id, 'name': connection_type_name, 'usf_connection_groups': []}
            c.execute(
                "SELECT id, name FROM usf_connection_groups WHERE connection_type_id=?", (connection_type_id,))
            connection_groups = c.fetchall()

            for connection_group_id, connection_group_name in connection_groups:
                connection_group_data = {'id': connection_group_id,
                               'name': connection_group_name, 'usf_connections': []}
                c.execute(
                    "SELECT id, name, short_name, host, \"database\", \"user\", password, port, db_path FROM usf_connections WHERE connection_group_id=?", (connection_group_id,))
                usf_connections = c.fetchall()
                for connections in usf_connections:
                    connection_id, name, short_name, host, db, user, pwd, port, db_path = connections
                    conn_data = {"id": connection_id, "name": name, "short_name": short_name, "host": host, "database": db,
                                 "user": user, "password": pwd, "port": port, "db_path": db_path}
                    connection_group_data['usf_connections'].append(conn_data)
                connection_type_data['usf_connection_groups'].append(connection_group_data)
            data.append(connection_type_data)
    return data

# --- Data Modification Functions (No Changes) ---


def add_connection_group(name, parent_id):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO usf_connection_groups (name, connection_type_id) VALUES (?, ?)", (name, parent_id))
        conn.commit()


def add_connection(data, connection_group_id):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        if "db_path" in data:  # SQLite
            c.execute("INSERT INTO usf_connections (name, short_name, connection_group_id, db_path) VALUES (?, ?, ?)",
                      (data["name"], data["short_name"], connection_group_id, data["db_path"]))
        else:  # Postgres/Oracle
            c.execute("INSERT INTO usf_connections (name, short_name, connection_group_id, host, \"database\", \"user\", password, port) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (data["name"], data["short_name"], connection_group_id, data["host"], data["database"], data["user"], data["password"], data["port"]))
        conn.commit()


def update_connection(data):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        if "db_path" in data:  # SQLite
            c.execute("UPDATE usf_connections SET name = ?, short_name = ?, db_path = ? WHERE id = ?",
                      (data["name"], data["short_name"], data["db_path"], data["id"]))
        else:  # Postgres/Oracle
            c.execute("UPDATE usf_connections SET name = ?, short_name = ?, host = ?, database = ?, user = ?, password = ?, port = ? WHERE id = ?",
                      (data["name"], data["short_name"], data["host"], data["database"], data["user"], data["password"], data["port"], data["id"]))
        conn.commit()


def delete_connection(connection_id):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM usf_connections WHERE id = ?", (connection_id,))
        c.execute(
            "DELETE FROM usf_query_history WHERE connection_id = ?", (connection_id,))
        conn.commit()

# --- History Functions (No Changes) ---


def save_query_history(conn_id, query, status, rows, duration):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO usf_query_history 
            (connection_id, query_text, status, rows_affected, execution_time_sec, timestamp) 
            VALUES (?, ?, ?, ?, ?, ?)""",
                  (conn_id, query, status, rows, duration, datetime.datetime.now().isoformat()))
        conn.commit()


def get_query_history(conn_id):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, query_text, timestamp, status, rows_affected, execution_time_sec 
            FROM usf_query_history WHERE connection_id = ? ORDER BY timestamp DESC""",
                  (conn_id,))
        return c.fetchall()


def delete_history(history_id):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM usf_query_history WHERE id = ?", (history_id,))
        conn.commit()


def delete_all_history(conn_id):
    with sqlite.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "DELETE FROM usf_query_history WHERE connection_id = ?", (conn_id,))
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
            "CREATE TABLE IF NOT EXISTS usf_connection_types (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
        c.execute("CREATE TABLE IF NOT EXISTS usf_connection_groups (id INTEGER PRIMARY KEY, name TEXT, connection_type_id INTEGER, FOREIGN KEY (connection_type_id) REFERENCES usf_connection_types (id))")
        c.execute("CREATE TABLE IF NOT EXISTS usf_connections (id INTEGER PRIMARY KEY, name TEXT, connection_group_id INTEGER, host TEXT, \"database\" TEXT, \"user\" TEXT, password TEXT, port INTEGER, db_path TEXT, FOREIGN KEY (connection_group_id) REFERENCES usf_connection_groups (id))")

        c.execute("SELECT COUNT(*) FROM usf_connection_types")
        if c.fetchone()[0] == 0:
            c.execute(
                "INSERT OR IGNORE INTO usf_connection_types (name) VALUES ('PostgreSQL Connections'), ('SQLite Connections'), ('Oracle Connections')")

        c.execute("PRAGMA table_info(usf_connections)")
        columns = [col[1] for col in c.fetchall()]
        if 'usage_count' not in columns:
            c.execute(
                "ALTER TABLE usf_connections ADD COLUMN usage_count INTEGER NOT NULL DEFAULT 0")

        c.execute("CREATE TABLE IF NOT EXISTS usf_query_history (id INTEGER PRIMARY KEY, connection_id INTEGER, query_text TEXT, status TEXT, rows_affected INTEGER, execution_time_sec REAL, timestamp TEXT)")
        conn.commit()