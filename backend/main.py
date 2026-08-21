import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api import admin, auth, classifications, donors, events, expenses, filters, fundraisers, ltv, metrics, overview, payouts, tracker
from core.auth import init_user_db

app = FastAPI(
    title="Crowdfunding Analytics & Enterprise CRM API",
    description="High-performance FastAPI engine providing LTV analytics, 360° donor profiles, classification rules, and dataset management.",
    version="2.0.0"
)

# Enable CORS for React / Vercel frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://rethink-s-crm.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "https://rethink-s-crm-5e5c3bf8.fastapicloud.dev",
        "*"
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Register API Routers
app.include_router(auth.router)
app.include_router(metrics.router)
app.include_router(overview.router)
app.include_router(ltv.router)
app.include_router(donors.router)
app.include_router(classifications.router)
app.include_router(admin.router)
app.include_router(expenses.router)
app.include_router(filters.router)
app.include_router(events.router)
app.include_router(tracker.router)
app.include_router(payouts.router)
app.include_router(fundraisers.router)


@app.get("/api/health", tags=["Health"])
@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "Crowdfunding Enterprise CRM API",
        "version": "2.0.0"
    }


@app.get("/", tags=["Root"])
def root_endpoint():
    return {
        "status": "online",
        "service": "Crowdfunding Analytics & Enterprise CRM API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/health"
    }


def _background_prewarm():
    """Warms up SQLite seed database, in-memory parquet cache, and DuckDB analytics engine asynchronously."""
    try:
        from core.database import seed_database_if_empty
        seed_database_if_empty()
    except Exception as e:
        print(f"[Seed Check Notice]: {e}")

    try:
        from core.auth import init_user_db
        init_user_db()
    except Exception as e:
        print(f"[Auth DB Init Notice]: {e}")

    try:
        from core.data_processor import load_data
        df = load_data()
        print(f"In-memory dataset cache pre-warmed: {len(df):,} donor records.")
    except Exception as e:
        print(f"[Cache Pre-warm Notice]: {e}")

    try:
        from core.analytics_engine import get_duckdb_connection
        get_duckdb_connection()
        print("DuckDB high-speed analytics engine initialized.")
    except Exception as e:
        print(f"[DuckDB Pre-warm Notice]: {e}")


@app.on_event("startup")
def startup_event():
    print("Crowdfunding Enterprise CRM API initialized and ready to receive requests.")
    if not os.environ.get("VERCEL"):
        import threading
        threading.Thread(target=_background_prewarm, daemon=True).start()



