"""Optimization API endpoints for A/B testing, send time, and follow-ups."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime
from oneai_reach.config.settings import Settings, get_settings
from oneai_reach.application.outreach.ab_testing_service import get_ab_testing_service, TestType, TestStatus
from oneai_reach.application.outreach.send_time_optimizer import get_send_time_optimizer
from oneai_reach.application.outreach.followup_service import get_followup_service

router = APIRouter(tags=["optimization"])


class CreateABTestRequest(BaseModel):
    name: str
    test_type: str  # subject_line, email_body, send_time
    variants: List[Dict]


class RecordEventRequest(BaseModel):
    test_id: str
    variant_id: str
    event_type: str  # sent, opened, clicked, replied, converted


class SendTimeRequest(BaseModel):
    lead_id: str
    email: Optional[str] = None
    vertical: Optional[str] = None
    primaryType: Optional[str] = None


@router.get("/ab-tests")
async def list_ab_tests(status: Optional[str] = None):
    """List all A/B tests."""
    config = get_settings()
    service = get_ab_testing_service(config)
    
    filter_status = None
    if status:
        try:
            filter_status = TestStatus(status)
        except ValueError:
            pass
    
    tests = service.list_tests(filter_status)
    return {
        "status": "success",
        "data": {
            "tests": [
                {
                    "id": t.id,
                    "name": t.name,
                    "type": t.test_type.value,
                    "status": t.status.value,
                    "variants_count": len(t.variants),
                    "created_at": t.created_at,
                }
                for t in tests
            ]
        }
    }


@router.post("/ab-tests/create")
async def create_ab_test(req: CreateABTestRequest):
    """Create a new A/B test."""
    config = get_settings()
    service = get_ab_testing_service(config)
    
    try:
        test_type = TestType(req.test_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid test type: {req.test_type}")
    
    test = service.create_test(req.name, test_type, req.variants)
    
    return {
        "status": "success",
        "message": f"A/B test created: {test.name}",
        "data": {
            "id": test.id,
            "name": test.name,
            "variants": len(test.variants),
        }
    }


@router.post("/ab-tests/{test_id}/start")
async def start_ab_test(test_id: str):
    """Start an A/B test."""
    config = get_settings()
    service = get_ab_testing_service(config)
    
    try:
        service.start_test(test_id)
        return {"status": "success", "message": f"Test {test_id} started"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/ab-tests/{test_id}/results")
async def get_ab_test_results(test_id: str):
    """Get A/B test results."""
    config = get_settings()
    service = get_ab_testing_service(config)
    
    results = service.get_test_results(test_id)
    if not results:
        raise HTTPException(status_code=404, detail="Test not found")
    
    return {"status": "success", "data": results}


@router.post("/ab-tests/event")
async def record_ab_test_event(req: RecordEventRequest):
    """Record engagement event for A/B test."""
    config = get_settings()
    service = get_ab_testing_service(config)
    
    service.record_event(req.test_id, req.variant_id, req.event_type)
    
    return {"status": "success", "message": "Event recorded"}


@router.post("/send-time/predict")
async def predict_send_time(req: SendTimeRequest):
    """Predict optimal send time for a lead."""
    config = get_settings()
    optimizer = get_send_time_optimizer(config)
    
    lead_data = {
        "id": req.lead_id,
        "email": req.email,
        "vertical": req.vertical,
        "primaryType": req.primaryType,
    }
    
    prediction = optimizer.predict_best_time(lead_data)
    
    return {
        "status": "success",
        "data": {
            "best_day": prediction.best_day,
            "best_hour": prediction.best_hour,
            "confidence": prediction.confidence,
            "reason": prediction.reason,
            "alternatives": prediction.alternative_times,
        }
    }


@router.get("/send-time/stats")
async def get_send_time_stats():
    """Get send time optimization statistics."""
    config = get_settings()
    optimizer = get_send_time_optimizer(config)
    
    stats = optimizer.get_optimization_stats()
    
    return {
        "status": "success",
        "data": stats
    }


@router.get("/followups/due")
async def get_due_followups():
    """Get follow-ups that are due to be sent."""
    config = get_settings()
    service = get_followup_service(config)
    
    due = service.get_due_followups()
    
    return {
        "status": "success",
        "data": {
            "count": len(due),
            "followups": [
                {
                    "lead_id": seq.lead_id,
                    "sequence": seq.sequence_name,
                    "next_followup": seq.next_followup_at,
                    "completed": seq.completed_followups,
                    "total": seq.total_followups,
                }
                for seq in due
            ]
        }
    }


@router.get("/overview")
async def get_optimization_overview():
    """Get comprehensive optimization overview."""
    config = get_settings()
    
    ab_service = get_ab_testing_service(config)
    send_optimizer = get_send_time_optimizer(config)
    followup_service = get_followup_service(config)
    
    # Get A/B test stats
    all_tests = ab_service.list_tests()
    running_tests = [t for t in all_tests if t.status == TestStatus.RUNNING]
    completed_tests = [t for t in all_tests if t.status == TestStatus.COMPLETED]
    
    # Get send time stats
    send_stats = send_optimizer.get_optimization_stats()
    
    # Get follow-up stats
    due_followups = followup_service.get_due_followups()
    
    return {
        "status": "success",
        "data": {
            "ab_testing": {
                "total_tests": len(all_tests),
                "running": len(running_tests),
                "completed": len(completed_tests),
                "winners_found": len([t for t in completed_tests if t.winner_id]),
            },
            "send_time": send_stats,
            "followups": {
                "due_now": len(due_followups),
            },
            "recommendations": [
                "Start A/B testing your top 3 email templates" if len(all_tests) < 3 else "A/B testing active",
                "Enable send time optimization for 30-50% higher opens" if send_stats["total_engagements"] < 50 else "Send time optimization learning",
                "Set up automated follow-up sequences" if len(due_followups) == 0 else "Follow-ups running",
            ]
        }
    }
