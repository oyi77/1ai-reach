"""Product search service for CS engine - detects product inquiries and searches catalog."""

from typing import List, Optional

from oneai_reach.domain.models.product import Product
from oneai_reach.infrastructure.database.sqlite_product_repository import (
    SQLiteProductRepository,
)
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class ProductSearchService:
    """Service for detecting product inquiries and searching product catalog."""

    # Indonesian keywords that indicate product inquiry
    PRODUCT_KEYWORDS = frozenset(
        {
            "produk",
            "varian",
            "harga",
            "stock",
            "stok",
            "ada gak",
            "ada ga",
            "ada tidak",
            "tersedia",
            "jual",
            "jual apa",
            "ada apa",
            "punya apa",
            "warna",
            "ukuran",
            "size",
            "ready",
            "katalog",
            "daftar produk",
            "list produk",
            "apa aja",
        }
    )

    def __init__(self, product_repository: SQLiteProductRepository):
        """Initialize product search service.

        Args:
            product_repository: Repository for product data access
        """
        self.product_repository = product_repository

    def detect_product_inquiry(self, message_text: str) -> bool:
        """Detect if message is asking about products.

        Args:
            message_text: Customer message text

        Returns:
            True if message contains product inquiry keywords
        """
        msg_lower = message_text.lower()
        return any(keyword in msg_lower for keyword in self.PRODUCT_KEYWORDS)

    def search_products(
        self, wa_number_id: str, query: str, limit: int = 5
    ) -> List[Product]:
        """Search products for a WA number.

        Args:
            wa_number_id: WhatsApp number ID
            query: Search query text
            limit: Maximum number of results

        Returns:
            List of matching products
        """
        try:
            products = self.product_repository.search(wa_number_id, query, limit)
            logger.info(
                f"Product search for wa_number_id={wa_number_id}, query='{query}': {len(products)} results"
            )
            return products
        except Exception as e:
            logger.error(f"Product search failed: {e}")
            return []

    def format_products_for_llm(self, products: List[Product]) -> str:
        """Format product results for LLM prompt context.

        Args:
            products: List of products to format

        Returns:
            Formatted string for LLM context
        """
        if not products:
            return ""

        parts = []
        for i, product in enumerate(products, 1):
            # Format price
            price_rp = product.base_price_cents / 100
            price_str = f"Rp{price_rp:,.0f}"

            # Format stock status
            stock_str = (
                "Tersedia" if product.status.value == "active" else "Tidak tersedia"
            )

            # Build product info
            product_info = f"[{i}] {product.name}"
            if product.description:
                product_info += f" - {product.description}"
            product_info += f"\n    Harga: {price_str}"
            product_info += f"\n    Status: {stock_str}"

            if product.category:
                product_info += f"\n    Kategori: {product.category}"

            if product.sku:
                product_info += f"\n    SKU: {product.sku}"

            parts.append(product_info)

        return "\n\n".join(parts)
