#!/usr/bin/env python3
"""
Ethbot v3 — API Server.

Runs the dashboard API on port 8000.
- Worker mode: serves API from local data (trades.csv, bot_state.json)
- Web mode: proxies API requests to the worker service
"""
import argparse
import os
import uvicorn
import httpx
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response

app = FastAPI(title="Ethbot v3 API", version="3.0.0")

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Determine mode: web service proxies to worker, worker serves directly
SERVICE_NAME = os.getenv("RAILWAY_SERVICE_NAME", "worker")
WORKER_INTERNAL_URL = os.getenv(
    "WORKER_API_URL",
    "http://worker.railway.internal:8080"
)

if SERVICE_NAME == "web":
    # ── WEB MODE: Proxy all /api/v3/* to worker ──
    print(f"Web mode: proxying API to {WORKER_INTERNAL_URL}")

    @app.api_route("/api/v3/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def proxy_api(path: str, request: Request):
        """Proxy all API requests to the worker service."""
        url = f"{WORKER_INTERNAL_URL}/api/v3/{path}"
        params = dict(request.query_params)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if request.method == "GET":
                    resp = await client.get(url, params=params)
                else:
                    body = await request.body()
                    resp = await client.request(
                        request.method, url, params=params, content=body,
                        headers={"content-type": request.headers.get("content-type", "application/json")}
                    )
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    media_type=resp.headers.get("content-type", "application/json"),
                )
        except Exception as e:
            return JSONResponse(
                {"error": f"Worker unreachable: {e}"},
                status_code=502,
            )
else:
    # ── WORKER MODE: Serve API from local data ──
    from api.v3_routes import router as v3_router
    app.include_router(v3_router)

# Health check
@app.get("/health")
async def health():
    return {"status": "healthy", "version": "v3", "mode": SERVICE_NAME}

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
    if full_path.startswith("api/") or full_path.startswith("health"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    index = DASHBOARD_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"status": "ok", "note": "Dashboard not built."})


def main():
    parser = argparse.ArgumentParser(description="Ethbot v3 API Server")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    print(f"Starting Ethbot v3 API on {args.host}:{args.port} (mode: {SERVICE_NAME})")
    print(f"Dashboard: {'FOUND' if (DASHBOARD_DIST / 'index.html').exists() else 'NOT BUILT'} at {DASHBOARD_DIST}")
    if SERVICE_NAME == "web":
        print(f"Proxying API to: {WORKER_INTERNAL_URL}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

