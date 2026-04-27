"""
CS Learn CLI — Manual training and playbook management tool.

Usage:
  python3 scripts/cs_learn_cli.py --seed-flosia          # Seed Flosia-specific KB
  python3 scripts/cs_learn_cli.py --add-response        # Add new response pattern
  python3 scripts/cs_learn_cli.py --train-scenario        # Interactive training mode
  python3 scripts/cs_learn_cli.py --analytics             # Show performance metrics
  python3 scripts/cs_learn_cli.py --auto-learn            # Auto-extract from outcomes
"""

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from kb_manager import add_entry, seed_default_kb, search, get_entries
from cs_outcomes import init_outcomes_db, extract_learnings, mark_learning_extracted
from cs_analytics import CSAnalytics
from state_manager import init_db


_FLOSIA_KB_ENTRIES = [
    {
        "category": "faq",
        "question": "Apa itu parfum laundry Flosia?",
        "answer": (
            "Flosia adalah parfum laundry premium dengan wangi tahan lama hingga 3 hari. "
            "Konsentrat tinggi sehingga lebih hemat penggunaan. Tersedia varian:"
            "Aqua Fresh, Sweet Bubblegum, dan Royal Perfume. Cocok untuk laundry komersial maupun pribadi."
        ),
        "content": "parfum laundry flosia wangi tahan lama konsentrat hemat varian",
        "tags": "product,flosia,parfum,info",
        "priority": 10,
    },
    {
        "category": "faq",
        "question": "Berapa harga parfum laundry Flosia?",
        "answer": (
            "Harga Flosia parfum laundry:\n"
            "• Paket Trial 500ml: Rp35.000\n"
            "• Jerigen 5L: Rp95.000 (bisa untuk 150kg pakaian = Rp633/kg)\n"
            "• Paket Hemat 3 Jerigen: Rp242.250 (hemat 15% + gratis spray 250ml)\n"
            "\nLebih hemat dari deterjen biasa dan wanginya awet 3 hari!"
        ),
        "content": "harga flosia parfum laundry 500ml jerigen 5L paket hemat",
        "tags": "harga,pricing,flosia,product",
        "priority": 10,
    },
    {
        "category": "snippet",
        "question": "Menangani keluhan harga mahal",
        "answer": (
            "Kak, coba hitung ya: 1 jerigen 5L Flosia bisa untuk 150kg pakaian, "
            "jadi cuma Rp633 per kg. Lebih hemat dari deterjen biasa! "
            "Plus wanginya awet 3 hari. Ada juga Paket Trial 500ml Rp35.000 "
            "kalau mau coba dulu. Mau yang mana?"
        ),
        "content": "harga mahal reframe value calculation hemat deterjen",
        "tags": "price_objection,learned,closing",
        "priority": 9,
    },
    {
        "category": "snippet",
        "question": "Closing - siap order",
        "answer": (
            "Mantap Kak! Saya catat:\n\n"
            "📦 Paket Flosia\n"
            "💰 Total: [total]\n"
            "📍 Alamat: [belum diisi]\n"
            "📱 No HP: [belum diisi]\n\n"
            "Bisa diisi datanya? Biar langsung kirim hari ini! 🚀"
        ),
        "content": "closing order catat data alamat kirim hari ini",
        "tags": "closing,order,ready_to_buy",
        "priority": 9,
    },
    {
        "category": "snippet",
        "question": "Menanggapi pertanyaan ongkir",
        "answer": (
            "Ongkir ke [lokasi] cuma Rp[lokasi] ya Kak. Masih terjangkau untuk kualitas premium. "
            "Atau kalau mau GRATIS ongkir, bisa order via Shopee kami: "
            "https://s.shopee.co.id/1Lbo3T6GmI (link official Flosia). Gimana Kak?"
        ),
        "content": "ongkir pengiriman gratis shopee link jawa luar",
        "tags": "shipping,ongkir,shopee,alternative",
        "priority": 8,
    },
    {
        "category": "snippet",
        "question": "Menanggapi permintaan grosir",
        "answer": (
            "Buat order besar minimal 3 jerigen, kita kasih harga khusus grosir "
            "+ kirim via KALOG cargo (ongkir jauh lebih murah dari reguler). "
            "Minat detailnya Kak? Bisa juga jadi reseller dengan keuntungan 20%."
        ),
        "content": "grosir reseller bulk order cargo KALOG minimal 3 jerigen",
        "tags": "grosir,bulk,reseller,wholesale",
        "priority": 8,
    },
    {
        "category": "faq",
        "question": "Berapa lama wanginya tahan?",
        "answer": (
            "Wangi Flosia tahan hingga 3 hari pada pakaian yang disimpan dengan baik. "
            "Untuk hasil optimal, gunakan sesuai takaran (1-2 tutup per kg pakaian kering) "
            "dan jemur di tempat yang tidak terkena sinar matahari langsung."
        ),
        "content": "wangi tahan lama 3 hari takaran optimal jemur",
        "tags": "product,quality,awet,wangi",
        "priority": 7,
    },
    {
        "category": "snippet",
        "question": "Menanggapi keraguan trust",
        "answer": (
            "Ngerti banget Kak, wajar was-was 😊 Flosia sudah 500+ customer aktif, "
            "rating Shopee 4.9/5. Bisa cek testimoni real di @flosia.jombang. "
            "Atau kalau mau lebih aman, order via Shopee bisa COD. "
            "Link: https://s.shopee.co.id/1Lbo3T6GmI"
        ),
        "content": "trust aman shopee rating testimoni COD link",
        "tags": "trust,doubt,aman,shopee,COD",
        "priority": 8,
    },
    {
        "category": "snippet",
        "question": "Follow up pelanggan yang belum membalas",
        "answer": (
            "Halo Kak! Masih tertarik dengan parfum laundry Flosia? "
            "Stock jerigen 5L masih ada nih, tapi tinggal 5 unit lagi. "
            "Mau saya reserve satu untuk Kakak? 😊"
        ),
        "content": "followup stock habis reserve reminder",
        "tags": "followup,scarcity,gentle",
        "priority": 6,
    },
    {
        "category": "doc",
        "question": "Informasi pembayaran Flosia",
        "answer": (
            "Metode pembayaran Flosia:\n"
            "• Transfer BCA: 1131339351 a/n Andik Veris Febriyanto\n"
            "• QRIS (all e-wallet)\n"
            "• Shopee (bisa COD/cicilan)\n\n"
            "Screenshot transfer + kirim alamat = langsung proses kirim hari ini!"
        ),
        "content": "pembayaran transfer BCA QRIS shopee COD rekening",
        "tags": "payment,pembayaran,BCA,transfer",
        "priority": 9,
    },
]


