import sqlite3
import threading
import time

from sqlalchemy import create_engine

from config.settings import DATABASE_URL, LOCAL_DB_PATH, LOCAL_DB_URL

# Create local SQLAlchemy engine
try:
    local_engine = create_engine(LOCAL_DB_URL)
except Exception as e:
    print(f"Local engine init notice: {e}")
    local_engine = None

# Setup Cloud Database Engine (Supabase PostgreSQL)
try:
    if "postgres" in DATABASE_URL:
        connect_args = {"options": "-c statement_timeout=30000"}
        cloud_engine = create_engine(
            DATABASE_URL, 
            connect_args=connect_args,
            pool_pre_ping=True
        )
    else:
        cloud_engine = None
except Exception as e:
    print(f"Cloud DB engine init notice: {e}")
    cloud_engine = None

# Main engine defaults to local_engine for ultra-fast query performance
engine = local_engine if local_engine else cloud_engine

def _write_sync_status(success: bool, op_type: str, err: str = ""):
    """Helper to record cloud DB background sync status in SQLite."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _cloud_sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT,
                operation TEXT,
                error_msg TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        st_val = "SUCCESS" if success else "ERROR"
        conn.execute(
            "INSERT INTO _cloud_sync_log (status, operation, error_msg) VALUES (?, ?, ?)",
            (st_val, op_type, err[:500])
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_cloud_sync_status():
    """Returns the latest cloud sync status record from SQLite."""
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("SELECT status, operation, timestamp, error_msg FROM _cloud_sync_log ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"status": row[0], "operation": row[1], "timestamp": row[2], "error": row[3]}
    except Exception:
        pass
    return None

def sync_to_cloud_async(data_df, mode="append"):
    """
    Pushes DataFrame to Cloud PostgreSQL in non-blocking background thread
    via high-speed native COPY stream.
    """
    if not DATABASE_URL or "postgres" not in DATABASE_URL:
        return

    def _sync_worker(df, m):
        import io

        import psycopg2
        try:
            t0 = time.time()
            buf = io.StringIO()
            df.to_csv(buf, index=False, header=False, sep='\t', na_rep='')
            buf.seek(0)
            
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            
            cols_def = ', '.join([f'"{c}" TEXT' for c in df.columns])
            cur.execute(f'CREATE TABLE IF NOT EXISTS "donations" ({cols_def});')
            if m == "replace":
                cur.execute('TRUNCATE TABLE "donations";')
            conn.commit()
            
            target_cols = ', '.join([f'"{c}"' for c in df.columns])
            copy_sql = f'COPY "donations" ({target_cols}) FROM STDIN WITH (FORMAT csv, DELIMITER \'\t\', NULL \'\');'
            cur.copy_expert(sql=copy_sql, file=buf)
            conn.commit()
            cur.close()
            conn.close()
            elapsed = time.time() - t0
            _write_sync_status(True, f"upload ({m})", "")
            print(f"✅ Supabase Cloud PostgreSQL native COPY complete in {elapsed:.2f}s!")
        except Exception as e:
            _write_sync_status(False, f"upload ({m})", str(e))
            print(f"Cloud DB sync notice: {e}")

    threading.Thread(target=_sync_worker, args=(data_df, mode), daemon=True).start()
