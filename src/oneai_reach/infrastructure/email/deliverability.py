"""Email deliverability monitoring and optimization."""

import dns.resolver
import re
import time
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, asdict, field
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class DomainHealthResult:
    domain: str
    spf_valid: bool = False
    spf_record: Optional[str] = None
    dkim_valid: bool = False
    dkim_selectors: List[str] = field(default_factory=list)
    dmarc_valid: bool = False
    dmarc_record: Optional[str] = None
    dmarc_policy: str = "none"
    mx_records: List[str] = field(default_factory=list)
    score: int = 0
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SpamScoreResult:
    content: str
    score: float = 0.0
    threshold: float = 5.0
    is_spammy: bool = False
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.is_spammy = self.score >= self.threshold


@dataclass
class WarmupStatus:
    email: str
    day: int = 1
    daily_limit: int = 10
    sent_today: int = 0
    total_sent: int = 0
    total_received: int = 0
    spam_complaints: int = 0
    bounce_count: int = 0
    reputation_score: int = 50
    status: str = "active"
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_sent_at: Optional[str] = None


class DomainHealthChecker:
    COMMON_DKIM_SELECTORS = ["default", "mail", "selector1", "selector2", "google", "brevo", "sendgrid"]

    def check(self, domain: str) -> DomainHealthResult:
        result = DomainHealthResult(domain=domain)
        
        # Check SPF
        try:
            spf_records = dns.resolver.resolve(domain, 'TXT')
            for record in spf_records:
                txt = str(record).strip('"')
                if txt.startswith('v=spf1'):
                    result.spf_valid = True
                    result.spf_record = txt
                    break
        except Exception as e:
            result.issues.append(f"SPF lookup failed")

        # Check DKIM
        for selector in self.COMMON_DKIM_SELECTORS:
            try:
                dkim_domain = f"{selector}._domainkey.{domain}"
                dkim_records = dns.resolver.resolve(dkim_domain, 'TXT')
                for record in dkim_records:
                    txt = str(record).strip('"')
                    if 'v=DKIM1' in txt or 'k=rsa' in txt:
                        result.dkim_valid = True
                        result.dkim_selectors.append(selector)
                        break
            except Exception:
                continue

        # Check DMARC
        try:
            dmarc_domain = f"_dmarc.{domain}"
            dmarc_records = dns.resolver.resolve(dmarc_domain, 'TXT')
            for record in dmarc_records:
                txt = str(record).strip('"')
                if txt.startswith('v=DMARC1'):
                    result.dmarc_valid = True
                    result.dmarc_record = txt
                    if 'p=reject' in txt:
                        result.dmarc_policy = "reject"
                    elif 'p=quarantine' in txt:
                        result.dmarc_policy = "quarantine"
                    break
        except Exception:
            result.issues.append(f"DMARC lookup failed")

        # Check MX
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            result.mx_records = [str(r.exchange).rstrip('.') for r in mx_records]
        except Exception:
            result.issues.append(f"MX lookup failed")

        result.score = self._calculate_score(result)
        self._add_recommendations(result)
        return result

    def _calculate_score(self, result: DomainHealthResult) -> int:
        score = 0
        if result.spf_valid: score += 25
        else: result.issues.append("Missing SPF record")
        
        if result.dkim_valid: score += 25
        else: result.issues.append("Missing DKIM record")
        
        if result.dmarc_valid:
            score += 30
            if result.dmarc_policy == "reject": score += 10
            elif result.dmarc_policy == "quarantine": score += 5
        else: result.issues.append("Missing DMARC record")
        
        if result.mx_records: score += 10
        else: result.issues.append("No MX records")
        
        return min(100, score)

    def _add_recommendations(self, result: DomainHealthResult):
        if not result.spf_valid:
            result.recommendations.append("Add SPF: v=spf1 include:_spf.brevo.com ~all")
        if not result.dkim_valid:
            result.recommendations.append("Configure DKIM in email provider")
        if not result.dmarc_valid:
            result.recommendations.append("Add DMARC: v=DMARC1; p=quarantine")


class SpamScoreChecker:
    SPAM_WORDS = {
        "high": ["free money", "cash bonus", "lottery", "risk-free", "guaranteed income", "earn $", "make money fast", "congratulations", "you've been selected", "no cost", "free gift"],
        "medium": ["opportunity", "investment", "profit", "limited time", "expires", "call now", "act now", "urgent"],
        "low": ["sale", "offer", "deal", "discount", "buy", "subscribe"]
    }

    def check(self, subject: str, body: str, from_email: str) -> SpamScoreResult:
        result = SpamScoreResult(content=f"{subject} {body}")
        full_text = f"{subject} {body}".lower()

        for risk, words in self.SPAM_WORDS.items():
            weight = {"high": 2.0, "medium": 1.0, "low": 0.5}[risk]
            for word in words:
                if word in full_text:
                    result.score += weight
                    result.issues.append(f"Trigger: '{word}'")

        if re.search(r'\b[A-Z]{4,}\b', subject):
            result.score += 1.0
            result.issues.append("Excessive ALL CAPS")
        
        if re.search(r'!{3,}', subject + body):
            result.score += 1.0
            result.issues.append("Too many exclamation marks")

        if self._is_free_email(from_email):
            result.score += 2.0
            result.issues.append("Free email domain")

        self._generate_recommendations(result)
        return result

    def _is_free_email(self, email: str) -> bool:
        free = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com"}
        return email.split('@')[-1].lower() in free

    def _generate_recommendations(self, result: SpamScoreResult):
        if result.score >= 5:
            result.recommendations.append("Remove spam trigger words")
            result.recommendations.append("Use professional domain")


