import json
import random

class FlosiaSalesEngine:
    STATES = ["ENTRY", "QUALIFY", "OFFER", "ONGKIR", "MICRO_CLOSE", "CLOSE"]
    
    BEST_PATTERNS = {
        "ENTRY": {
            "normal": "intro_ask_usecase",
            "urgent": "intro_fast_track"
        },
        "QUALIFY": {
            "normal": "relate_benefit_ask_cat",
            "price_sensitive": "relate_value_focus"
        },
        "OFFER": {
            "normal": "recommend_bestseller",
            "bulk": "recommend_cargo_bulk"
        },
        "ONGKIR": {
            "normal": "show_ongkir_cta",
            "friction": "show_ongkir_shopee_fallback"
        },
        "MICRO_CLOSE": {
            "normal": "ask_details_assume",
        },
        "CLOSE": {
            "normal": "confirm_payment_bca",
        }
    }

    PATTERN_POOL = {
        "intro_ask_usecase": "Halo Kak! Salam kenal dari Flosia Jombang 😊 Produk parfum laundry premium kami ready ya. Kakak rencananya untuk pemakaian pribadi atau untuk usaha laundry nih?",
        "intro_fast_track": "Halo Kak! Flosia Jombang ready stok. Mau langsung diorder biar dikirim hari ini? Buat pribadi atau laundry Kak?",
        "relate_benefit_ask_cat": "Wah pas banget Kak! Flosia ini emang andalan karena wanginya super awet seharian dan jauh lebih hemat pemakaiannya 👍 Kakak mau cari parfum laundry, detergen, atau pembersih otomotif dulu?",
        "relate_value_focus": "Pilihan tepat Kak! Pakai Flosia itu jatuhnya lebih hemat karena konsentratnya tinggi, jadi irit banget buat jangka panjang. Mau lihat katalog harga paketnya?",
        "recommend_bestseller": "Untuk Kakak, saya rekomendasikan Best Seller kami: Paket Jerigen 5L + Parfum Spray 250ml. Paling irit harganya dan puas kualitasnya Kak! Mau ambil Paket Hemat ini?",
        "recommend_cargo_bulk": "Buat kebutuhan besar, saya sarankan ambil minimal 3 jerigen (15L) Kak. Harga grosir lebih miring dan kirimnya pakai KALOG biar ongkirnya super murah. Minat Kak?",
        "show_ongkir_cta": "Ongkir ke area Kakak cuma Rp{ongkir:,} saja ya Kak. Masih sangat terjangkau kok untuk kualitas premium Flosia 😊 Saya bantu siapkan pesanannya sekarang ya?",
        "show_ongkir_shopee_fallback": "Ongkir reguler ke tempat Kakak Rp{ongkir:,} ya Kak. Tapi kalau Kakak mau dapet GRATIS ONGKIR, bisa banget order lewat Shopee kami di sini: https://s.shopee.co.id/1Lbo3T6GmI hhe. Gimana Kak?",
        "ask_details_assume": "Siap Kak! Boleh dibantu isi data pengirimannya dulu ya biar langsung kami rekap:\n\nNama:\nNo HP:\nAlamat Lengkap:\n\nFormatnya diisi dulu ya Kak agar pesanan segera meluncur! 🚀",
        "confirm_payment_bca": "Data sudah saya simpan ya Kak 🙏 Totalnya jadi Rp{order_value:,}. Pembayaran via transfer ke BCA 1131339351 a/n Andik Veris Febriyanto. Begitu dana masuk langsung kami proses kirim hari ini! 😊"
    }

    def __init__(self, context=None):
        self.context = context or {
            "state": "ENTRY",
            "user_type": "normal",
            "product_name": "Flosia",
            "ongkir": 15000,
            "order_value": 110000,
            "customer_type": "new"
        }

    def select_pattern(self, state, user_type):
        # 1. Get best pattern for context
        best = self.BEST_PATTERNS.get(state, {}).get(user_type) or self.BEST_PATTERNS.get(state, {}).get("normal")
        
        # 2. Occasional exploration (10% chance)
        if random.random() < 0.1:
            alternatives = [p for p in self.PATTERN_POOL if p.startswith(state.lower()) and p != best]
            if alternatives:
                return random.choice(alternatives)
        
        return best

    def get_response(self, message_text):
        state = self.context.get("state", "ENTRY")
        # Reuse existing detection logic if available or simplified here
        user_type = self.context.get("user_type", "normal")
        
        pattern_id = self.select_pattern(state, user_type)
        response_template = self.PATTERN_POOL.get(pattern_id, "Halo Kak, ada yang bisa dibantu?")
        
        # Format variables
        response = response_template.format(
            ongkir=self.context.get("ongkir", 15000),
            order_value=self.context.get("order_value", 110000)
        )
        
        # Determine next state
        state_idx = self.STATES.index(state)
        next_state = self.STATES[min(state_idx + 1, len(self.STATES) - 1)]

        return {
            "next_state": next_state,
            "response": response,
            "strategy": f"pattern_{user_type}",
            "pattern_used": pattern_id,
            "confidence": 0.95
        }
