import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api import admin, auth, classifications, donors, events, expenses, filters, ltv, metrics, overview
from core.auth import init_user_db
from core.data_processor import load_data

# Initialize user DB
init_user_db()

app = FastAPI(
    title="Crowdfunding Analytics & Enterprise CRM API",
    description="High-performance FastAPI engine providing LTV analytics, 360° donor profiles, classification rules, and dataset management.",
    version="2.0.0"
)

# Enable CORS for React / Vercel frontend
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
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


@app.get("/api/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "Crowdfunding Enterprise CRM API",
        "version": "2.0.0"
    }


# Mount Built Static Frontend Assets if present
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")


@app.on_event("startup")
def startup_event():
    print("Crowdfunding Enterprise CRM API initialized.")
    load_data()
