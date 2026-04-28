"""Intent signal detection - identifies buying signals from leads.

Monitors and detects:
- Funding news (Series A, B, C, etc.)
- Job postings (key roles indicating growth)
- Tech stack changes (new tools = budget)
- Leadership changes (new decision makers)
- Expansion signals (new offices, markets)

These signals indicate high intent and should trigger:
- Priority lead scoring boost
- Personalized outreach mentioning the signal
- Immediate follow-up (timing advantage)
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json
import hashlib

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger
from oneai_reach.infrastructure.web_reader import JinaWebReader

logger = get_logger(__name__)


class IntentSignal:
    """Represents a detected intent signal."""
    
    def __init__(self, lead_id: str, signal_type: str, description: str, 
                 source_url: str, detected_at: datetime, confidence: float):
        self.lead_id = lead_id
        self.signal_type = signal_type  # funding, hiring, tech_change, leadership, expansion
        self.description = description
        self.source_url = source_url
        self.detected_at = detected_at
        self.confidence = confidence  # 0.0-1.0
        self.acted_on = False
    
    def to_dict(self) -> Dict:
        return {
            "lead_id": self.lead_id,
            "signal_type": self.signal_type,
            "description": self.description,
            "source_url": self.source_url,
            "detected_at": self.detected_at.isoformat(),
            "confidence": self.confidence,
            "acted_on": self.acted_on
        }


class IntentDetector:
    """Detects buying intent signals from various sources."""
    
    SIGNAL_TYPES = ["funding", "hiring", "tech_change", "leadership", "expansion"]
    
    def __init__(self, config: Settings):
        self.config = config
        try:
            self.jina_client = JinaWebReader(config)
        except Exception:
            self.jina_client = None
        self.signals_dir = Path(config.database.data_dir) / "intent_signals"
        self.signals_dir.mkdir(parents=True, exist_ok=True)
        self.signals_file = self.signals_dir / "signals.json"
    
    def detect_funding_news(self, company_name: str, lead_id: str) -> List[IntentSignal]:
        """Detect recent funding announcements for a company."""
        signals = []
        
        if not self.jina_client:
            return signals
        
        query = f"{company_name} funding round Series investment 2024 2025 2026"
        
        try:
            result = self.jina_client.search(query)
            if result and "results" in result:
                for item in result["results"][:5]:
                    title = item.get("title", "").lower()
                    if any(kw in title for kw in ["funding", "series", "investment", "raised", "venture"]):
                        signal = IntentSignal(
                            lead_id=lead_id,
                            signal_type="funding",
                            description=f"Funding detected: {item.get('title', 'Funding announced')}",
                            source_url=item.get("url", ""),
                            detected_at=datetime.now(timezone.utc),
                            confidence=0.9
                        )
                        signals.append(signal)
        except Exception as e:
            logger.error(f"Funding detection error for {company_name}: {e}")
        
        return signals
    
    def detect_hiring_signals(self, company_name: str, lead_id: str) -> List[IntentSignal]:
        """Detect aggressive hiring (indicates growth & budget)."""
        signals = []
        
        if not self.jina_client:
            return signals
        
        query = f"{company_name} hiring jobs careers \"we're hiring\" team"
        
        try:
            result = self.jina_client.search(query)
            if result and "results" in result:
                hiring_count = 0
                for item in result["results"][:10]:
                    title = item.get("title", "").lower()
                    if any(kw in title for kw in ["hiring", "jobs", "careers", "join our team"]):
                        hiring_count += 1
                
                if hiring_count >= 3:
                    signal = IntentSignal(
                        lead_id=lead_id,
                        signal_type="hiring",
                        description=f"Aggressive hiring detected ({hiring_count} job postings)",
                        source_url=result["results"][0].get("url", ""),
                        detected_at=datetime.now(timezone.utc),
                        confidence=min(0.5 + (hiring_count * 0.1), 0.95)
                    )
                    signals.append(signal)
        except Exception as e:
            logger.error(f"Hiring detection error for {company_name}: {e}")
        
        return signals
    
    def detect_tech_stack_changes(self, company_website: str, lead_id: str) -> List[IntentSignal]:
        """Detect recent tech stack additions (indicates digital transformation)."""
        signals = []
        
        try:
            # Read website content
            content = self.jina_client.read_url(company_website)
            if content:
                # Look for tech stack indicators
                tech_keywords = {
                    "salesforce": "CRM implementation",
                    "hubspot": "Marketing automation",
                    "aws": "Cloud infrastructure",
                    "shopify": "E-commerce platform",
                    "stripe": "Payment processing",
                    "intercom": "Customer support tool",
                    "slack": "Team collaboration",
                    "notion": "Productivity tools",
                }
                
                detected_techs = []
                content_lower = content.lower()
                for tech, description in tech_keywords.items():
                    if tech in content_lower:
                        detected_techs.append(description)
                
                if len(detected_techs) >= 2:
                    signal = IntentSignal(
                        lead_id=lead_id,
                        signal_type="tech_change",
                        description=f"Tech stack expansion: {', '.join(detected_techs[:3])}",
                        source_url=company_website,
                        detected_at=datetime.now(timezone.utc),
                        confidence=0.7
                    )
                    signals.append(signal)
        except Exception as e:
            logger.error(f"Tech stack detection error for {company_website}: {e}")
        
        return signals
    
    def detect_leadership_changes(self, company_name: str, lead_id: str) -> List[IntentSignal]:
        """Detect new C-level hires (new decision makers)."""
        signals = []
        query = f"{company_name} CEO CTO CFO CMO \"Chief\" appointed announced 2024 2025"
        
        try:
            result = self.jina_client.search(query)
            if result and "results" in result:
                for item in result["results"][:5]:
                    title = item.get("title", "").lower()
                    if any(kw in title for kw in ["ceo", "cto", "cfo", "cmo", "chief", "appointed", "joins"]):
                        signal = IntentSignal(
                            lead_id=lead_id,
                            signal_type="leadership",
                            description=f"Leadership change: {item.get('title', 'New executive')}",
                            source_url=item.get("url", ""),
                            detected_at=datetime.now(timezone.utc),
                            confidence=0.85
                        )
                        signals.append(signal)
                        break  # Only first one
        except Exception as e:
            logger.error(f"Leadership detection error for {company_name}: {e}")
        
        return signals
    
    def generate_intent_message(self, signal: IntentSignal, company_name: str) -> str:
        """Generate personalized outreach message mentioning the intent signal."""
        
        if signal.signal_type == "funding":
            return f"""Hi! Congratulations on the recent funding news - exciting times ahead for {company_name}!

