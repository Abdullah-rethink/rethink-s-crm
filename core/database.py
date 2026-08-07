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

def sync_to_cloud_async(data_df, mode="append", max_retries=3):
    """
    Pushes DataFrame to Cloud PostgreSQL in non-blocking background thread
    via high-speed native COPY stream with automatic retries and backoff.
    """
    if not DATABASE_URL or "postgres" not in DATABASE_URL:
        return

    def _sync_worker(df, m):
        import io
        import psycopg2

        attempts = 0
        last_error = ""

        # Preserving 100% full data fidelity without any string truncation
        sync_df = df.copy()

        while attempts < max_retries:
            attempts += 1
            try:
                t0 = time.time()
                buf = io.StringIO()
                sync_df.to_csv(buf, index=False, header=False, sep='\t', na_rep='')
                buf.seek(0)
                
                conn = psycopg2.connect(DATABASE_URL)
                cur = conn.cursor()
                
                # Infer exact PostgreSQL types (DOUBLE PRECISION for floats, BIGINT for ints, TEXT for strings)
                col_defs = []
                for col in sync_df.columns:
                    dtype = sync_df[col].dtype
                    if pd.api.types.is_float_dtype(dtype):
                        col_defs.append(f'"{col}" DOUBLE PRECISION')
                    elif pd.api.types.is_integer_dtype(dtype):
                        col_defs.append(f'"{col}" BIGINT')
                    else:
                        col_defs.append(f'"{col}" TEXT')
                
                cols_def = ', '.join(col_defs)
                cur.execute(f'CREATE TABLE IF NOT EXISTS "donations" ({cols_def});')
                
                # Enable PostgreSQL TOAST tuple compression for compact storage without data loss
                try:
                    cur.execute('ALTER TABLE "donations" SET (toast_tuple_target = 128);')
                except Exception:
                    pass

                if m == "replace":
                    cur.execute('TRUNCATE TABLE "donations";')
                conn.commit()
                
                target_cols = ', '.join([f'"{c}"' for c in sync_df.columns])
                copy_sql = f'COPY "donations" ({target_cols}) FROM STDIN WITH (FORMAT csv, DELIMITER \'\t\', NULL \'\');'
                
                # Low-RAM 5,000-row Chunked Stream to prevent Supabase RAM Commitment spikes
                chunk_size = 5000
                total_rows = len(sync_df)
                num_chunks = (total_rows + chunk_size - 1) // chunk_size

                for i in range(num_chunks):
                    chunk = sync_df.iloc[i * chunk_size : (i + 1) * chunk_size]
                    buf = io.StringIO()
                    chunk.to_csv(buf, index=False, header=False, sep='\t', na_rep='')
                    buf.seek(0)
                    cur.copy_expert(sql=copy_sql, file=buf)
                    buf.close()
                    conn.commit()

                cur.close()
                conn.close()
                elapsed = time.time() - t0
                _write_sync_status(True, f"upload ({m})", f"Completed in {elapsed:.2f}s on attempt {attempts}")
                print(f"[Cloud DB] Supabase Cloud PostgreSQL low-RAM chunked COPY complete in {elapsed:.2f}s (Attempt {attempts}/{max_retries})!")
                return
            except Exception as e:
                last_error = str(e)
                print(f"[Cloud DB Sync Attempt {attempts}/{max_retries} Notice]: {last_error}")
                if attempts < max_retries:
                    time.sleep(2 ** attempts) # Exponential backoff: 2s, 4s...

        _write_sync_status(False, f"upload ({m})", f"Failed after {max_retries} attempts: {last_error}")

    threading.Thread(target=_sync_worker, args=(data_df, mode), daemon=True).start()
