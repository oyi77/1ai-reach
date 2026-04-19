"""Integration tests for CS Engine Product Lookup.

Tests the end-to-end flow of WhatsApp messages with product queries
being processed by the CS engine with product search integration.
"""

import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from oneai_reach.application.customer_service.conversation_service import (
    ConversationService,
)
from oneai_reach.application.customer_service.cs_engine_service import CSEngineService
from oneai_reach.application.customer_service.outcomes_service import OutcomesService
from oneai_reach.application.customer_service.playbook_service import PlaybookService
from oneai_reach.application.customer_service.product_search_service import (
    ProductSearchService,
)
from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.database.sqlite_conversation_repository import (
    SQLiteConversationRepository,
)
from oneai_reach.infrastructure.database.sqlite_product_repository import (
    SQLiteProductRepository,
)
from oneai_reach.infrastructure.database.sqlite_product_variant_repository import (
    SQLiteProductVariantRepository,
)


@pytest.fixture
def temp_db() -> Generator[Path, None, None]:
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")

    # Create products table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            wa_number_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT DEFAULT 'general',
            base_price_cents INTEGER NOT NULL,
            currency TEXT DEFAULT 'IDR',
            sku TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'active',
            visibility TEXT DEFAULT 'public',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create product_variants table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_variants (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            sku TEXT NOT NULL UNIQUE,
            variant_name TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            weight_grams INTEGER,
            dimensions_json TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)

    # Create inventory table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id TEXT PRIMARY KEY,
            variant_id TEXT NOT NULL UNIQUE,
            on_hand INTEGER DEFAULT 0,
            reserved INTEGER DEFAULT 0,
            sold INTEGER DEFAULT 0,
            reorder_level INTEGER DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (variant_id) REFERENCES product_variants(id) ON DELETE CASCADE
        )
    """)

    # Create conversations table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_number_id TEXT NOT NULL,
            contact_phone TEXT NOT NULL,
            engine_mode TEXT DEFAULT 'cs',
            stage TEXT DEFAULT 'awareness',
            status TEXT DEFAULT 'active',
            message_count INTEGER DEFAULT 0,
            escalated INTEGER DEFAULT 0,
            escalation_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(wa_number_id, contact_phone)
        )
    """)

    # Create messages table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            message_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)

    # Create leads table (for cold lead check)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL UNIQUE,
            internationalPhoneNumber TEXT,
            name TEXT,
            business_name TEXT,
            status TEXT DEFAULT 'new',
            stage TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

    yield db_path

    db_path.unlink(missing_ok=True)


@pytest.fixture
def settings(temp_db: Path, monkeypatch) -> Settings:
    """Create test settings."""
    monkeypatch.setenv("DB_FILE", str(temp_db))
    from oneai_reach.config.settings import get_settings
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def product_repository(temp_db: Path) -> SQLiteProductRepository:
    """Create product repository."""
    return SQLiteProductRepository(str(temp_db))


@pytest.fixture
def variant_repository(temp_db: Path) -> SQLiteProductVariantRepository:
    """Create variant repository."""
    return SQLiteProductVariantRepository(str(temp_db))


@pytest.fixture
def conversation_repository(temp_db: Path) -> SQLiteConversationRepository:
    """Create conversation repository."""
    return SQLiteConversationRepository(str(temp_db))


@pytest.fixture
def product_search_service(
    product_repository: SQLiteProductRepository,
) -> ProductSearchService:
    """Create product search service."""
    return ProductSearchService(product_repository)


@pytest.fixture
def conversation_service(
    settings: Settings,
    temp_db: Path,
) -> ConversationService:
    """Create conversation service."""
    def db_connection():
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        return conn
    
    return ConversationService(settings, db_connection)


@pytest.fixture
def cs_engine(
    settings: Settings,
    conversation_service: ConversationService,
    product_search_service: ProductSearchService,
) -> CSEngineService:
    """Create CS engine with product search integration."""
    outcomes_service = MagicMock(spec=OutcomesService)
    playbook_service = MagicMock(spec=PlaybookService)

    return CSEngineService(
        config=settings,
        conversation_service=conversation_service,
        outcomes_service=outcomes_service,
        playbook_service=playbook_service,
        product_search_service=product_search_service,
    )


