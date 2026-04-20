#!/usr/bin/env python3
"""
Ethbot v3 — Entry Point.

Usage:
    python main_v3.py              # Run with .env defaults
    python main_v3.py --paper      # Force paper mode
    python main_v3.py --live       # Force live mode (requires API keys)
"""
import argparse
import os

# Load .env file if present
def load_dotenv():
    """Load .env.bot or .env file."""
    for env_file in [".env.bot", ".env"]:
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        key, val = key.strip(), val.strip().strip('"').strip("'")
                        if key not in os.environ:  # Don't override existing
                            os.environ[key] = val
            print(f"Loaded env from {env_file}")
            return
    print("No .env file found, using system environment")


def main():
    parser = argparse.ArgumentParser(description="Ethbot v3 Trading Engine")
    parser.add_argument("--paper", action="store_true", help="Force paper trading mode")
    parser.add_argument("--live", action="store_true", help="Force live trading mode")
    parser.add_argument("--interval", default=None, help="Override trading interval (e.g. 1m, 5m, 15m)")
    parser.add_argument("--pair", default=None, help="Override trading pair (e.g. ETHUSDT)")
    args = parser.parse_args()

    # Load env
    load_dotenv()

    # Apply overrides
    if args.paper:
        os.environ["PAPER_MODE"] = "true"
    if args.live:
        os.environ["PAPER_MODE"] = "false"
    if args.interval:
        os.environ["INTERVAL"] = args.interval
    if args.pair:
        os.environ["PAIR"] = args.pair

    # Import and run
    from bot.config import TradingConfig
    from bot.engine import run

    config = TradingConfig.from_env()
    run(config)


if __name__ == "__main__":
    main()
