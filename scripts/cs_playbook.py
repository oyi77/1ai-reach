"""
CS Playbook — Dynamic response playbook with scenario-based strategies.

Scenarios covered:
- Price objections ("harganya mahal")
- Closing requests (ready to buy)
- Bulk orders (grosir/reseller)
- Shipping concerns (ongkir mahal)
- Product inquiries
- Trust/doubt handling
- Follow-ups

Each scenario has multiple response patterns with success tracking.
New successful responses are auto-learned from winning conversations.
"""

import json
import random
import sys
from pathlib import Path
from typing import Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from cs_outcomes import get_best_patterns, record_pattern_use


class ResponsePattern:
    def __init__(self, pattern_id: str, text: str, scenario: str, tags: list = None):
        self.pattern_id = pattern_id
        self.text = text
        self.scenario = scenario
        self.tags = tags or []
        self.times_used = 0
        self.times_successful = 0

    def format(self, **kwargs) -> str:
        return self.text.format(**kwargs)


class CSPlaybook:
    """Dynamic playbook that learns from successful conversations."""

    SCENARIOS = {
        "price_objection": [
            "harganya mahal",
            "kenapa mahal",
            "bisa kurang",
            "diskon",
            "nego",
            "mahal banget",
            "kemahalan",
            "murahin",
        ],
        "closing_ready": [
            "mau beli",
            "mau order",
            "gimana cara beli",
            "transfer ke mana",
            "bisa bayar",
            "mau pesan",
            "ready",
            "stock ada",
            "bisa dikirim",
        ],
        "bulk_inquiry": [
            "grosir",
            "reseller",
            "banyak",
            "partai",
            "minimal order",
            "harga grosir",
            "agen",
            "distributor",
        ],
        "shipping_concern": [
            "ongkir",
            "pengiriman",
            "jauh",
            "luar kota",
            "berapa ongkir",
            "gratis ongkir",
            "kirim ke",
        ],
        "product_inquiry": [
            "produk apa",
            "varian",
            "jenis",
            "ada yang",
            "tersedia",
            "stock",
            "warna",
            "ukuran",
        ],
        "trust_doubt": [
            "aman",
            "bisa percaya",
            "takut tipu",
            "penipuan",
            "cod",
            "shopee",
            "tokopedia",
            "testimoni",
            "review",
        ],
        "follow_up": [
            "masih ada",
            "masih ready",
            "masih stock",
            "update",
            "terakhir",
            "belum dibalas",
        ],
        "general": [],
    }

    def __init__(self):
        self.patterns = self._load_default_patterns()
        self._load_learned_patterns()

    def _load_default_patterns(self) -> dict[str, list[ResponsePattern]]:
        patterns = {
            "price_objection": [
                ResponsePattern(
                    "price_reframe_value",
                    "Kak, produk kami emang investasi awalnya lebih besar sedikit, tapi coba hitung: kualitas premium, hasilnya memuaskan, dan tahan lama! Lebih hemat dalam jangka panjang. Mau saya bantu hitung untuk kebutuhan Kakak?",
                    "price_objection",
                    ["value", "reframe", "calculation"],
                ),
                ResponsePattern(
                    "price_bundle_offer",
                    "Kak, saya ngerti budget penting 😊 Yuk, saya bantu: kalau ambil paket hemat, harganya turun 15% + ada bonusnya! Mau saya rekapkan?",
                    "price_objection",
                    ["bundle", "discount", "value_add"],
                ),
                ResponsePattern(
                    "price_quality_compare",
                    "Kak, banyak yang bilang mahal di awal, tapi setelah pakai bilang worth it karena kualitasnya premium dan hasilnya konsisten. Ada juga versi ekonomis kalau Kakak mau coba dulu. Minat yang mana?",
                    "price_objection",
                    ["compare", "alternative", "social_proof"],
                ),
                ResponsePattern(
                    "price_trial_offer",
                    "Kak, saya kasih solusi: ada paket trial dengan harga terjangkau. Kalau cocok baru upgrade. Gimana?",
                    "price_objection",
                    ["trial", "low_risk", "direct_cta"],
                ),
            ],
            "closing_ready": [
                ResponsePattern(
                    "close_confirm_details",
                    "Mantap Kak! Saya catat dulu:\n\n📦 {product_name}\n💰 Rp{order_value}\n📍 Alamat: [blm diisi]\n📱 No HP: [blm diisi]\n\nBisa diisi datanya? Biar langsung kirim hari ini!",
                    "closing_ready",
                    ["confirmation", "details", "form"],
                ),
                ResponsePattern(
                    "close_assumptive",
                    "Oke Kak, saya siapkan pesanan ya! Mau dikirim hari ini atau besok? Alamatnya mana nih? Langsung saya rekap biar cepet sampai! 😊",
                    "closing_ready",
                    ["assumptive", "choice_close", "urgency"],
                ),
            ],
            "bulk_inquiry": [
                ResponsePattern(
                    "bulk_cargo_offer",
                    "Halo Kak! Buat order besar, kita kasih harga khusus grosir + kirim via cargo (ongkir jauh lebih murah dari reguler). Minat detailnya?",
                    "bulk_inquiry",
                    ["cargo", "volume_discount", "savings"],
                ),
                ResponsePattern(
                    "bulk_reseller_info",
                    "Kak mau jadi reseller? Dapat harga reseller spesial + bonus marketing kit. Cocok buat bisnis atau dijual lagi. Mau saya jelaskan sistemnya?",
                    "bulk_inquiry",
                    ["reseller", "opportunity", "partnership"],
                ),
            ],
            "shipping_concern": [
                ResponsePattern(
                    "shipping_reframe",
                    "Ongkir ke {location} cuma Rp{ongkir} Kak, masih terjangkau kok untuk kualitas premium. Atau kalau mau GRATIS ongkir, bisa order via Shopee: {shopee_link} 👍",
                    "shipping_concern",
                    ["reframe", "alternative", "marketplace"],
                ),
                ResponsePattern(
                    "shipping_free_threshold",
                    "Kak, kalau order Rp{free_threshold} ke atas, ongkir kita gratis kan! Total order Kakak Rp{current_order}, tambah {add_amount} lagi untuk gratis ongkir. Mau saya hitungkan?",
                    "shipping_concern",
                    ["upsell", "threshold", "incentive"],
                ),
            ],
            "product_inquiry": [
                ResponsePattern(
                    "product_variants",
                    "Kak, kita ada beberapa pilihan:\n1️⃣ {variant_1} - {desc_1}\n2️⃣ {variant_2} - {desc_2}\n3️⃣ {variant_3} - {desc_3}\n\nYang mana sesuai kebutuhan Kakak?",
                    "product_inquiry",
                    ["options", "comparison", "consultative"],
                ),
            ],
            "trust_doubt": [
                ResponsePattern(
                    "trust_social_proof",
                    "Ngerti banget Kak, wajar was-wada 😊 Kita sudah 500+ customer dengan rating bagus. Testimoni real ada di {testimonial_link}. Atau bisa COD lewat Shopee: {shopee_link} biar aman.",
                    "trust_doubt",
                    ["social_proof", "rating", "cod_option"],
                ),
                ResponsePattern(
                    "trust_transparent",
                    "Fair concern Kak! Kita legal PT Berkah Karya Teknologi, ada website berkahkarya.com dan Shopee official. Bisa cek review dulu atau bayar via Shopee (lebih aman). Gimana Kak?",
                    "trust_doubt",
                    ["transparency", "credentials", "options"],
                ),
            ],
            "follow_up": [
                ResponsePattern(
                    "follow_up_gentle",
                    "Halo Kak! Masih tertarik dengan {product_name}? Stock masih ada nih. Mau saya bantu?",
                    "follow_up",
                    ["scarcity", "gentle", "opportunity"],
                ),
            ],
            "general": [
                ResponsePattern(
                    "general_helpful",
                    "Tentu Kak! Saya bantu. {response}",
                    "general",
                    ["flexible", "placeholder"],
                ),
            ],
        }
        return patterns

    def _load_learned_patterns(self):
        """Load patterns learned from successful conversations."""
        for scenario in self.SCENARIOS.keys():
            learned = get_best_patterns(scenario, limit=3)
            for p in learned:
                if p["pattern_id"] not in [
                    rp.pattern_id for rp in self.patterns.get(scenario, [])
                ]:
                    self.patterns.setdefault(scenario, []).append(
                        ResponsePattern(
                            pattern_id=p["pattern_id"],
                            text=p["pattern_text"],
                            scenario=scenario,
                            tags=["learned"],
                        )
                    )

    def detect_scenario(self, message: str) -> str:
        """Detect which scenario the message fits."""
        msg_lower = message.lower()

        for scenario, keywords in self.SCENARIOS.items():
            if any(kw in msg_lower for kw in keywords):
                return scenario

        return "general"

    def get_response(
        self,
        scenario: str,
        user_type: str = "normal",
        context: dict = None,
        explore: bool = False,
    ) -> dict:
        """Get best response for scenario with optional exploration."""
        context = context or {}
        patterns = self.patterns.get(scenario, self.patterns["general"])

        if not patterns:
            return {
                "response": "Halo Kak, ada yang bisa dibantu?",
                "pattern_id": "fallback",
            }

        # 10% exploration: try a random pattern
        if explore and random.random() < 0.1 and len(patterns) > 1:
            pattern = random.choice(patterns[1:])  # Skip first (best) for exploration
        else:
            # Use highest success rate or first (default best)
            patterns_with_scores = []
            for i, p in enumerate(patterns):
                score = p.times_successful / max(p.times_used, 1)
                patterns_with_scores.append((score, i, p))
            patterns_with_scores.sort(reverse=True)
            pattern = (
                patterns_with_scores[0][2] if patterns_with_scores else patterns[0]
            )

        # Format response with context
        try:
            response_text = pattern.format(**context)
        except KeyError:
            response_text = pattern.text

        # Record usage for learning
        record_pattern_use(
            pattern.pattern_id,
            pattern.text,
            scenario,
            was_successful=False,  # Will be updated when outcome known
        )

        return {
            "response": response_text,
            "pattern_id": pattern.pattern_id,
            "scenario": scenario,
            "user_type": user_type,
        }

    def add_learned_pattern(
        self, scenario: str, text: str, source_conversation: int = None
    ):
        """Add a new pattern learned from a successful conversation."""
        pattern_id = f"learned_{scenario}_{source_conversation or 'manual'}_{len(self.patterns.get(scenario, []))}"
        pattern = ResponsePattern(pattern_id, text, scenario, tags=["learned", "auto"])
        self.patterns.setdefault(scenario, []).append(pattern)
        return pattern_id


