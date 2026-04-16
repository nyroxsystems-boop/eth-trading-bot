"""
Jarvis Webhook Schema — Pydantic models for external LLM control.

Used by POST /api/jarvis/update_regime to validate incoming payloads
from n8n, Claude, or any external orchestrator.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class JarvisRegimeUpdate(BaseModel):
    """
    Payload for POST /api/jarvis/update_regime
    
    All fields are optional — only send what you want to change.
    The bot will merge these with its current state.
    
    Example payload from n8n/Claude:
    {
        "ml_confidence_threshold": 0.55,
        "active_edges": ["BREAKOUT", "NORMAL"],
        "risk_multiplier": 0.8,
        "reason": "High volatility detected — tightening ML gate"
    }
    """
    ml_confidence_threshold: Optional[float] = Field(
        None,
        ge=0.30, le=0.90,
        description="ML confidence floor for trade entry (default: 0.42). "
                    "Higher = fewer but higher-quality trades."
    )
    active_edges: Optional[List[str]] = Field(
        None,
        description="List of active strategy edges. "
                    "Valid: BREAKOUT, DRAWDOWN, OS-FAST, NORMAL, BB_BOUNCE, MACD_CROSS, RANGE_SUP"
    )
    emergency_stop: Optional[bool] = Field(
        None,
        description="Set to true to immediately halt all trading. "
                    "The bot will NOT enter new positions until this is set to false."
    )
    risk_multiplier: Optional[float] = Field(
        None,
        ge=0.1, le=5.0,
        description="Multiplier for Kelly position sizing (default: 1.0). "
                    "0.5 = half size, 2.0 = double size."
    )
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Human-readable reason for this update (logged for audit)."
    )


class JarvisStateResponse(BaseModel):
    """Response from GET /api/jarvis/state"""
    override_active: bool
    ml_confidence_threshold: float
    active_edges: List[str]
    emergency_stop: bool
    risk_multiplier: float
    last_update: float
    last_update_iso: Optional[str]
