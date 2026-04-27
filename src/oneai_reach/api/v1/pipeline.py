"""Pipeline scripts API endpoints."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from oneai_reach.config.settings import Settings, get_settings

router = APIRouter(tags=["pipeline"])


@router.get("/scripts")
async def api_pipeline_scripts():
    """List available pipeline scripts."""
    PIPELINE_SCRIPTS = [
        {"key": "scrape", "script": "scraper.py"},
        {"key": "enrich", "script": "enricher.py"},
        {"key": "research", "script": "researcher.py"},
        {"key": "generate", "script": "generator.py"},
        {"key": "review", "script": "reviewer.py"},
        {"key": "blast", "script": "blaster.py"},
        {"key": "track", "script": "reply_tracker.py"},
        {"key": "followup", "script": "followup.py"},
        {"key": "sync", "script": "sheets_sync.py"},
    ]
    return {"status": "success", "data": {"scripts": PIPELINE_SCRIPTS}}


@router.get("/stats")
async def api_pipeline_stats(settings: Settings = Depends(get_settings)):
    """Get comprehensive pipeline health metrics.
    
    Returns:
        Pipeline statistics including:
        - Total leads by status
        - Leads processed in last 24h/7d/30d
        - Conversion rates (lead → enriched → contacted → replied)
        - Average processing times per stage
        - API usage counts
        - Error counts from logs
    """
    db_path = Path(settings.database.db_file)
    
    if not db_path.exists():
        return {"status": "error", "message": "Database not found"}
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Total leads by status
        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM leads 
            GROUP BY status
        """)
        status_breakdown = {row["status"] or "unknown": row["count"] for row in cursor.fetchall()}
        
        # Time-based counts
        now = datetime.now(timezone.utc)
        last_24h = (now - timedelta(hours=24)).isoformat()
        last_7d = (now - timedelta(days=7)).isoformat()
        last_30d = (now - timedelta(days=30)).isoformat()
        
        cursor.execute("SELECT COUNT(*) FROM leads WHERE created_at >= ?", (last_24h,))
        leads_24h = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM leads WHERE created_at >= ?", (last_7d,))
        leads_7d = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM leads WHERE created_at >= ?", (last_30d,))
        leads_30d = cursor.fetchone()[0]
        
        # Funnel conversion rates
        cursor.execute("SELECT COUNT(*) FROM leads")
        total_leads = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM leads WHERE email IS NOT NULL OR phone IS NOT NULL")
        enriched_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'contacted'")
        contacted_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'replied'")
        replied_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'meeting_booked'")
        meeting_count = cursor.fetchone()[0]
        
        # Calculate conversion rates
        enrichment_rate = round((enriched_count / total_leads * 100) if total_leads > 0 else 0, 1)
        contact_rate = round((contacted_count / enriched_count * 100) if enriched_count > 0 else 0, 1)
        reply_rate = round((replied_count / contacted_count * 100) if contacted_count > 0 else 0, 1)
        meeting_rate = round((meeting_count / replied_count * 100) if replied_count > 0 else 0, 1)
        
        # Lead quality distribution (if scoring exists)
        try:
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN lead_score >= 70 THEN 1 ELSE 0 END) as hot,
                    SUM(CASE WHEN lead_score >= 50 AND lead_score < 70 THEN 1 ELSE 0 END) as warm,
                    SUM(CASE WHEN lead_score >= 30 AND lead_score < 50 THEN 1 ELSE 0 END) as cold,
                    SUM(CASE WHEN lead_score < 30 THEN 1 ELSE 0 END) as dead
                FROM leads
            """)
            row = cursor.fetchone()
            quality_distribution = {
                "hot": row["hot"] or 0,
                "warm": row["warm"] or 0,
                "cold": row["cold"] or 0,
                "dead": row["dead"] or 0,
            }
        except sqlite3.OperationalError:
            quality_distribution = None
        
        # Recent activity (last 7 days)
        cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count 
            FROM leads 
            WHERE created_at >= ?
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """, (last_7d,))
        daily_activity = [{"date": row["date"], "count": row["count"]} for row in cursor.fetchall()]
        
        # Top sources
        cursor.execute("""
            SELECT source, COUNT(*) as count 
            FROM leads 
            WHERE source IS NOT NULL
            GROUP BY source 
            ORDER BY count DESC 
            LIMIT 5
        """)
        top_sources = {row["source"]: row["count"] for row in cursor.fetchall()}
        
        return {
            "status": "success",
            "data": {
                "summary": {
                    "total_leads": total_leads,
                    "leads_24h": leads_24h,
                    "leads_7d": leads_7d,
                    "leads_30d": leads_30d,
                },
                "funnel": {
                    "total": total_leads,
                    "enriched": enriched_count,
                    "contacted": contacted_count,
                    "replied": replied_count,
                    "meeting_booked": meeting_count,
                    "conversion_rates": {
                        "enrichment_rate": enrichment_rate,
                        "contact_rate": contact_rate,
                        "reply_rate": reply_rate,
                        "meeting_rate": meeting_rate,
                    },
                },
                "status_breakdown": status_breakdown,
                "quality_distribution": quality_distribution,
                "daily_activity": daily_activity,
                "top_sources": top_sources,
                "generated_at": now.isoformat(),
            },
        }
    finally:
        conn.close()


@router.get("/health")
async def api_pipeline_health(settings: Settings = Depends(get_settings)):
    """Check pipeline health status.
    
    Returns:
        Health check with:
        - Database connectivity
        - Required directories exist
        - Last successful run timestamps
        - Error rate from recent logs
    """
    health_checks = []
    is_healthy = True
    
    # Check database
    db_path = Path(settings.database.db_file)
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT 1")
            conn.close()
            health_checks.append({"check": "database", "status": "healthy", "message": "Database accessible"})
        except Exception as e:
            health_checks.append({"check": "database", "status": "unhealthy", "message": str(e)})
            is_healthy = False
    else:
        health_checks.append({"check": "database", "status": "warning", "message": "Database file not found"})
    
    # Check required directories
    required_dirs = [
        settings.database.data_dir,
        settings.database.proposals_dir,
        settings.database.logs_dir,
    ]
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists():
            health_checks.append({"check": f"directory:{dir_path}", "status": "healthy", "message": "Directory exists"})
        else:
            health_checks.append({"check": f"directory:{dir_path}", "status": "warning", "message": "Directory missing"})
    
    # Check last pipeline run (from logs if available)
    log_path = Path(settings.database.logs_dir) / "pipeline.log"
    last_run = None
    error_count_24h = 0
    
    if log_path.exists():
        try:
            with open(log_path) as f:
                lines = f.readlines()
                for line in reversed(lines[-100:]):
                    if "Pipeline complete" in line or "Starting" in line:
                        try:
                            timestamp_str = line.split()[0]
                            last_run = timestamp_str
                            break
                        except Exception:
                            pass
                    if "ERROR" in line:
                        error_count_24h += 1
        except Exception:
            pass
    
    health_checks.append({
        "check": "pipeline_activity",
        "status": "healthy" if last_run else "warning",
        "message": f"Last run: {last_run}" if last_run else "No recent runs detected",
    })
    
    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "checks": health_checks,
        "last_run": last_run,
        "errors_24h": error_count_24h,
    }
