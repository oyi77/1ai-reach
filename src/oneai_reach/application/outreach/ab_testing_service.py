"""A/B testing framework for email templates, subject lines, and send times.

Provides:
- Test creation and management
- Traffic allocation (A/B/n splits)
- Statistical significance calculation
- Auto-optimization (allocate more to winners)
- Performance tracking across variants
"""

import json
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict, field
from enum import Enum
import logging

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class TestStatus(Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused"


class TestType(Enum):
    SUBJECT_LINE = "subject_line"
    EMAIL_BODY = "email_body"
    SEND_TIME = "send_time"
    CTA = "call_to_action"
    SENDER_NAME = "sender_name"
    CHANNEL = "channel"


@dataclass
class Variant:
    """A/B test variant."""
    id: str
    name: str
    content: str  # Subject, body, or other content
    traffic_allocation: float  # 0.0-1.0
    sent_count: int = 0
    open_count: int = 0
    click_count: int = 0
    reply_count: int = 0
    conversion_count: int = 0


@dataclass
class ABTest:
    """A/B test definition."""
    id: str
    name: str
    test_type: TestType
    status: TestStatus
    variants: List[Variant]
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    min_sample_size: int = 100  # Per variant for significance
    confidence_level: float = 0.95
    winner_id: Optional[str] = None
    results: Dict = field(default_factory=dict)


class ABTestingService:
    """A/B testing service for outreach optimization."""

    def __init__(self, config: Settings):
        self.config = config
        self.tests_dir = Path(config.database.data_dir) / "ab_tests"
        self.tests_dir.mkdir(parents=True, exist_ok=True)

    def create_test(self, name: str, test_type: TestType, variants: List[Dict]) -> ABTest:
        """Create a new A/B test."""
        # Create variants with equal traffic allocation
        variant_objects = []
        allocation = 1.0 / len(variants)
        
        for i, var_data in enumerate(variants):
            variant_objects.append(Variant(
                id=f"{name.lower().replace(' ', '_')}_{i}",
                name=var_data.get("name", f"Variant {i+1}"),
                content=var_data["content"],
                traffic_allocation=allocation
            ))

        test = ABTest(
            id=f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name=name,
            test_type=test_type,
            status=TestStatus.DRAFT,
            variants=variant_objects,
            created_at=datetime.now(timezone.utc).isoformat()
        )

        self._save_test(test)
        logger.info(f"Created A/B test: {test.name}")
        return test

    def start_test(self, test_id: str):
        """Start an A/B test."""
        test = self._load_test(test_id)
        if not test:
            raise ValueError(f"Test {test_id} not found")

        test.status = TestStatus.RUNNING
        test.started_at = datetime.now(timezone.utc).isoformat()
        self._save_test(test)
        logger.info(f"Started A/B test: {test.name}")

    def get_variant(self, test_id: str) -> Optional[Variant]:
        """Get variant for a send based on traffic allocation."""
        test = self._load_test(test_id)
        if not test or test.status != TestStatus.RUNNING:
            return None

        # Weighted random selection based on traffic allocation
        import random
        rand = random.random()
        cumulative = 0.0

        for variant in test.variants:
            cumulative += variant.traffic_allocation
            if rand <= cumulative:
                return variant

        return test.variants[-1]  # Fallback to last variant

    def record_event(self, test_id: str, variant_id: str, event_type: str):
        """Record engagement event for a variant."""
        test = self._load_test(test_id)
        if not test:
            return

        variant = next((v for v in test.variants if v.id == variant_id), None)
        if not variant:
            return

        # Update counts
        if event_type == "sent":
            variant.sent_count += 1
        elif event_type == "opened":
            variant.open_count += 1
        elif event_type == "clicked":
            variant.click_count += 1
        elif event_type == "replied":
            variant.reply_count += 1
        elif event_type == "converted":
            variant.conversion_count += 1

        # Check if test should complete
        self._check_test_completion(test)

        self._save_test(test)

    def _check_test_completion(self, test: ABTest):
        """Check if test has reached statistical significance."""
        # Check if minimum sample size reached
        min_sent = min(v.sent_count for v in test.variants)
        if min_sent < test.min_sample_size:
            return

        # Calculate statistical significance
        results = self._calculate_significance(test)
        test.results = results

        # If winner found with high confidence, complete test
        if results.get("significant") and results.get("winner"):
            test.status = TestStatus.COMPLETED
            test.completed_at = datetime.now(timezone.utc).isoformat()
            test.winner_id = results["winner"]["id"]
            logger.info(f"A/B test completed: {test.name} - Winner: {results['winner']['id']}")

    def _calculate_significance(self, test: ABTest) -> Dict:
        """Calculate statistical significance of results."""
        if len(test.variants) < 2:
            return {"significant": False}

        # Compare open rates (primary metric)
        variants = test.variants
        v1, v2 = variants[0], variants[1]

        if v1.sent_count == 0 or v2.sent_count == 0:
            return {"significant": False}

        # Calculate conversion rates
        p1 = v1.open_count / v1.sent_count
        p2 = v2.open_count / v2.sent_count

        # Pooled proportion
        p_pool = (v1.open_count + v2.open_count) / (v1.sent_count + v2.sent_count)

        # Standard error
        se = math.sqrt(p_pool * (1 - p_pool) * (1/v1.sent_count + 1/v2.sent_count))
        if se == 0:
            return {"significant": False}

        # Z-score
        z = (p1 - p2) / se

        # P-value (two-tailed)
        p_value = 2 * (1 - self._norm_cdf(abs(z)))

        # Determine winner
        significant = p_value < (1 - test.confidence_level)
        winner = None

        if significant:
            winner = v1 if p1 > p2 else v2
            winner_data = {
                "id": winner.id,
                "name": winner.name,
                "open_rate": winner.open_count / winner.sent_count if winner.sent_count > 0 else 0,
                "improvement": abs(p1 - p2) * 100,
                "confidence": (1 - p_value) * 100
            }
        else:
            winner_data = None

        return {
            "significant": significant,
            "p_value": p_value,
            "z_score": z,
            "variant_1": {
                "id": v1.id,
                "open_rate": p1,
                "sent": v1.sent_count
            },
            "variant_2": {
                "id": v2.id,
                "open_rate": p2,
                "sent": v2.sent_count
            },
            "winner": winner_data
        }

    def _norm_cdf(self, x: float) -> float:
        """Normal distribution CDF approximation."""
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def auto_optimize(self, test_id: str):
        """Automatically adjust traffic allocation to favor winners."""
        test = self._load_test(test_id)
        if not test or test.status != TestStatus.RUNNING:
            return

        # Calculate performance for each variant
        performance = []
        for variant in test.variants:
            if variant.sent_count > 0:
                open_rate = variant.open_count / variant.sent_count
                performance.append((variant, open_rate))
            else:
                performance.append((variant, 0.0))

        # If clear winner emerging, shift traffic
        if len(performance) >= 2:
            performance.sort(key=lambda x: x[1], reverse=True)
            best_rate = performance[0][1]
            
            # If best is 20%+ better than average, allocate more traffic
            avg_rate = sum(p[1] for p in performance) / len(performance)
            if best_rate > avg_rate * 1.2:
                # Shift 10% traffic to winner
                winner = performance[0][0]
                for variant in test.variants:
                    if variant.id == winner.id:
                        variant.traffic_allocation = min(0.8, variant.traffic_allocation + 0.1)
                    else:
                        variant.traffic_allocation = max(0.1, variant.traffic_allocation - (0.1 / (len(test.variants) - 1)))

                self._save_test(test)
                logger.info(f"Auto-optimized traffic for test {test.name}")

    def get_test_results(self, test_id: str) -> Optional[Dict]:
        """Get test results and statistics."""
        test = self._load_test(test_id)
        if not test:
            return None

        results = {
            "id": test.id,
            "name": test.name,
            "status": test.status.value,
            "type": test.test_type.value,
            "variants": []
        }

        for variant in test.variants:
            results["variants"].append({
                "id": variant.id,
                "name": variant.name,
                "sent": variant.sent_count,
                "opens": variant.open_count,
                "clicks": variant.click_count,
                "replies": variant.reply_count,
                "open_rate": variant.open_count / variant.sent_count if variant.sent_count > 0 else 0,
                "click_rate": variant.click_count / variant.sent_count if variant.sent_count > 0 else 0,
                "reply_rate": variant.reply_count / variant.sent_count if variant.sent_count > 0 else 0,
                "traffic_allocation": variant.traffic_allocation
            })

        if test.results:
            results["statistics"] = test.results

        return results

    def _save_test(self, test: ABTest):
        """Save test to file."""
        path = self.tests_dir / f"{test.id}.json"
        with open(path, 'w') as f:
            json.dump(asdict(test), f, indent=2, default=str)

    def _load_test(self, test_id: str) -> Optional[ABTest]:
        """Load test from file."""
        path = self.tests_dir / f"{test_id}.json"
        if not path.exists():
            return None

        with open(path, 'r') as f:
            data = json.load(f)
            return ABTest(**data)

    def list_tests(self, status: Optional[TestStatus] = None) -> List[ABTest]:
        """List all tests, optionally filtered by status."""
        tests = []
        for path in self.tests_dir.glob("*.json"):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    test = ABTest(**data)
                    if status is None or test.status == status:
                        tests.append(test)
            except Exception as e:
                logger.error(f"Error loading test {path}: {e}")
        return tests


def get_ab_testing_service(config: Settings) -> ABTestingService:
    """Get or create A/B testing service."""
    return ABTestingService(config)