With fresh capital, you're probably looking to invest in growth initiatives. We've helped similar funded companies scale their operations efficiently.

Worth a 15-min chat about how we can support your growth plans?

Best,
BerkahKarya Team"""
        
        elif signal.signal_type == "hiring":
            return f"""Hi! Noticed {company_name} is on a hiring spree - looks like you're scaling fast!

Rapid growth often means operational challenges. We specialize in helping companies like yours streamline processes during expansion.

Open to exploring how we can help?

Best,
BerkahKarya Team"""
        
        elif signal.signal_type == "tech_change":
            return f"""Hi! Impressed by {company_name}'s tech stack upgrades - clearly investing in digital transformation!

We help companies maximize ROI from their new tools through automation and integration.

Interested in a quick chat about optimization opportunities?

Best,
BerkahKarya Team"""
        
        elif signal.signal_type == "leadership":
            return f"""Hi! Congrats on the new leadership at {company_name} - exciting direction ahead!

New executives often bring fresh initiatives. We'd love to support your team's goals with our automation expertise.

Worth a conversation?

Best,
BerkahKarya Team"""
        
        else:  # expansion
            return f"""Hi! Exciting to see {company_name} expanding - growth is always a good problem to have!

We help companies scale operations smoothly during expansion phases.

Any interest in exploring how we can support your growth?

Best,
BerkahKarya Team"""
    
    def scan_lead(self, company_name: str, company_website: str, lead_id: str) -> List[IntentSignal]:
        """Run all intent detection scans on a single lead."""
        all_signals = []
        
        logger.info(f"Scanning intent signals for {company_name}")
        
        # Run all detectors
        all_signals.extend(self.detect_funding_news(company_name, lead_id))
        all_signals.extend(self.detect_hiring_signals(company_name, lead_id))
        all_signals.extend(self.detect_tech_stack_changes(company_website, lead_id))
        all_signals.extend(self.detect_leadership_changes(company_name, lead_id))
        
        # Save signals
        self._save_signals(all_signals)
        
        if all_signals:
            logger.info(f"Detected {len(all_signals)} intent signals for {company_name}")
        
        return all_signals
    
    def get_priority_score(self, signals: List[IntentSignal]) -> int:
        """Calculate priority score boost based on detected signals."""
        if not signals:
            return 0
        
        score = 0
        for signal in signals:
            # Funding = highest priority (budget confirmed)
            if signal.signal_type == "funding":
                score += 30
            # Leadership = high priority (new decision maker)
            elif signal.signal_type == "leadership":
                score += 25
            # Hiring = medium-high (growth = budget)
            elif signal.signal_type == "hiring":
                score += 20
            # Tech change = medium (digital transformation)
            elif signal.signal_type == "tech_change":
                score += 15
            # Expansion = medium
            elif signal.signal_type == "expansion":
                score += 15
            
            # Confidence multiplier
            score = int(score * signal.confidence)
        
        return min(score, 100)  # Cap at 100
    
    def _save_signals(self, signals: List[IntentSignal]):
        """Save detected signals to file."""
        existing = self._load_signals()
        
        for signal in signals:
            # Avoid duplicates
            signal_hash = hashlib.md5(f"{signal.lead_id}:{signal.source_url}".encode()).hexdigest()
            if not any(s.get("hash") == signal_hash for s in existing):
                signal_dict = signal.to_dict()
                signal_dict["hash"] = signal_hash
                existing.append(signal_dict)
        
        # Keep last 10000 signals
        existing = existing[-10000:]
        
        with open(self.signals_file, 'w') as f:
            json.dump(existing, f, indent=2)
    
    def _load_signals(self) -> List[Dict]:
        """Load existing signals from file."""
        if self.signals_file.exists():
            with open(self.signals_file) as f:
                return json.load(f)
        return []
    
    def get_unacted_signals(self, lead_id: str) -> List[Dict]:
        """Get signals that haven't been acted on yet."""
        all_signals = self._load_signals()
        return [s for s in all_signals if s["lead_id"] == lead_id and not s.get("acted_on", False)]
    
    def mark_signal_acted(self, signal_hash: str):
        """Mark a signal as acted on."""
        signals = self._load_signals()
        for signal in signals:
            if signal.get("hash") == signal_hash:
                signal["acted_on"] = True
                break
        with open(self.signals_file, 'w') as f:
            json.dump(signals, f, indent=2)


def get_intent_detector(config: Settings) -> IntentDetector:
    """Get or create intent detector."""
    return IntentDetector(config)
