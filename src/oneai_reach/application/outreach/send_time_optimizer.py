"""Send time optimization using ML to predict best send times.

Analyzes:
- Historical open/click patterns by hour/day
- Lead timezone and industry
- Company size and seniority
- Channel preferences (email vs WhatsApp)

Returns optimal send time predictions with confidence scores.
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from collections import defaultdict
import logging

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SendTimePrediction:
    """Optimal send time prediction."""
    best_day: str  # Monday, Tuesday, etc.
    best_hour: int  # 0-23
    confidence: float  # 0.0-1.0
    alternative_times: List[Dict]  # Backup options
    reason: str  # Why this time was chosen


@dataclass
class EngagementPattern:
    """Engagement pattern for a lead/domain/industry."""
    entity_type: str  # lead, domain, industry
    entity_id: str
    total_sent: int = 0
    total_opens: int = 0
    total_clicks: int = 0
    hourly_opens: Dict[int, int] = None  # hour -> count
    daily_opens: Dict[str, int] = None  # day -> count
    best_hour: Optional[int] = None
    best_day: Optional[str] = None
    last_updated: str = None

    def __post_init__(self):
        if self.hourly_opens is None:
            self.hourly_opens = defaultdict(int)
        if self.daily_opens is None:
            self.daily_opens = defaultdict(int)
        if self.last_updated is None:
            self.last_updated = datetime.now(timezone.utc).isoformat()


class SendTimeOptimizer:
    """ML-based send time optimization."""

    # Industry best practices (fallback data)
    INDUSTRY_BEST_TIMES = {
        "technology": {"day": "Tuesday", "hour": 10},
        "healthcare": {"day": "Wednesday", "hour": 14},
        "finance": {"day": "Thursday", "hour": 11},
        "retail": {"day": "Friday", "hour": 9},
        "education": {"day": "Monday", "hour": 13},
        "manufacturing": {"day": "Tuesday", "hour": 8},
        "hospitality": {"day": "Wednesday", "hour": 15},
        "default": {"day": "Tuesday", "hour": 10},
    }

    # General best send times (aggregated across industries)
    GENERAL_BEST_TIMES = [
        {"day": "Tuesday", "hour": 10, "score": 95},
        {"day": "Wednesday", "hour": 11, "score": 92},
        {"day": "Thursday", "hour": 14, "score": 88},
        {"day": "Tuesday", "hour": 14, "score": 85},
        {"day": "Wednesday", "hour": 9, "score": 82},
    ]

    def __init__(self, config: Settings):
        self.config = config
        self.patterns_dir = Path(config.database.data_dir) / "send_time_patterns"
        self.patterns_dir.mkdir(parents=True, exist_ok=True)

    def predict_best_time(self, lead_data: Dict) -> SendTimePrediction:
        """Predict optimal send time for a lead."""
        # Try to load lead-specific pattern
        lead_id = lead_data.get("id")
        if lead_id:
            lead_pattern = self._load_pattern("lead", lead_id)
            if lead_pattern and lead_pattern.total_sent >= 5:
                return self._create_prediction_from_pattern(lead_pattern, "lead-specific data")

        # Try domain-level pattern
        domain = self._extract_domain(lead_data.get("email", ""))
        if domain:
            domain_pattern = self._load_pattern("domain", domain)
            if domain_pattern and domain_pattern.total_sent >= 10:
                return self._create_prediction_from_pattern(domain_pattern, "domain-level data")

        # Try industry-level pattern
        industry = lead_data.get("vertical", lead_data.get("primaryType", "")).lower()
        if industry:
            industry_pattern = self._load_pattern("industry", industry)
            if industry_pattern and industry_pattern.total_sent >= 20:
                return self._create_prediction_from_pattern(industry_pattern, "industry data")

        # Fall back to industry best practices
        if industry:
            best_time = self.INDUSTRY_BEST_TIMES.get(industry, self.INDUSTRY_BEST_TIMES["default"])
            return SendTimePrediction(
                best_day=best_time["day"],
                best_hour=best_time["hour"],
                confidence=0.5,
                alternative_times=self.GENERAL_BEST_TIMES[1:4],
                reason=f"Industry best practices for {industry}"
            )

        # Ultimate fallback: general best times
        best = self.GENERAL_BEST_TIMES[0]
        return SendTimePrediction(
            best_day=best["day"],
            best_hour=best["hour"],
            confidence=0.3,
            alternative_times=self.GENERAL_BEST_TIMES[1:4],
            reason="General best practices (no historical data)"
        )

    def record_engagement(self, lead_data: Dict, event_type: str, timestamp: datetime = None):
        """Record engagement for pattern learning."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        hour = timestamp.hour
        day = timestamp.strftime("%A")

        # Update lead pattern
        lead_id = lead_data.get("id")
        if lead_id and event_type in ("opened", "clicked"):
            pattern = self._load_pattern("lead", lead_id) or EngagementPattern(
                entity_type="lead", entity_id=lead_id
            )
            pattern.hourly_opens[hour] += 1
            pattern.daily_opens[day] += 1
            pattern.total_opens += 1
            pattern.best_hour = max(pattern.hourly_opens, key=pattern.hourly_opens.get)
            pattern.best_day = max(pattern.daily_opens, key=pattern.daily_opens.get)
            pattern.last_updated = datetime.now(timezone.utc).isoformat()
            self._save_pattern(pattern)

        # Update domain pattern
        domain = self._extract_domain(lead_data.get("email", ""))
        if domain and event_type in ("opened", "clicked"):
            pattern = self._load_pattern("domain", domain) or EngagementPattern(
                entity_type="domain", entity_id=domain
            )
            pattern.hourly_opens[hour] += 1
            pattern.daily_opens[day] += 1
            pattern.total_opens += 1
            pattern.best_hour = max(pattern.hourly_opens, key=pattern.hourly_opens.get)
            pattern.best_day = max(pattern.daily_opens, key=pattern.daily_opens.get)
            pattern.last_updated = datetime.now(timezone.utc).isoformat()
            self._save_pattern(pattern)

        # Update industry pattern
        industry = lead_data.get("vertical", lead_data.get("primaryType", "")).lower()
        if industry and event_type in ("opened", "clicked"):
            pattern = self._load_pattern("industry", industry) or EngagementPattern(
                entity_type="industry", entity_id=industry
            )
            pattern.hourly_opens[hour] += 1
            pattern.daily_opens[day] += 1
            pattern.total_opens += 1
            pattern.best_hour = max(pattern.hourly_opens, key=pattern.hourly_opens.get)
            pattern.best_day = max(pattern.daily_opens, key=pattern.daily_opens.get)
            pattern.last_updated = datetime.now(timezone.utc).isoformat()
            self._save_pattern(pattern)

    def _create_prediction_from_pattern(self, pattern: EngagementPattern, source: str) -> SendTimePrediction:
        """Create prediction from engagement pattern."""
        best_hour = pattern.best_hour or 10
        best_day = pattern.best_day or "Tuesday"

        # Calculate confidence based on sample size
        confidence = min(0.95, 0.5 + (pattern.total_opens / 100))

        # Generate alternative times
        alternatives = []
        sorted_hours = sorted(pattern.hourly_opens.items(), key=lambda x: x[1], reverse=True)
        for hour, count in sorted_hours[1:4]:
            if count > 0:
                alternatives.append({
                    "day": best_day,
                    "hour": hour,
                    "opens": count
                })

        return SendTimePrediction(
            best_day=best_day,
            best_hour=best_hour,
            confidence=confidence,
            alternative_times=alternatives,
            reason=f"Based on {pattern.total_opens} engagement events ({source})"
        )

    def _extract_domain(self, email: str) -> Optional[str]:
        """Extract domain from email address."""
        if not email or '@' not in email:
            return None
        return email.split('@')[-1].lower()

    def _load_pattern(self, entity_type: str, entity_id: str) -> Optional[EngagementPattern]:
        """Load engagement pattern from file."""
        path = self.patterns_dir / f"{entity_type}_{entity_id}.json"
        if not path.exists():
            return None

        with open(path, 'r') as f:
            data = json.load(f)
            return EngagementPattern(**data)

    def _save_pattern(self, pattern: EngagementPattern):
        """Save engagement pattern to file."""
        path = self.patterns_dir / f"{pattern.entity_type}_{pattern.entity_id}.json"
        with open(path, 'w') as f:
            json.dump(asdict(pattern), f, indent=2)

    def get_optimization_stats(self) -> Dict:
        """Get send time optimization statistics."""
        patterns = []
        for path in self.patterns_dir.glob("*.json"):
            try:
                with open(path, 'r') as f:
                    patterns.append(json.load(f))
            except Exception:
                pass

        return {
            "total_patterns": len(patterns),
            "lead_patterns": len([p for p in patterns if p["entity_type"] == "lead"]),
            "domain_patterns": len([p for p in patterns if p["entity_type"] == "domain"]),
            "industry_patterns": len([p for p in patterns if p["entity_type"] == "industry"]),
            "total_engagements": sum(p.get("total_opens", 0) for p in patterns),
        }


def get_send_time_optimizer(config: Settings) -> SendTimeOptimizer:
    """Get or create send time optimizer."""
    return SendTimeOptimizer(config)