class AdaptiveContext:
    """Manages conversation context for personalization."""

    def __init__(self, wa_number_id: str, contact_phone: str):
        self.wa_number_id = wa_number_id
        self.contact_phone = contact_phone
        self.scenarios_hit = []
        self.objections_raised = []
        self.interests_shown = []
        self.last_pattern_used = None
        self.conversation_turns = 0

    def update(self, scenario: str, pattern_id: str, user_message: str):
        """Update context based on interaction."""
        self.scenarios_hit.append(scenario)
        self.last_pattern_used = pattern_id
        self.conversation_turns += 1

        if scenario == "price_objection":
            self.objections_raised.append("price")
        elif scenario == "trust_doubt":
            self.objections_raised.append("trust")

        if "mau" in user_message.lower() or "minat" in user_message.lower():
            self.interests_shown.append(scenario)

    def get_user_profile(self) -> str:
        """Infer user type from conversation history."""
        if "price" in self.objections_raised and len(self.objections_raised) > 1:
            return "price_sensitive"
        elif self.scenarios_hit.count("bulk_inquiry") > 0:
            return "bulk"
        elif "trust" in self.objections_raised:
            return "friction"
        elif self.conversation_turns > 5 and len(self.interests_shown) > 0:
            return "hot_lead"
        return "normal"

    def should_escalate_to_human(self) -> tuple[bool, str]:
        """Determine if conversation should escalate to human."""
        if self.objections_raised.count("price") >= 3:
            return True, "Multiple price objections - may need custom pricing"
        if self.objections_raised.count("trust") >= 2:
            return True, "Trust issues - human reassurance needed"
        if self.conversation_turns > 15:
            return True, "Conversation too long - human take over"
        return False, ""


