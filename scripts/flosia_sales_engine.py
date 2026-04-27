import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oneai_reach.application.agents.flosia_sales_service import FlosiaSalesService
from oneai_reach.config.settings import get_settings


def main():
    settings = get_settings()
    service = FlosiaSalesService(settings)
    
    context = {
        "state": "ENTRY",
        "user_type": "normal",
        "ongkir": 15000,
        "order_value": 110000,
    }
    
    result = service.get_response("Halo", context)
    print(f"Response: {result['response']}")
    print(f"Next state: {result['next_state']}")


if __name__ == "__main__":
    main()
