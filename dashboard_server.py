#!/usr/bin/env python3
"""
Static file server for dashboard
Serves the built React dashboard from /dashboard/dist
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

app = FastAPI()

# Mount static files
dashboard_dist = Path(__file__).parent / "dashboard" / "dist"

if dashboard_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(dashboard_dist / "assets")), name="assets")
    
    @app.get("/")
    @app.get("/{full_path:path}")
    async def serve_dashboard(full_path: str = ""):
        index_file = dashboard_dist / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"error": "Dashboard not built"}
else:
    @app.get("/")
    async def no_dashboard():
        return {"error": "Dashboard not found. Run 'cd dashboard && npm run build' first."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
