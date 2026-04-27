"""Unit tests for cs_playbook response patterns."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oneai_reach.application.customer_service.playbook_service import PlaybookService as CSPlaybook


class TestCSPlaybook:
    def test_detect_price_objection(self):
        pb = CSPlaybook()
        scenario = pb.detect_scenario("harganya mahal banget")
        assert scenario == "price_objection"

    def test_detect_closing(self):
        pb = CSPlaybook()
        scenario = pb.detect_scenario("mau beli dong")
        assert scenario == "closing_ready"

    def test_detect_bulk(self):
        pb = CSPlaybook()
        scenario = pb.detect_scenario("harga grosir berapa")
        assert scenario == "bulk_inquiry"

    def test_detect_shipping(self):
        pb = CSPlaybook()
        scenario = pb.detect_scenario("ongkir ke jakarta berapa")
        assert scenario == "shipping_concern"

    def test_detect_product_inquiry(self):
        pb = CSPlaybook()
        scenario = pb.detect_scenario("ada varian apa aja")
        assert scenario == "product_inquiry"

    def test_detect_trust_doubt(self):
        pb = CSPlaybook()
        scenario = pb.detect_scenario("takut tipu nih")
        assert scenario == "trust_doubt"

    def test_detect_general_fallback(self):
        pb = CSPlaybook()
        scenario = pb.detect_scenario("halo")
        assert scenario == "general"

    def test_get_response_returns_dict_with_response_key(self):
        pb = CSPlaybook()
        result = pb.get_response("price_objection")
        assert isinstance(result, dict)
        assert "response" in result
        assert "pattern_id" in result
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 20

    def test_get_response_general_scenario(self):
        pb = CSPlaybook()
        result = pb.get_response("general", context={"response": "test reply"})
        assert "response" in result
        assert "test reply" in result["response"]

    def test_add_learned_pattern(self):
        pb = CSPlaybook()
        pattern_id = pb.add_learned_pattern(
            "price_objection", "Kak, kita bisa nego!", source_conversation=42
        )
        assert "learned" in pattern_id
        assert "price_objection" in pattern_id

        patterns = pb.patterns.get("price_objection", [])
        assert any(p.pattern_id == pattern_id for p in patterns)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
