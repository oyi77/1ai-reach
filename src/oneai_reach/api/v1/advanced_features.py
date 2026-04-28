"""Intent signals & lead recycling API endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

from oneai_reach.config.settings import get_settings
from oneai_reach.application.outreach.intent_detector import get_intent_detector
from oneai_reach.application.outreach.lead_recycler import get_lead_recycler
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)
config = get_settings()

# Intent signals router
intent_router = APIRouter(prefix="/api/v1/intent", tags=["intent"])

@intent_router.get("/overview")
def get_intent_overview():
    """Get intent signals dashboard overview."""
    detector = get_intent_detector(config)
    signals = detector._load_signals()
    
    # Count by type
    by_type = {}
    unacted = 0
    for signal in signals:
        signal_type = signal.get("signal_type", "unknown")
        by_type[signal_type] = by_type.get(signal_type, 0) + 1
        if not signal.get("acted_on", False):
            unacted += 1
    
    # Recent signals
    recent = sorted(signals, key=lambda x: x.get("detected_at", ""), reverse=True)[:10]
    
    return {
        "data": {
            "total_signals": len(signals),
            "unacted_signals": unacted,
            "by_type": by_type,
            "recent_signals": recent
        }
    }


# Lead recycling router
recycling_router = APIRouter(prefix="/api/v1/outreach/recycling", tags=["outreach"])

@recycling_router.get("/overview")
def get_recycling_overview():
    """Get lead recycling queue overview."""
    recycler = get_lead_recycler(config)
    
    # Load leads database
    from oneai_reach.infrastructure.database.lead_repository import LeadRepository
    repo = LeadRepository(config)
    df = repo.get_all_leads()
    
    if df.empty:
        return {"data": {"total_cold_leads": 0, "by_interval": {}, "candidates": []}}
    
    # Find cold leads
    cold_leads = recycler.find_cold_leads(df, days_since_contact=30)
    
    # Prioritize
    prioritized = recycler.prioritize_cold_leads(cold_leads)
    
    # Build candidates list
    candidates = []
    by_interval = {30: 0, 60: 0, 90: 0}
    
    for lead_id, days_since, priority in prioritized[:20]:
        lead_row = df[df["id"] == lead_id]
        if lead_row.empty:
            continue
        
        row = lead_row.iloc[0]
        candidates.append({
            "lead_id": lead_id,
            "company_name": str(row.get("company_name", "Unknown")),
            "email": str(row.get("email", "")),
            "phone": str(row.get("internationalPhoneNumber", row.get("phone", ""))),
            "days_since_contact": days_since,
            "status": str(row.get("status", "contacted")),
            "priority": priority,
            "last_contacted": str(row.get("contacted_at", ""))
        })
        
        # Count by interval
        for interval in [30, 60, 90]:
            if days_since >= interval and days_since < interval + 15:
                by_interval[interval] += 1
                break
    
    return {
        "data": {
            "total_cold_leads": len(cold_leads),
            "by_interval": by_interval,
            "candidates": candidates
        }
    }


# Reports router
reports_router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

@reports_router.get("/overview")
def get_reports_overview():
    """Get automated reports overview."""
    reports_dir = Path(config.database.data_dir) / "reports"
    
    if not reports_dir.exists():
        return {"data": {"total_reports": 0, "weekly_reports": 0, "monthly_reports": 0, "recent_reports": []}}
    
    # Find all reports
    reports = []
    weekly_count = 0
    monthly_count = 0
    
    for report_file in reports_dir.glob("*.json"):
        try:
            with open(report_file) as f:
                report_data = json.load(f)
            
            reports.append({
                "id": report_file.stem,
                "report_type": report_data.get("report_type", "unknown"),
                "period": report_data.get("period", ""),
                "generated_at": report_data.get("generated_at", ""),
                "file_path": str(report_file),
                "pipeline": report_data.get("pipeline", {}),
                "conversion_rates": report_data.get("conversion_rates", {})
            })
            
            if report_data.get("report_type") == "weekly":
                weekly_count += 1
            elif report_data.get("report_type") == "monthly":
                monthly_count += 1
        except Exception:
            continue
    
    # Sort by date
    reports = sorted(reports, key=lambda x: x.get("generated_at", ""), reverse=True)
    
    return {
        "data": {
            "total_reports": len(reports),
            "weekly_reports": weekly_count,
            "monthly_reports": monthly_count,
            "recent_reports": reports[:10]
        }
    }
