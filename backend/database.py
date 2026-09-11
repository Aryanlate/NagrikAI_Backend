import sqlite3
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from constants import DEPARTMENTS, LOCATION_REQUIRED_CATEGORIES

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tickets.db")


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id TEXT PRIMARY KEY,
                raw_text TEXT NOT NULL,
                category TEXT NOT NULL,
                department TEXT NOT NULL,
                urgency TEXT NOT NULL,
                sla_hours INTEGER NOT NULL,
                sla_deadline TEXT NOT NULL,
                status TEXT NOT NULL,
                breached INTEGER NOT NULL DEFAULT 0,
                location TEXT,
                missing_fields TEXT NOT NULL DEFAULT '[]',
                clarification_question TEXT,
                citizen_response_message TEXT,
                created_at TEXT NOT NULL,
                escalation_action TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    if "missing_fields" in data and isinstance(data["missing_fields"], str):
        try:
            data["missing_fields"] = json.loads(data["missing_fields"])
        except (json.JSONDecodeError, TypeError):
            data["missing_fields"] = []
    data["breached"] = bool(data.get("breached", 0))
    return data


def _get_next_ticket_id(conn: sqlite3.Connection) -> str:
    cursor = conn.execute("SELECT ticket_id FROM tickets ORDER BY ticket_id DESC LIMIT 1")
    row = cursor.fetchone()
    if row is None:
        return "TKT-0001"
    last_id = row["ticket_id"]
    try:
        num = int(last_id.split("-")[1])
        return f"TKT-{num + 1:04d}"
    except (IndexError, ValueError):
        return "TKT-0001"


def insert_ticket(ticket: Dict[str, Any]) -> str:
    conn = _get_connection()
    try:
        if not ticket.get("ticket_id"):
            ticket["ticket_id"] = _get_next_ticket_id(conn)

        missing_fields_json = json.dumps(ticket.get("missing_fields", []), ensure_ascii=False)

        conn.execute(
            """
            INSERT INTO tickets (
                ticket_id, raw_text, category, department, urgency,
                sla_hours, sla_deadline, status, breached, location,
                missing_fields, clarification_question, citizen_response_message,
                created_at, escalation_action
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket["ticket_id"],
                ticket["raw_text"],
                ticket["category"],
                ticket["department"],
                ticket["urgency"],
                ticket["sla_hours"],
                ticket["sla_deadline"],
                ticket["status"],
                1 if ticket.get("breached") else 0,
                ticket.get("location"),
                missing_fields_json,
                ticket.get("clarification_question"),
                ticket.get("citizen_response_message"),
                ticket["created_at"],
                ticket.get("escalation_action"),
            ),
        )
        conn.commit()
        return ticket["ticket_id"]
    finally:
        conn.close()


def get_all_tickets() -> List[Dict[str, Any]]:
    conn = _get_connection()
    try:
        cursor = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def get_ticket(ticket_id: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    try:
        cursor = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def update_ticket_status(
    ticket_id: str,
    status: str,
    breached: bool,
    escalation_action: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    try:
        conn.execute(
            """
            UPDATE tickets
            SET status = ?, breached = ?, escalation_action = ?
            WHERE ticket_id = ?
            """,
            (status, 1 if breached else 0, escalation_action, ticket_id),
        )
        conn.commit()
        return get_ticket(ticket_id)
    finally:
        conn.close()


def _generate_escalation_action(ticket: Dict[str, Any]) -> str:
    dept = ticket.get("department", "the concerned department")
    urgency = ticket.get("urgency", "medium")
    urgency_map = {"high": "immediately", "medium": "as soon as possible", "low": "at the earliest"}
    action = (
        f"Escalate to HOD of {dept} {urgency_map.get(urgency, 'immediately')}. "
        f"Ticket {ticket.get('ticket_id')} for category '{ticket.get('category')}' "
        f"has breached its SLA of {ticket.get('sla_hours')} hours. "
        f"Citizen should be contacted with a resolution timeline within 2 hours."
    )
    return action


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def check_and_flag_breaches() -> List[Dict[str, Any]]:
    conn = _get_connection()
    now_iso = _utcnow_iso()
    breached_ids: List[str] = []
    try:
        cursor = conn.execute(
            """
            SELECT * FROM tickets
            WHERE status IN ('open', 'in_progress') AND breached = 0
            """
        )
        rows = cursor.fetchall()
        for row in rows:
            ticket = _row_to_dict(row)
            deadline = ticket.get("sla_deadline", "")
            if deadline and deadline < now_iso:
                escalation = _generate_escalation_action(ticket)
                conn.execute(
                    """
                    UPDATE tickets
                    SET status = 'breached', breached = 1, escalation_action = ?
                    WHERE ticket_id = ?
                    """,
                    (escalation, ticket["ticket_id"]),
                )
                breached_ids.append(ticket["ticket_id"])
        conn.commit()

        breached_tickets: List[Dict[str, Any]] = []
        if breached_ids:
            qmarks = ",".join("?" * len(breached_ids))
            cursor = conn.execute(
                f"SELECT * FROM tickets WHERE ticket_id IN ({qmarks})",
                breached_ids,
            )
            breached_tickets = [_row_to_dict(r) for r in cursor.fetchall()]
        return breached_tickets
    finally:
        conn.close()
