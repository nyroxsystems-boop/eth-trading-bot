#!/usr/bin/env python3
"""
Training Data Sync - Push local training metrics to Railway Dashboard
Runs as a background service to keep dashboard updated with local training progress
"""

import os
import json
import time
import requests
from pathlib import Path
from datetime import datetime

# Configuration
RAILWAY_API_URL = os.getenv("RAILWAY_API_URL", "https://web-production-d57ac.up.railway.app")
SYNC_INTERVAL_SECONDS = 30
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))

def load_training_status():
    """Load current training status from local files"""
    status = {
        "training_active": False,
        "dqn_status": None,
        "model_info": None,
        "last_sync": datetime.now().isoformat()
    }
    
    # Check DQN training live status
    dqn_live_file = LOG_DIR / "dqn_training_live.json"
    if dqn_live_file.exists():
        try:
            with open(dqn_live_file, "r") as f:
                dqn_data = json.load(f)
                status["dqn_status"] = dqn_data
                
                # Check if training is recent (within last 5 minutes)
                timestamp = datetime.fromisoformat(dqn_data.get("timestamp", "2020-01-01"))
                age_seconds = (datetime.now() - timestamp).total_seconds()
                status["training_active"] = age_seconds < 300
        except Exception as e:
            print(f"Error loading DQN status: {e}")
    
    # Check for trained model
    model_file = LOG_DIR / "dqn_agent.pt"
    if model_file.exists():
        stat = model_file.stat()
        status["model_info"] = {
            "file": str(model_file),
            "size_kb": round(stat.st_size / 1024, 1),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
        }
    
    return status

def sync_to_dashboard(status: dict):
    """Push training status to Railway dashboard API"""
    try:
        # Create a summary for the API
        payload = {
            "source": "local_mac",
            "timestamp": datetime.now().isoformat(),
            "training_active": status.get("training_active", False),
            "dqn_status": status.get("dqn_status"),
            "model_info": status.get("model_info")
        }
        
        # The dashboard API endpoint for training updates
        response = requests.post(
            f"{RAILWAY_API_URL}/api/ml/training-sync",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Synced to dashboard: {payload.get('dqn_status', {}).get('progress_pct', 0):.0f}% complete")
            return True
        else:
            # Fallback: just log locally if endpoint doesn't exist
            print(f"ℹ️ Dashboard sync endpoint not available (status {response.status_code})")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Sync failed (will retry): {e}")
        return False

def run_sync_loop():
    """Main sync loop"""
    print(f"🔄 Training Sync started - pushing to {RAILWAY_API_URL}")
    print(f"   Sync interval: {SYNC_INTERVAL_SECONDS}s")
    
    while True:
        try:
            status = load_training_status()
            
            if status.get("training_active"):
                dqn = status.get("dqn_status", {})
                print(f"📊 Training: Episode {dqn.get('episode', '?')}/{dqn.get('total_episodes', '?')} | "
                      f"ROI: {dqn.get('roi', 0):.1f}% | Portfolio: ${dqn.get('portfolio_value', 0):,.2f}")
                sync_to_dashboard(status)
            else:
                print(f"💤 No active training detected...")
                
        except Exception as e:
            print(f"❌ Sync loop error: {e}")
        
        time.sleep(SYNC_INTERVAL_SECONDS)

if __name__ == "__main__":
    run_sync_loop()