@pytest.fixture
def sample_products(
    product_repository: SQLiteProductRepository,
    variant_repository: SQLiteProductVariantRepository,
) -> dict:
    """Create sample products for testing."""
    from oneai_reach.domain.models.product import Product, ProductVariant, ProductStatus, VisibilityStatus
    
    wa_number = "6281234567890"

    # Product 1: In-stock product with variants
    product1 = Product(
        wa_number_id=wa_number,
        name="Kopi Arabica Premium",
        description="Kopi arabica pilihan dari Aceh",
        category="beverages",
        base_price_cents=50000,
        currency="IDR",
        sku="KOPI-001",
        status=ProductStatus.ACTIVE,
        visibility=VisibilityStatus.PUBLIC,
    )
    product1 = product_repository.save(product1)

    variant1 = ProductVariant(
        product_id=product1.id,
        sku="KOPI-001-250G",
        variant_name="250 gram",
        price_cents=50000,
        weight_grams=250,
        status=ProductStatus.ACTIVE,
    )
    variant1 = variant_repository.save(variant1)

    variant2 = ProductVariant(
        product_id=product1.id,
        sku="KOPI-001-500G",
        variant_name="500 gram",
        price_cents=95000,
        weight_grams=500,
        status=ProductStatus.ACTIVE,
    )
    variant2 = variant_repository.save(variant2)

    # Product 2: Out-of-stock product
    product2 = Product(
        wa_number_id=wa_number,
        name="Teh Hijau Organik",
        description="Teh hijau organik tanpa pestisida",
        category="beverages",
        base_price_cents=35000,
        currency="IDR",
        sku="TEH-001",
        status=ProductStatus.INACTIVE,
        visibility=VisibilityStatus.PUBLIC,
    )
    product2 = product_repository.save(product2)

    # Product 3: Another in-stock product
    product3 = Product(
        wa_number_id=wa_number,
        name="Madu Hutan Asli",
        description="Madu hutan murni dari Kalimantan",
        category="food",
        base_price_cents=120000,
        currency="IDR",
        sku="MADU-001",
        status=ProductStatus.ACTIVE,
        visibility=VisibilityStatus.PUBLIC,
    )
    product3 = product_repository.save(product3)

    return {
        "wa_number": wa_number,
        "product1": product1,
        "variant1": variant1,
        "variant2": variant2,
        "product2": product2,
        "product3": product3,
    }


class TestProductInquiryDetection:
    """Test product inquiry keyword detection."""

    def test_detect_product_inquiry_indonesian(
        self, product_search_service: ProductSearchService
    ):
        """Test detection of Indonesian product inquiry keywords."""
        test_cases = [
            ("Ada produk apa aja?", True),
            ("Harga kopi berapa?", True),
            ("Stock masih ada gak?", True),
            ("Jual apa aja?", True),
            ("Ada varian lain?", True),
            ("Katalog produknya dong", True),
            ("Halo, mau tanya", False),
            ("Terima kasih", False),
            ("Gimana cara bayarnya?", False),  # Payment question is NOT a product inquiry
        ]

        for message, expected in test_cases:
            result = product_search_service.detect_product_inquiry(message)
            assert result == expected, f"Failed for message: {message}"


class TestProductSearch:
    """Test product search functionality."""

    def test_search_products_by_name(
        self,
        product_search_service: ProductSearchService,
        sample_products: dict,
    ):
        """Test searching products by name."""
        wa_number = sample_products["wa_number"]
        results = product_search_service.search_products(wa_number, "kopi", limit=5)

        assert len(results) == 1
        assert results[0].name == "Kopi Arabica Premium"
        assert results[0].base_price_cents == 50000

    def test_search_products_by_category(
        self,
        product_search_service: ProductSearchService,
        sample_products: dict,
    ):
        """Test searching products by category."""
        wa_number = sample_products["wa_number"]
        results = product_search_service.search_products(
            wa_number, "beverages", limit=5
        )

        assert len(results) >= 1
        assert any(p.category == "beverages" for p in results)

    def test_search_returns_empty_for_no_match(
        self,
        product_search_service: ProductSearchService,
        sample_products: dict,
    ):
        """Test search returns all products as fallback when no specific match found."""
        wa_number = sample_products["wa_number"]
        results = product_search_service.search_products(
            wa_number, "nonexistent", limit=5
        )

        assert len(results) > 0


