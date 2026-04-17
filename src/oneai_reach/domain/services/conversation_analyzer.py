"""Conversation analyzer service - sentiment and intent analysis.

Pure business logic for analyzing conversation text to extract
sentiment, intent, and engagement signals.
"""

from typing import Dict, List


class ConversationAnalyzer:
    """Analyze conversation text for sentiment and intent.

    Uses keyword-based heuristics to determine:
    - Sentiment: positive, neutral, negative
    - Intent: question, complaint, purchase, feedback, other
    - Engagement level: high, medium, low

    This is a simplified rule-based analyzer. In production, this could
    be replaced with ML models or LLM-based analysis.
    """

    # Sentiment keywords
    POSITIVE_KEYWORDS = [
        "terima kasih",
        "thanks",
        "bagus",
        "good",
        "great",
        "excellent",
        "senang",
        "happy",
        "puas",
        "satisfied",
        "suka",
        "like",
        "love",
        "mantap",
        "oke",
        "ok",
        "baik",
        "setuju",
        "agree",
    ]

    NEGATIVE_KEYWORDS = [
        "mahal",
        "expensive",
        "buruk",
        "bad",
        "jelek",
        "kecewa",
        "disappointed",
        "tidak suka",
        "don't like",
        "hate",
        "benci",
        "lambat",
        "slow",
        "rusak",
        "broken",
        "gagal",
        "failed",
        "salah",
        "wrong",
        "error",
    ]

    # Intent keywords
    QUESTION_KEYWORDS = [
        "?",
        "apa",
        "what",
        "bagaimana",
        "how",
        "kapan",
        "when",
        "dimana",
        "where",
        "berapa",
        "how much",
        "kenapa",
        "why",
        "bisa",
        "can",
        "boleh",
        "may",
    ]

    COMPLAINT_KEYWORDS = [
        "komplain",
        "complaint",
        "masalah",
        "problem",
        "issue",
        "tidak berfungsi",
        "not working",
        "rusak",
        "broken",
        "kecewa",
        "disappointed",
        "refund",
        "kembalikan",
    ]

    PURCHASE_KEYWORDS = [
        "beli",
        "buy",
        "purchase",
        "order",
        "pesan",
        "booking",
        "bayar",
        "pay",
        "payment",
        "harga",
        "price",
        "berapa",
        "mau",
        "want",
        "interested",
        "tertarik",
    ]

    FEEDBACK_KEYWORDS = [
        "saran",
        "suggestion",
        "feedback",
        "review",
        "ulasan",
        "pendapat",
        "opinion",
        "kritik",
        "criticism",
    ]

    def analyze(self, text: str) -> Dict[str, any]:
        """Analyze conversation text for sentiment and intent.

        Args:
            text: Conversation text to analyze

        Returns:
            Dictionary with:
                - sentiment: "positive", "neutral", or "negative"
                - intent: "question", "complaint", "purchase", "feedback", or "other"
                - engagement: "high", "medium", or "low"
                - confidence: float 0.0-1.0

        Examples:
            >>> analyzer = ConversationAnalyzer()
            >>> result = analyzer.analyze("Terima kasih, produknya bagus!")
            >>> result["sentiment"]
            'positive'
            >>> result = analyzer.analyze("Berapa harga produk ini?")
            >>> result["intent"]
            'question'
        """
        text_lower = text.lower()

        # Analyze sentiment
        sentiment = self._analyze_sentiment(text_lower)

        # Analyze intent
        intent = self._analyze_intent(text_lower)

        # Calculate engagement level
        engagement = self._calculate_engagement(text, sentiment, intent)

        # Calculate confidence (simple heuristic based on text length)
        confidence = min(1.0, len(text.split()) / 20.0)

        return {
            "sentiment": sentiment,
            "intent": intent,
            "engagement": engagement,
            "confidence": round(confidence, 2),
        }

    def _analyze_sentiment(self, text: str) -> str:
        """Determine sentiment from text.

        Args:
            text: Lowercase text

        Returns:
            "positive", "neutral", or "negative"
        """
        positive_count = sum(1 for kw in self.POSITIVE_KEYWORDS if kw in text)
        negative_count = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw in text)

        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        else:
            return "neutral"

    def _analyze_intent(self, text: str) -> str:
        """Determine intent from text.

        Args:
            text: Lowercase text

        Returns:
            "question", "complaint", "purchase", "feedback", or "other"
        """
        # Check each intent category
        is_question = any(kw in text for kw in self.QUESTION_KEYWORDS)
        is_complaint = any(kw in text for kw in self.COMPLAINT_KEYWORDS)
        is_purchase = any(kw in text for kw in self.PURCHASE_KEYWORDS)
        is_feedback = any(kw in text for kw in self.FEEDBACK_KEYWORDS)

        # Priority order: complaint > purchase > question > feedback > other
        if is_complaint:
            return "complaint"
        elif is_purchase:
            return "purchase"
        elif is_question:
            return "question"
        elif is_feedback:
            return "feedback"
        else:
            return "other"

    def _calculate_engagement(self, text: str, sentiment: str, intent: str) -> str:
        """Calculate engagement level.

        Args:
            text: Original text
            sentiment: Detected sentiment
            intent: Detected intent

        Returns:
            "high", "medium", or "low"
        """
        # Base score on text length
        word_count = len(text.split())

        # High engagement: long messages, purchase intent, or strong sentiment
        if (
            word_count > 30
            or intent == "purchase"
            or sentiment in ("positive", "negative")
        ):
            return "high"
        # Low engagement: very short messages
        elif word_count < 5:
            return "low"
        # Medium engagement: everything else
        else:
            return "medium"

    def batch_analyze(self, texts: List[str]) -> List[Dict[str, any]]:
        """Analyze multiple conversation texts.

        Args:
            texts: List of conversation texts

        Returns:
            List of analysis results
        """
        return [self.analyze(text) for text in texts]

    def get_aggregate_sentiment(self, texts: List[str]) -> Dict[str, any]:
        """Get aggregate sentiment across multiple messages.

        Args:
            texts: List of conversation texts

        Returns:
            Dictionary with sentiment distribution and overall sentiment
        """
        if not texts:
            return {
                "overall": "neutral",
                "positive_count": 0,
                "neutral_count": 0,
                "negative_count": 0,
                "total": 0,
            }

        results = self.batch_analyze(texts)

        positive_count = sum(1 for r in results if r["sentiment"] == "positive")
        neutral_count = sum(1 for r in results if r["sentiment"] == "neutral")
        negative_count = sum(1 for r in results if r["sentiment"] == "negative")

        # Overall sentiment is the majority
        if positive_count > negative_count and positive_count > neutral_count:
            overall = "positive"
        elif negative_count > positive_count and negative_count > neutral_count:
            overall = "negative"
        else:
            overall = "neutral"

        return {
            "overall": overall,
            "positive_count": positive_count,
            "neutral_count": neutral_count,
            "negative_count": negative_count,
            "total": len(texts),
        }
