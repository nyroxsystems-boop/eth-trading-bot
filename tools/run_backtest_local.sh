#!/bin/bash
# =============================================================
# Local-Only Backtester Runner
# =============================================================
# The continuous backtester has been removed from Railway to save
# resources. Run this script locally to generate and test strategies.
#
# Usage:
#   ./tools/run_backtest_local.sh          # uses local DB
#   DATABASE_URL=postgres://... ./tools/run_backtest_local.sh  # uses prod DB
# =============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Default to local SQLite if no DATABASE_URL set
if [ -z "$DATABASE_URL" ]; then
    echo "⚠️  No DATABASE_URL set — using local SQLite (results won't sync to Railway)"
    echo "   Set DATABASE_URL for production database sync."
fi

echo "🔬 Starting Continuous Backtester (LOCAL ONLY)..."
echo "   Press Ctrl+C to stop."
echo ""

python3 continuous_backtester.py