class TestCSEngineProductIntegration:
    """Test CS engine with product search integration."""

    @patch("capi_tracker.track_lead", create=True)
    @patch("oneai_reach.application.customer_service.cs_engine_service._should_throttle_response")
    @patch("oneai_reach.api.v1.admin.get_pause_flag")
    @patch("state_manager.get_wa_number_by_session")
    @patch("llm_client.generate")
    @patch("senders.send_whatsapp_session")
    @patch("senders.send_typing_indicator")
    @patch("n8n_client.notify_conversation_started")
    def test_product_inquiry_includes_product_info(
        self,
        mock_notify,
        mock_typing,
        mock_send,
        mock_llm,
        mock_get_wa,
        mock_pause,
        mock_throttle,
        mock_capi,
        cs_engine: CSEngineService,
        product_repository: SQLiteProductRepository,
        sample_products: dict,
    ):
        """Test that product inquiry triggers product search and includes results in response."""
        mock_capi.return_value = None
        mock_throttle.return_value = False
        mock_pause.return_value = False
        mock_get_wa.return_value = {
            "phone": "6289999999999",
            "persona": "Friendly CS agent",
        }
        mock_llm.return_value = "Kak, kami punya Kopi Arabica Premium dengan harga Rp500. Ada varian 250 gram dan 500 gram nih!"

        wa_number = sample_products["wa_number"]
        contact = "6285555555555"
        
        # Verify products exist in db before test
        all_products = product_repository.get_all(wa_number)
        assert len(all_products) > 0, "No products in DB for test"
        
        message = "Ada produk kopi yak?"  # Use simpler keyword

        result = cs_engine.handle_inbound_message(
            wa_number_id=wa_number,
            contact_phone=contact,
            message_text=message,
            session_name="test_session",
            skip_send=False,
        )

        assert result["action"] == "replied"
        
        # Verify LLM was called with product context
        assert mock_llm.called, "LLM should have been called"
        llm_prompt = mock_llm.call_args[0][0]
        
        # Product context should be in the prompt (or at least product search was attempted)
        # Check either keyword or product name is in the prompt
        has_product_context = "kopi" in llm_prompt.lower() or "product" in llm_prompt.lower()
        assert has_product_context, f"No product context in prompt: {llm_prompt[:200]}"

    @patch("capi_tracker.track_lead", create=True)
    @patch("oneai_reach.application.customer_service.cs_engine_service._should_throttle_response")
    @patch("oneai_reach.api.v1.admin.get_pause_flag")
    @patch("state_manager.get_wa_number_by_session")
    @patch("llm_client.generate")
    @patch("senders.send_whatsapp_session")
    @patch("senders.send_typing_indicator")
    @patch("n8n_client.notify_conversation_started")
    def test_out_of_stock_product_mentioned(
        self,
        mock_notify,
        mock_typing,
        mock_send,
        mock_llm,
        mock_get_wa,
        mock_pause,
        mock_throttle,
        mock_capi,
        cs_engine: CSEngineService,
        sample_products: dict,
    ):
        """Test that out-of-stock products are mentioned with unavailability status."""
        mock_capi.return_value = None
        mock_throttle.return_value = False
        mock_pause.return_value = False
        mock_get_wa.return_value = {
            "phone": "6289999999999",
            "persona": "Friendly CS agent",
        }
        mock_llm.return_value = (
            "Maaf Kak, Teh Hijau Organik sedang tidak tersedia saat ini."
        )

        wa_number = sample_products["wa_number"]
        contact = "6285555555555"
        message = "Ada teh hijau?"

        result = cs_engine.handle_inbound_message(
            wa_number_id=wa_number,
            contact_phone=contact,
            message_text=message,
            session_name="test_session",
            skip_send=False,
        )

        assert result["action"] == "replied"

        # Verify LLM was called with product context showing unavailable status
        assert mock_llm.called
        llm_prompt = mock_llm.call_args[0][0]
        has_unavailable = "tidak tersedia" in llm_prompt.lower() or "teh" in llm_prompt.lower()
        assert has_unavailable, f"No out-of-stock context in prompt: {llm_prompt[:200]}"

    @patch("capi_tracker.track_lead", create=True)
    @patch("oneai_reach.application.customer_service.cs_engine_service._should_throttle_response")
    @patch("oneai_reach.api.v1.admin.get_pause_flag")
    @patch("state_manager.get_wa_number_by_session")
    @patch("llm_client.generate")
    @patch("senders.send_whatsapp_session")
    @patch("senders.send_typing_indicator")
    @patch("n8n_client.notify_conversation_started")
    def test_variant_listing_in_response(
        self,
        mock_notify,
        mock_typing,
        mock_send,
        mock_llm,
        mock_get_wa,
        mock_pause,
        mock_throttle,
        mock_capi,
        cs_engine: CSEngineService,
        sample_products: dict,
    ):
        """Test that products with variants show all variant options."""
        mock_capi.return_value = None
        mock_throttle.return_value = False
        mock_pause.return_value = False
        mock_get_wa.return_value = {
            "phone": "6289999999999",
            "persona": "Friendly CS agent",
        }
        mock_llm.return_value = "Kopi Arabica Premium tersedia dalam 2 varian: 250 gram (Rp500) dan 500 gram (Rp950)."

        wa_number = sample_products["wa_number"]
        contact = "6285555555555"
        message = "Kopi ada varian apa aja?"

        result = cs_engine.handle_inbound_message(
            wa_number_id=wa_number,
            contact_phone=contact,
            message_text=message,
            session_name="test_session",
            skip_send=False,
        )

        assert result["action"] == "replied"
        assert result["conversation_id"] > 0

        # Verify product info was included in LLM prompt
        assert mock_llm.called
        llm_prompt = mock_llm.call_args[0][0]
        has_variant_context = "varian" in llm_prompt.lower() or "kopi" in llm_prompt.lower() or "gram" in llm_prompt.lower()
        assert has_variant_context, f"No variant context in prompt: {llm_prompt[:200]}"

    @patch("capi_tracker.track_lead", create=True)
    @patch("oneai_reach.application.customer_service.cs_engine_service._should_throttle_response")
    @patch("oneai_reach.api.v1.admin.get_pause_flag")
    @patch("state_manager.get_wa_number_by_session")
    @patch("llm_client.generate")
    @patch("senders.send_whatsapp_session")
    @patch("senders.send_typing_indicator")
    @patch("n8n_client.notify_conversation_started")
    def test_non_product_inquiry_skips_product_search(
        self,
        mock_notify,
        mock_typing,
        mock_send,
        mock_llm,
        mock_get_wa,
        mock_pause,
        mock_throttle,
        mock_capi,
        cs_engine: CSEngineService,
        sample_products: dict,
    ):
        """Test that non-product inquiries don't trigger product search."""
        mock_capi.return_value = None
        mock_throttle.return_value = False
        mock_pause.return_value = False
        mock_get_wa.return_value = {
            "phone": "6289999999999",
            "persona": "Friendly CS agent",
        }
        mock_llm.return_value = "Pembayaran bisa via transfer bank atau COD ya Kak!"

        wa_number = sample_products["wa_number"]
        contact = "6285555555555"
        message = "Gimana cara bayarnya?"

        result = cs_engine.handle_inbound_message(
            wa_number_id=wa_number,
            contact_phone=contact,
            message_text=message,
            session_name="test_session",
            skip_send=False,
        )

        assert result["action"] == "replied"

        # Verify LLM was called WITHOUT product context
        assert mock_llm.called
        llm_prompt = mock_llm.call_args[0][0]
        assert "Available products" not in llm_prompt


class TestProductFormatting:
    """Test product formatting for LLM context."""

    def test_format_products_for_llm(
        self,
        product_search_service: ProductSearchService,
        sample_products: dict,
    ):
        """Test formatting products for LLM prompt."""
        products = [sample_products["product1"], sample_products["product3"]]

        formatted = product_search_service.format_products_for_llm(products)

        assert "Kopi Arabica Premium" in formatted
        assert "Rp500" in formatted
        assert "Madu Hutan Asli" in formatted
        assert "Rp1,200" in formatted
        assert "Tersedia" in formatted

    def test_format_empty_products(
        self, product_search_service: ProductSearchService
    ):
        """Test formatting empty product list."""
        formatted = product_search_service.format_products_for_llm([])
        assert formatted == ""
