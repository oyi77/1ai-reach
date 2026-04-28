"""Email bounce & unsubscribe handler - maintains list hygiene.

Features:
- Bounce detection and classification (hard vs soft)
- Automatic suppression list management
- Unsubscribe link generation and tracking
- One-click unsubscribe handling
- Complaint tracking (spam reports)
- List hygiene scoring

Compliance: CAN-SPAM, GDPR, CASL
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json
import hashlib
import re

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class BounceHandler:
    """Handles email bounces and maintains suppression list."""
    
    BOUNCE_TYPES = {
        "hard": [
            "user unknown", "mailbox not found", "no such user",
            "address rejected", "invalid recipient", "permanent",
            "5.1.1", "5.2.1", "5.1.0"
        ],
        "soft": [
            "mailbox full", "over quota", "temporarily unavailable",
            "service unavailable", "try again later", "deferred",
            "4.2.2", "4.3.1", "message delayed"
        ],
        "spam": [
            "spam", "blocked", "reputation", "blacklist",
            "content rejected", "policy violation"
        ]
    }
    
    def __init__(self, config: Settings):
        self.config = config
        self.compliance_dir = Path(config.database.data_dir) / "compliance"
        self.compliance_dir.mkdir(parents=True, exist_ok=True)
        self.bounce_file = self.compliance_dir / "bounces.json"
        self.suppression_file = self.compliance_dir / "suppression_list.json"
        self.unsubscribe_file = self.compliance_dir / "unsubscribes.json"
    
    def process_bounce(self, email: str, bounce_message: str, lead_id: str = None) -> Tuple[str, bool]:
        """Process a bounce notification and classify it.
        
        Returns:
            Tuple of (bounce_type: str, should_suppress: bool)
        """
        bounce_type = self._classify_bounce(bounce_message)
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Record bounce
        bounces = self._load_bounces()
        bounces.append({
            "email": email,
            "lead_id": lead_id,
            "bounce_type": bounce_type,
            "message": bounce_message[:500],
            "timestamp": timestamp
        })
        bounces = bounces[-5000:]  # Keep last 5000
        self._save_bounces(bounces)
        
        # Determine if should suppress
        should_suppress = bounce_type in ("hard", "spam")
        
        if should_suppress:
            self.add_to_suppression(email, f"bounce_{bounce_type}", lead_id)
            logger.warning(f"Suppressed {email} due to {bounce_type} bounce")
        
        return bounce_type, should_suppress
    
    def _classify_bounce(self, bounce_message: str) -> str:
        """Classify bounce type from error message."""
        message_lower = bounce_message.lower()
        
        # Check for spam complaints
        if any(kw in message_lower for kw in self.BOUNCE_TYPES["spam"]):
            return "spam"
        
        # Check for hard bounces
        if any(kw in message_lower for kw in self.BOUNCE_TYPES["hard"]):
            return "hard"
        
        # Check for soft bounces
        if any(kw in message_lower for kw in self.BOUNCE_TYPES["soft"]):
            return "soft"
        
        # Default to soft (give benefit of doubt)
        return "soft"
    
    def add_to_suppression(self, email: str, reason: str, lead_id: str = None):
        """Add email to suppression list."""
        suppression = self._load_suppression()
        
        email_hash = hashlib.md5(email.encode()).hexdigest()
        
        # Check if already suppressed
        if email_hash in suppression:
            suppression[email_hash]["reasons"].append(reason)
            suppression[email_hash]["updated_at"] = datetime.now(timezone.utc).isoformat()
        else:
            suppression[email_hash] = {
                "email": email,
                "lead_id": lead_id,
                "reasons": [reason],
                "added_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        
        self._save_suppression(suppression)
        logger.info(f"Added {email} to suppression list: {reason}")
    
    def is_suppressed(self, email: str) -> bool:
        """Check if email is on suppression list."""
        suppression = self._load_suppression()
        email_hash = hashlib.md5(email.encode()).hexdigest()
        return email_hash in suppression
    
    def generate_unsubscribe_link(self, email: str, lead_id: str) -> str:
        """Generate one-click unsubscribe link."""
        token_data = f"{email}:{lead_id}:secret"
        token = hashlib.sha256(token_data.encode()).hexdigest()[:16]
        return f"https://reach.aitradepulse.com/api/v1/unsubscribe/{lead_id}/{token}?email={email}"
    
    def process_unsubscribe(self, email: str, token: str, lead_id: str) -> bool:
        """Process unsubscribe request."""
        expected_token_data = f"{email}:{lead_id}:secret"
        expected_token = hashlib.sha256(expected_token_data.encode()).hexdigest()[:16]
        
        if token != expected_token:
            logger.warning(f"Invalid unsubscribe token for {email}")
            return False
        
        self.add_to_suppression(email, "unsubscribe_request", lead_id)
        
        unsubscribes = self._load_unsubscribes()
        unsubscribes.append({
            "email": email,
            "lead_id": lead_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "link"
        })
        self._save_unsubscribes(unsubscribes)
        
        logger.info(f"Processed unsubscribe for {email}")
        return True
    
    def get_list_health_score(self) -> Dict:
        """Calculate email list health score."""
        bounces = self._load_bounces()
        suppression = self._load_suppression()
        unsubscribes = self._load_unsubscribes()
        
        # Count by type
        hard_bounces = len([b for b in bounces if b["bounce_type"] == "hard"])
        soft_bounces = len([b for b in bounces if b["bounce_type"] == "soft"])
        spam_complaints = len([b for b in bounces if b["bounce_type"] == "spam"])
        
        # Calculate score (100 = perfect)
        total_issues = hard_bounces + (soft_bounces * 0.3) + spam_complaints + len(unsubscribes)
        
        # Penalize heavily for hard bounces and spam complaints
        penalty = (hard_bounces * 5) + (spam_complaints * 10) + len(suppression)
        
        score = max(0, 100 - penalty)
        
        # Health status
        if score >= 90:
            status = "excellent"
        elif score >= 70:
            status = "good"
        elif score >= 50:
            status = "fair"
        else:
            status = "poor"
        
        return {
            "score": score,
            "status": status,
            "hard_bounces": hard_bounces,
            "soft_bounces": soft_bounces,
            "spam_complaints": spam_complaints,
            "total_unsubscribes": len(unsubscribes),
            "suppression_list_size": len(suppression)
        }
    
    def cleanup_old_soft_bounces(self, days: int = 30):
        """Remove old soft bounces (they may be temporary)."""
        bounces = self._load_bounces()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        cleaned = []
        removed = 0
        
        for bounce in bounces:
            try:
                bounce_date = datetime.fromisoformat(bounce["timestamp"]).replace(tzinfo=timezone.utc)
                if bounce["bounce_type"] != "soft" or bounce_date > cutoff:
                    cleaned.append(bounce)
                else:
                    removed += 1
            except Exception:
                cleaned.append(bounce)
        
        self._save_bounces(cleaned)
        logger.info(f"Cleaned up {removed} old soft bounces")
        return removed
    
    def _load_bounces(self) -> List[Dict]:
        return json.load(open(self.bounce_file)) if self.bounce_file.exists() else []
    
    def _save_bounces(self, bounces: List[Dict]):
        with open(self.bounce_file, 'w') as f:
            json.dump(bounces, f, indent=2)
    
    def _load_suppression(self) -> Dict:
        return json.load(open(self.suppression_file)) if self.suppression_file.exists() else {}
    
    def _save_suppression(self, suppression: Dict):
        with open(self.suppression_file, 'w') as f:
            json.dump(suppression, f, indent=2)
    
    def _load_unsubscribes(self) -> List[Dict]:
        return json.load(open(self.unsubscribe_file)) if self.unsubscribe_file.exists() else []
    
    def _save_unsubscribes(self, unsubscribes: List[Dict]):
        with open(self.unsubscribe_file, 'w') as f:
            json.dump(unsubscribes, f, indent=2)


def get_bounce_handler(config: Settings) -> BounceHandler:
    """Get or create bounce handler."""
    return BounceHandler(config)