# Global playbook instance
_playbook = None


def get_playbook() -> CSPlaybook:
    """Get or create global playbook instance."""
    global _playbook
    if _playbook is None:
        _playbook = CSPlaybook()
    return _playbook


def get_response_for_message(
    message: str,
    user_type: str = "normal",
    context: dict = None,
    explore: bool = False,
) -> dict:
    """Convenience function to get response for a message."""
    playbook = get_playbook()
    scenario = playbook.detect_scenario(message)
    return playbook.get_response(scenario, user_type, context, explore)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="CS Playbook")
    p.add_argument("--test-scenario", help="Test scenario detection")
    p.add_argument("--test-response", help="Test response generation")
    p.add_argument("--list-scenarios", action="store_true", help="List all scenarios")

    args = p.parse_args()

    playbook = CSPlaybook()

    if args.test_scenario:
        scenario = playbook.detect_scenario(args.test_scenario)
        print(f"Message: {args.test_scenario}")
        print(f"Detected scenario: {scenario}")

    elif args.test_response:
        result = get_response_for_message(args.test_response)
        print(f"Input: {args.test_response}")
        print(f"Scenario: {result['scenario']}")
        print(f"Pattern: {result['pattern_id']}")
        print(f"Response: {result['response']}")

    elif args.list_scenarios:
        print("Available scenarios:")
        for scenario, keywords in playbook.SCENARIOS.items():
            print(f"\n{scenario}:")
            print(f"  Keywords: {', '.join(keywords[:5])}...")
            patterns = playbook.patterns.get(scenario, [])
            print(f"  Patterns: {len(patterns)}")

    else:
        p.print_help()
