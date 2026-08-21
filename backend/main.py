import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api import admin, auth, classifications, donors, events, expenses, filters, fundraisers, ltv, metrics, overview, payouts, tracker
from core.auth import init_user_db

# Initialize user DB
init_user_db()

app = FastAPI(
    title="Crowdfunding Analytics & Enterprise CRM API",
    description="High-performance FastAPI engine providing LTV analytics, 360° donor profiles, classification rules, and dataset management.",
    version="2.0.0"
)

# Enable CORS for React / Vercel frontend
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]

if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?:\/\/.*$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
    """Warms up in-memory parquet cache and DuckDB analytics engine asynchronously."""
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



