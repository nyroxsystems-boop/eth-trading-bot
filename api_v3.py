#!/usr/bin/env python3
"""
Ethbot v3 — API Server.

Runs the dashboard API on port 8000.
Can be run alongside the bot (separate process) or standalone.
"""
import argparse
import os
import uvicorn
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from api.v3_routes import router as v3_router

app = FastAPI(title="Ethbot v3 API", version="3.0.0")

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register v3 API routes FIRST (before static files)
app.include_router(v3_router)

# Health check
@app.get("/health")
async def health():
    return {"status": "healthy", "version": "v3"}

# Serve dashboard static files
DASHBOARD_DIST = Path(__file__).parent / "dashboard" / "dist"

@app.get("/")
async def serve_root():
    """Serve dashboard index.html at root."""
    index = DASHBOARD_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"status": "ok", "note": "Dashboard not built. Run: cd dashboard && npx vite build"})

# Mount assets AFTER API routes
if DASHBOARD_DIST.exists() and (DASHBOARD_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(DASHBOARD_DIST / "assets")), name="assets")

# SPA catch-all: any non-API route serves index.html for React Router
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """Catch-all for React Router — serves index.html for all non-API routes."""
    # Don't catch API routes
    if full_path.startswith("api/") or full_path.startswith("health"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    index = DASHBOARD_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"status": "ok", "note": "Dashboard not built. Run: cd dashboard && npx vite build"})


def main():
    parser = argparse.ArgumentParser(description="Ethbot v3 API Server")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    print(f"Starting Ethbot v3 API on {args.host}:{args.port}")
    print(f"Dashboard: {'FOUND' if (DASHBOARD_DIST / 'index.html').exists() else 'NOT BUILT'} at {DASHBOARD_DIST}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
