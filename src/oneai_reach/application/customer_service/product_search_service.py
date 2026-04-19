"""Product search service for CS engine - detects product inquiries and searches catalog."""

from typing import Dict, List, Optional

from oneai_reach.domain.models.product import Product
from oneai_reach.domain.repositories.product_repository import ProductRepository
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

# Keywords that indicate product search intent (ordered by priority)
# More specific terms first (product names/categories), then generic query terms
_PRODUCT_QUERY_KEYWORDS = [
    # Product name/categories (highest priority)
    "kopi", "teh", "susu", "cokelat", "matcha", "green tea", "latte", "espresso",
    "makanan", "snack", "kue", "roti", "biskuit", "cereal", "mie",
    "pakaian", "baju", "sepatu", "tas", "celana", "jacket", "hoodie",
    "elektronik", "hp", "laptop", "charger", "earphone", "speaker",
    "kecantikan", "skincare", "serum", "masker", "lipstik", "parfum",
    # Variant/options related
    "varian", "ukuran", "size", "warna", "color", "motif", "model",
    "gram", "ml", "liter", "kg", "pcs", "box",
    # Product attributes (images, stock, price) - MORE keywords!
    "gambar", "foto", "image", "photo", "lihat", "cek", "display", "lihat produk",
    "stock", "stok", "tersedia", "ready", "habis", "kosong", "masih ada", "ada lagi",
    "harga", "Harga", "HARGA", "priced", "murah", "mahal", "diskon", "promo", "sale",
    # Purchase intent
    "beli", "pesan", "order", "jual", "pemesanan", "pemesanan", "order",
    "can", "bisa", "ga", "gak", "nggak", "ada", "tersedia", "ready",
    # General inquiry - MORE!
    "produk", "catalog", "katalog", "list", "daftar", "apa", "saja", "avail", 
    "pesanan", "shipping", "kirim", "delivery", " COD ", "cod", "bayar", "pembayaran",
    "habis", "sold out", "soldout",
]

class ProductSearchService:
    """Service for detecting product inquiries and searching product catalog."""

    # Indonesian keywords that indicate product inquiry
    PRODUCT_KEYWORDS = frozenset(
        {
            # Basic product terms
            "produk", "produk", "barang", "item",
            # Variant/size/color
            "varian", "warna", "ukuran", "size", "ukuran", 
            # Price-related
            "harga", "priced", "cost", "uang", "rupiah", "diskon", "promo", "murah", "mahal",
            # Stock availability
            "stock", "stok", "tersedia", "ready", "ada", "habis", "kosong", 
            "ada gak", "ada ga", "ada tidak", "ready", "tersedia", 
            # Stock availability - MORE!
            "stock", "stok", "habis", "kosong", "masih ada", "ada lagi", "sold out", "ready",
            # Purchase intent
            "jual", "beli", "pesan", "order", "pemesanan", "punya apa", "mau beli", "mau pesan",
            # Catalog/inquiry
            "katalog", "catalog", "list produk", "daftar produk", "apa aja", "ada apa",
            # Images/pictures  
            "gambar", "foto", "image", "photo", "lihat", "cek", "display", "lihat produk", "kirim foto",
            # Delivery
            "kirim", "shipping", "delivery", "COD", "cod",
            # Price
            "harga", "murah", "mahal", "diskon", "promo", "sale", "Harga",
            # Categories common in Indonesia
            "makanan", "minuman", "pakaian", "kecantikan", "elektronik", "kopi", "teh", "susu",
        }
    )

    def __init__(self, product_repository: ProductRepository):
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
        
        # Check for catalog listing requests
        catalog_keywords = ["semua", "list", "catalog", "katalog", "semua produk", "list produk"]
        if any(keyword in msg_lower for keyword in catalog_keywords):
            return True
        
        return any(keyword in msg_lower for keyword in self.PRODUCT_KEYWORDS)

    def _extract_search_keywords(self, message: str) -> str:
        """Extract product search keywords from message text.
        
        Args:
            message: Customer message
            
        Returns:
            Best keyword to search for products
        """
        msg_lower = message.lower()
        
        # Check for each query keyword in the message
        for keyword in _PRODUCT_QUERY_KEYWORDS:
            if keyword in msg_lower:
                return keyword
        
        # Fall back to full message if no keyword matched
        return message

    def get_all_products(self, wa_number_id: str, limit: int = 10) -> List[Product]:
        """Get all products for a WA number (fallback when search returns empty).

        Args:
            wa_number_id: WhatsApp number ID
            limit: Maximum number of results

        Returns:
            List of all products
        """
        try:
            products = self.product_repository.get_all(wa_number_id)
            return products[:limit] if products else []
        except Exception as e:
            logger.error(f"Get all products failed: {e}")
            return []

    def search_products(
        self, wa_number_id: str, query: str, limit: int = 5, is_product_inquiry: bool = True
    ) -> List[Product]:
        """Search products for a WA number.

        Args:
            wa_number_id: WhatsApp number ID
            query: Search query text (or full message to extract keywords from)
            limit: Maximum number of results
            is_product_inquiry: Whether this is a product inquiry (controls fallback behavior)

        Returns:
            List of matching products
        """
        try:
            products = self.product_repository.search(wa_number_id, query, limit)
            
            if not products:
                search_term = self._extract_search_keywords(query)
                products = self.product_repository.search(wa_number_id, search_term, limit)
            
            # Only return all products as fallback if this is a product inquiry
            if not products and is_product_inquiry:
                products = self.get_all_products(wa_number_id, limit)
                logger.info(
                    f"No search results for wa_number_id={wa_number_id}, query='{query}'. Returning all products: {len(products)} results"
                )
            else:
                logger.info(
                    f"Product search for wa_number_id={wa_number_id}, query='{query}': {len(products)} results"
                )
            
            return products
        except Exception as e:
            logger.error(f"Product search failed: {e}")
            return []

    def format_products_for_llm(
        self, 
        products: List[Product], 
        image_urls: Optional[dict] = None
    ) -> str:
        """Format product results for LLM prompt context.

        Args:
            products: List of products to format
            image_urls: Optional dict mapping product_id to list of image URLs

        Returns:
            Formatted string for LLM context
        """
        if not products:
            return ""

        parts = []
        for i, product in enumerate(products, 1):
            price_rp = product.base_price_cents / 100
            price_str = f"Rp{price_rp:,.0f}"

            stock_str = (
                "Tersedia" if product.status.value == "active" else "Tidak tersedia"
            )

            product_info = f"[{i}] {product.name}"
            if product.description:
                product_info += f" - {product.description}"
            product_info += f"\n    Harga: {price_str}"
            product_info += f"\n    Status: {stock_str}"

            if product.category:
                product_info += f"\n    Kategori: {product.category}"

            if product.sku:
                product_info += f"\n    SKU: {product.sku}"

            if image_urls and product.id in image_urls:
                urls = image_urls[product.id]
                if urls:
                    product_info += f"\n    Gambar: {', '.join(urls)}"

            parts.append(product_info)

        return "\n\n".join(parts)