class EmailWarmupService:
    def __init__(self, data_dir: str = "data"):
        self.warmup_dir = Path(data_dir) / "email_warmup"
        self.warmup_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self.warmup_dir / "warmup_state.json"

    def start_warmup(self, email: str) -> WarmupStatus:
        status = WarmupStatus(email=email)
        self._save_status(status)
        return status

    def get_status(self, email: str) -> Optional[WarmupStatus]:
        state = self._load_state()
        data = state.get(email)
        return WarmupStatus(**data) if data else None

    def can_send(self, email: str) -> Tuple[bool, str]:
        status = self.get_status(email)
        if not status: return True, "No warm-up"
        if status.status == "paused": return False, "Warm-up paused"
        if status.status == "completed": return True, "Completed"
        if status.sent_today >= status.daily_limit:
            return False, f"Daily limit ({status.daily_limit}) reached"
        return True, "OK"

    def record_send(self, email: str):
        status = self.get_status(email)
        if not status: return
        status.sent_today += 1
        status.total_sent += 1
        status.last_sent_at = datetime.now().isoformat()
        self._save_status(status)

    def record_engagement(self, email: str, event: str):
        status = self.get_status(email)
        if not status: return
        if event in ("opened", "clicked"):
            status.total_received += 1
            status.reputation_score = min(100, status.reputation_score + 1)
        elif event == "spam":
            status.spam_complaints += 1
            status.reputation_score = max(0, status.reputation_score - 20)
        elif event == "bounce":
            status.bounce_count += 1
            status.reputation_score = max(0, status.reputation_score - 10)
        if status.reputation_score < 30:
            status.status = "paused"
        self._save_status(status)

    def _save_status(self, status: WarmupStatus):
        state = self._load_state()
        state[status.email] = asdict(status)
        with open(self._state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def _load_state(self) -> dict:
        if self._state_file.exists():
            with open(self._state_file, 'r') as f:
                return json.load(f)
        return {}


class DeliverabilityService:
    def __init__(self, data_dir: str = "data"):
        self.domain_checker = DomainHealthChecker()
        self.spam_checker = SpamScoreChecker()
        self.warmup_service = EmailWarmupService(data_dir)
        self._cache = {}

    def check_domain(self, domain: str) -> DomainHealthResult:
        cache_key = f"domain:{domain}"
        if cache_key in self._cache:
            t, r = self._cache[cache_key]
            if time.time() - t < 3600: return r
        result = self.domain_checker.check(domain)
        self._cache[cache_key] = (time.time(), result)
        return result

    def check_spam(self, subject: str, body: str, from_email: str) -> SpamScoreResult:
        return self.spam_checker.check(subject, body, from_email)

    def check_before_send(self, from_email: str, subject: str, body: str) -> Dict:
        domain = from_email.split('@')[-1]
        domain_health = self.check_domain(domain)
        spam_score = self.check_spam(subject, body, from_email)
        can_send, warmup_msg = self.warmup_service.can_send(from_email)
        status = self.warmup_service.get_status(from_email)

        issues = []
        if domain_health.score < 70: issues.append(f"Domain score: {domain_health.score}/100")
        if spam_score.is_spammy: issues.append(f"Spam score: {spam_score.score}/10")
        if not can_send: issues.append(warmup_msg)

        score = int((domain_health.score * 0.5) + ((10 - spam_score.score) * 10 * 0.3) + ((status.reputation_score if status else 50) * 0.2))

        return {
            "can_send": can_send and domain_health.score >= 50 and not spam_score.is_spammy,
            "deliverability_score": score,
            "domain_health": asdict(domain_health),
            "spam_score": asdict(spam_score),
            "warmup": asdict(status) if status else None,
            "issues": issues,
            "recommendations": domain_health.recommendations + spam_score.recommendations,
        }

    def start_warmup(self, email: str) -> WarmupStatus:
        return self.warmup_service.start_warmup(email)

    def record_event(self, email: str, event: str):
        self.warmup_service.record_engagement(email, event)


_service: Optional[DeliverabilityService] = None

def get_deliverability_service(data_dir: str = "data") -> DeliverabilityService:
    global _service
    if _service is None:
        _service = DeliverabilityService(data_dir)
    return _service
