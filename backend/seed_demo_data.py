import os
import sys
import json
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_db, insert_ticket, get_all_tickets
from constants import DEPARTMENTS
from ai_engine import generate_citizen_response


def _make_ticket(
    raw_text: str,
    category: str,
    urgency: str,
    location: str,
    hours_ago_created: int = 5,
    breach_offset_hours: int = 0,
    status: str = "open",
    breached: bool = False,
) -> dict:
    dept_info = DEPARTMENTS[category]
    sla_hours = dept_info["default_sla_hours"][urgency]
    created_at = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours_ago_created)).isoformat()
    sla_deadline = (
        datetime.fromisoformat(created_at)
        + timedelta(hours=sla_hours)
        + timedelta(hours=breach_offset_hours)
    ).isoformat()

    ticket = {
        "ticket_id": None,
        "raw_text": raw_text,
        "category": category,
        "department": dept_info["department"],
        "urgency": urgency,
        "sla_hours": sla_hours,
        "sla_deadline": sla_deadline,
        "status": status,
        "breached": breached,
        "location": location,
        "missing_fields": [],
        "clarification_question": None,
        "citizen_response_message": None,
        "created_at": created_at,
        "escalation_action": None,
    }
    return ticket


def main() -> None:
    init_db()

    existing = get_all_tickets()
    if existing:
        print(f"[seed] Found {len(existing)} existing ticket(s) — skipping seed to avoid duplicates.")
        print("[seed] Delete tickets.db and re-run to re-seed, or continue as-is.")
        return

    breached_ticket = _make_ticket(
        raw_text="Streetlight outside sector 12 community hall has been flickering dangerously for two weeks. Sparks at night. Nobody came despite two complaints.",
        category="Streetlights",
        urgency="high",
        location="Sector 12 Community Hall, Main Road, near park gate",
        hours_ago_created=24 * 4,
        breach_offset_hours=-36,
        status="breached",
        breached=True,
    )
    breached_ticket["escalation_action"] = (
        "Escalate to HOD of Municipal Lighting Department immediately. "
        f"Ticket for category 'Streetlights' has breached its SLA of "
        f"{breached_ticket['sla_hours']} hours. Fire/safety risk. Citizen must be contacted within 2 hours with a resolution timeline."
    )
    bid = insert_ticket(breached_ticket)
    print(f"[seed] Inserted breached demo ticket: {bid}")

    varied = [
        _make_ticket(
            raw_text="Heavy garbage pile near sector 4 bus stop, has not been picked up for 5 days. Rats and smell unbearable.",
            category="Garbage & Sanitation",
            urgency="medium",
            location="Sector 4 Bus Stop, Opposite Green Market",
            hours_ago_created=20,
        ),
        _make_ticket(
            raw_text="Pothole on the link road between sector 7 and 9 has become huge after rain. A two-wheeler skidded yesterday.",
            category="Roads & Potholes",
            urgency="high",
            location="Link Road, Sector 7 / Sector 9 junction",
            hours_ago_created=6,
        ),
        _make_ticket(
            raw_text="Loud DJ music continuing every night past midnight from the banquet hall on MG Road. Elderly and children cannot sleep.",
            category="Noise Complaint",
            urgency="medium",
            location="MG Road, near Sunrise Banquet Hall, Ward 5",
            hours_ago_created=30,
            status="in_progress",
        ),
        _make_ticket(
            raw_text="Sewer drain overflowing on 2nd cross street since yesterday morning. Raw sewage flowing on the road.",
            category="Drainage & Sewage",
            urgency="high",
            location="2nd Cross Street, New Colony, near water tank",
            hours_ago_created=2,
        ),
    ]

    for t in varied:
        temp_for_msg = dict(t)
        t["citizen_response_message"] = generate_citizen_response(temp_for_msg)
        tid = insert_ticket(t)
        print(f"[seed] Inserted ticket: {tid} — {t['category']} ({t['urgency']})")

    print("[seed] Demo seed complete.")


if __name__ == "__main__":
    main()
