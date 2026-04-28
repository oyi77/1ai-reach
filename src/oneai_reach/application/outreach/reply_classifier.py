"""LLM-based reply classification service.

Classifies email and WhatsApp replies into categories:
- positive: Interested, wants to meet, asking for more info
- negative: Not interested, unsubscribing, rude
- neutral: Acknowledgment, out of office, wrong contact
- inquiry: Has questions about service/pricing
"""

import re
from typing import Optional, Tuple
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

class ReplyClassifier:
    """Classifies outreach replies using pattern matching."""
    
    def __init__(self):
        pass
    
    def classify(self, reply_text: str) -> Tuple[str, int]:
        """Classify a reply and return (category, confidence).
        
        Args:
            reply_text: The reply text to classify
            
        Returns:
            Tuple of (category, confidence_score)
            Categories: positive, negative, neutral, inquiry
        """
        if not reply_text or len(reply_text.strip()) < 5:
            return ("neutral", 50)
        
        result = self._heuristic_classify(reply_text)
        return result or ("neutral", 50)
    
    def _heuristic_classify(self, text: str) -> Optional[Tuple[str, int]]:
        """Heuristic classification with comprehensive patterns."""
        text_lower = text.lower()
        
        # Strong positive signals
        positive_patterns = [
            (r"\b(interested|very interested|quite interested)\b", 90),
            (r"\b(yes|yeah|yep|sure|certainly|definitely)\b.*\b(interested|meeting|call|demo|discuss|chat)\b", 92),
            (r"\b(let'?s|lets)\b.*\b(schedule|meet|talk|connect|hop on|get on)\b", 90),
            (r"\b(more info|more information|learn more|tell me more)\b", 85),
            (r"\b(send me|send us|share)\b.*\b(proposal|pricing|details|information|deck|brochure)\b", 88),
            (r"\b(looks (great|good|interesting|promising)|this looks)\b", 82),
            (r"\b(i'?d (like|love)|we'?d (like|love))\b.*\b(to (hear|learn|know|discuss)|more)\b", 85),
            (r"\b(next steps|how to proceed|moving forward)\b", 83),
            (r"\b(set up|arrange|book)\b.*\b(meeting|call|appointment|demo)\b", 90),
            (r"\b(impressive|exciting|compelling)\b", 80),
        ]
        
        # Strong negative signals
        negative_patterns = [
            (r"\b(not interested|no thanks|no thank you|not interested|not intrested)\b", 95),
            (r"\b(remove|unsubscribe|opt-out|opt out|delete)\b.*\b(me|us|from list)\b", 98),
            (r"\b(stop contacting|don'?t contact|do not contact|stop emailing)\b", 97),
            (r"\b(spam|unwanted|unsolicited|junk)\b", 92),
            (r"\b(never|ever)\b.*\b(contact|email|call|message)\b.*\b(again|us|me)\b", 96),
            (r"\b(no budget|no money|can'?t afford|too expensive)\b", 88),
            (r"\b(already (have|using|working with)|satisfied with current)\b", 85),
            (r"\b(not a (fit|priority|need)|not right (time|now))\b", 82),
        ]
        
        # Neutral signals
        neutral_patterns = [
            (r"\b(out of (office|town)|ooo|on vacation|away until|returning)\b", 95),
            (r"\b(auto[- ]reply|automatic reply|out of office)\b", 98),
            (r"\b(wrong (person|contact|email|address|company))\b", 93),
            (r"\b(not the (right|correct))\b.*\b(person|contact|department)\b", 91),
            (r"\b(thanks for reaching out|thank you for (your|the))\b.*\b(however|but|unfortunately)\b", 75),
            (r"\b(i'?ll (keep|save)|we'?ll (keep|save))\b.*\b(on file|for future|in mind)\b", 70),
            (r"\b( circling back|following up)\b.*\b(not (available|ready))\b", 65),
        ]
        
        # Inquiry signals
        inquiry_patterns = [
            (r"\b(how much|what('?s| is)? the|pricing|price|cost|fee|rates)\b", 90),
            (r"\b(what (do|does)|how (do|does)|can you tell)\b.*\b(work|function|operate)\b", 85),
            (r"\b(question|questions|wondering|curious)\b", 80),
            (r"\b(service|services|package|packages|offerings|products)\b.*\b(include|cover|provide|offer)\b", 85),
            (r"\b(do you (offer|have|provide)|are you able to)\b", 82),
            (r"\b(what about|how about|can you)\b.*\b(integrate|custom|customize)\b", 83),
            (r"\b(case study|success story|client (example|story)|testimonial)\b", 78),
            (r"\b(implementation|onboarding|setup|integration)\b.*\b(work|process|timeline)\b", 84),
        ]
        
        # Check patterns by priority (highest confidence first)
        all_patterns = [
            ("negative", negative_patterns),
            ("neutral", neutral_patterns),
            ("positive", positive_patterns),
            ("inquiry", inquiry_patterns),
        ]
        
        best_match = None
        best_confidence = 0
        
        for category, patterns in all_patterns:
            for pattern, confidence in patterns:
                if re.search(pattern, text_lower):
                    if confidence > best_confidence:
                        best_match = (category, confidence)
                        best_confidence = confidence
        
        # Only return if confidence is high enough
        if best_confidence >= 75:
            return best_match
        
        return None
    
    def get_priority_score(self, category: str, confidence: int) -> int:
        """Calculate follow-up priority score (0-100).
        
        Higher scores = more urgent follow-up needed.
        """
        base_scores = {
            "positive": 90,
            "inquiry": 80,
            "neutral": 30,
            "negative": 10,
        }
        base = base_scores.get(category, 30)
        # Adjust by confidence
        adjustment = (confidence - 50) * 0.2
        return max(0, min(100, int(base + adjustment)))