def seed_flosia_kb(wa_number_id: str) -> int:
    """Seed Flosia-specific KB entries."""
    existing = get_entries(wa_number_id)
    existing_questions = {e["question"] for e in existing}

    count = 0
    for entry in _FLOSIA_KB_ENTRIES:
        if entry["question"] in existing_questions:
            continue
        add_entry(
            wa_number_id,
            entry["category"],
            entry["question"],
            entry["answer"],
            entry.get("content", ""),
            entry.get("tags", ""),
            entry.get("priority", 0),
        )
        count += 1

    return count


def interactive_training_mode(wa_number_id: str):
    """Interactive mode to train responses."""
    from cs_playbook import CSPlaybook, AdaptiveContext

    playbook = CSPlaybook()
    context = AdaptiveContext(wa_number_id, "training_session")

    print("\n🎓 CS Training Mode")
    print("Ketik 'quit' untuk keluar, 'save' untuk menyimpan ke KB\n")

    while True:
        try:
            message = input("Customer: ").strip()
            if message.lower() in ["quit", "exit"]:
                break

            scenario = playbook.detect_scenario(message)
            user_type = context.get_user_profile()

            print(f"[Detected: {scenario} | User: {user_type}]")

            # Get response from playbook
            response_data = playbook.get_response(scenario, user_type, {})
            print(f"AI: {response_data['response']}")
            print(f"[Pattern: {response_data['pattern_id']}]\n")

            # Ask if we should save this interaction
            feedback = input("Save to KB? (y/n/edit): ").strip().lower()
            if feedback == "y":
                question = f"Scenario: {scenario} - '{message[:30]}...'"
                answer = response_data["response"]
                entry_id = add_entry(
                    wa_number_id,
                    "snippet",
                    question,
                    answer,
                    f"trained {scenario}",
                    f"trained,{scenario},manual",
                    7,
                )
                print(f"✅ Saved to KB (id={entry_id})\n")
            elif feedback == "edit":
                custom_answer = input("Custom answer: ").strip()
                question = f"Scenario: {scenario} - '{message[:30]}...'"
                entry_id = add_entry(
                    wa_number_id,
                    "snippet",
                    question,
                    custom_answer,
                    f"trained {scenario}",
                    f"trained,{scenario},manual",
                    7,
                )
                print(f"✅ Saved custom to KB (id={entry_id})\n")

            context.update(scenario, response_data["pattern_id"], message)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}\n")

    print("\nTraining session ended.")


