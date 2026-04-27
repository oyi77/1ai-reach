import requests
import json
import time
import hashlib
import os
from pathlib import Path

# Load config
_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = _ROOT / "capi_config.json"

class MetaCAPITracker:
    def __init__(self):
        self.pixel_id = None
        self.access_token = None
        self.config = {}
        self.load_config()

    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                self.config = json.loads(CONFIG_FILE.read_text())
                self.pixel_id = self.config.get("pixel_id")
                self.access_token = self.config.get("access_token")
            except Exception as e:
                print(f"[capi_tracker] Failed to load config: {e}")

    def _hash_data(self, data):
        if not data:
            return None
        return hashlib.sha256(str(data).strip().lower().encode()).hexdigest()

    def track_event(self, event_name, phone=None, value=0.0, currency="IDR", event_source_url=None):
        if not self.pixel_id or not self.access_token:
            return False

        url = f"https://graph.facebook.com/v19.0/{self.pixel_id}/events?access_token={self.access_token}"
        
        user_data = {}
        if phone:
            # Clean phone
            clean_phone = "".join(filter(str.isdigit, str(phone)))
            user_data["em"] = [self._hash_data(f"{clean_phone}@c.us")] # Dummy hash for compatibility if needed or use ph
            user_data["ph"] = [self._hash_data(clean_phone)]
            user_data["external_id"] = [self._hash_data(clean_phone)]

        payload = {
            "data": [
                {
                    "event_name": event_name,
                    "event_time": int(time.time()),
                    "action_source": "chat",
                    "event_source_url": event_source_url or "https://wa.me/c/6285187514359",
                    "user_data": user_data,
                    "custom_data": {
                        "value": value,
                        "currency": currency
                    }
                }
            ]
        }

        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code < 300:
                print(f"[capi_tracker] ✅ Event '{event_name}' sent for {phone}")
                return True
            else:
                print(f"[capi_tracker] ❌ Failed to send event: {r.text}")
                return False
        except Exception as e:
            print(f"[capi_tracker] ❌ Error sending event: {e}")
            return False

# Global instance
tracker = MetaCAPITracker()

def track_lead(phone):
    return tracker.track_event("Lead", phone=phone)

def track_purchase(phone, value=0.0):
    return tracker.track_event("Purchase", phone=phone, value=value)

def track_atc(phone, value=0.0):
    return tracker.track_event("AddToCart", phone=phone, value=value)

def track_view_content(phone, value=0.0):
    return tracker.track_event("ViewContent", phone=phone, value=value)