def show_analytics():
    """Display comprehensive analytics."""
    analytics = CSAnalytics()

    print("\n📊 CS Analytics Dashboard\n")

    # KB Rankings
    rankings = analytics.get_kb_rankings(days=30, min_uses=2)
    print(f"🏆 Top KB Entries ({len(rankings)} found):")
    for i, r in enumerate(rankings[:5], 1):
        score = r.get("avg_score") or 0
        print(f"{i}. [{r['id']}] Score: {score:.2f} | {r['times_used']} uses")
        print(f"   Q: {r['question'][:50]}...")

    # Scenario Performance
    scenarios = analytics.get_scenario_performance(days=30)
    print(f"\n📈 Scenario Performance:")
    for pattern, stats in sorted(
        scenarios.items(), key=lambda x: x[1]["success_rate"], reverse=True
    )[:5]:
        print(f"  {pattern}: {stats['success_rate']:.2f} score ({stats['total']} uses)")

    # Recommendations
    recs = analytics.get_learning_recommendations()
    print(f"\n💡 Recommendations ({len(recs)} total):")
    for r in recs[:3]:
        print(f"  [{r['type']}] {r['reason']}")
        print(f"    → {r['action']}")

    analytics.close()


def auto_learn():
    """Extract learnings from outcomes and add to KB."""
    learnings = extract_learnings(limit=10)
    print(f"\n🧠 Auto-Learning Mode")
    print(f"Found {len(learnings)} conversations to learn from\n")

    for learning in learnings:
        print(f"Conversation {learning['conversation_id']} ({learning['scenario']}):")
        for i, resp in enumerate(learning["responses"][:3], 1):
            print(f"  {i}. {resp['response'][:60]}...")

        # Mark as extracted
        mark_learning_extracted(learning["id"])
        print("  ✅ Extracted\n")

    print(f"Done. Extracted {len(learnings)} patterns.")


def list_kb(wa_number_id: str, category: str = None):
    """List KB entries."""
    from kb_manager import get_entries

    entries = get_entries(wa_number_id, category)
    print(f"\n📚 KB Entries for '{wa_number_id}'")
    if category:
        print(f"Category: {category}")

    for e in entries:
        cat = e.get("category", "?")
        print(f"[{e['id']}] ({cat}) {e['question'][:60]}...")

    print(f"\nTotal: {len(entries)} entries")


if __name__ == "__main__":
    init_db()
    init_outcomes_db()

    p = argparse.ArgumentParser(description="CS Learning & Training CLI")
    p.add_argument("--wa-number-id", default="warung_kecantikan", help="WA number ID")
    p.add_argument("--seed-flosia", action="store_true", help="Seed Flosia KB")
    p.add_argument("--seed-default", action="store_true", help="Seed default FAQ")
    p.add_argument("--train", action="store_true", help="Interactive training mode")
    p.add_argument("--analytics", action="store_true", help="Show analytics")
    p.add_argument("--auto-learn", action="store_true", help="Auto-extract learnings")
    p.add_argument("--list", action="store_true", help="List KB entries")
    p.add_argument("--category", help="Filter by category")

    args = p.parse_args()

    if args.seed_flosia:
        count = seed_flosia_kb(args.wa_number_id)
        print(f"✅ Seeded {count} Flosia entries")

    elif args.seed_default:
        count = seed_default_kb(args.wa_number_id)
        print(f"✅ Seeded {count} default FAQ entries")

    elif args.train:
        interactive_training_mode(args.wa_number_id)

    elif args.analytics:
        show_analytics()

    elif args.auto_learn:
        auto_learn()

    elif args.list:
        list_kb(args.wa_number_id, args.category)

    else:
        p.print_help()
        print("\nExamples:")
        print("  python3 scripts/cs_learn_cli.py --seed-flosia")
        print("  python3 scripts/cs_learn_cli.py --train")
        print("  python3 scripts/cs_learn_cli.py --analytics")
        print("  python3 scripts/cs_learn_cli.py --auto-learn")
