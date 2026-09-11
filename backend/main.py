import logging
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import (
    init_db,
    insert_ticket,
    get_all_tickets,
    get_ticket,
    update_ticket_status,
    check_and_flag_breaches,
)
from ai_engine import extract_ticket, clarify_ticket, generate_citizen_response
from models import (
    AnalyzeRequest,
    ClarifyRequest,
    UpdateStatusRequest,
    TicketResponse,
    TicketListResponse,
    StatsResponse,
    HealthResponse,
)
from constants import DEPARTMENTS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NagrikAI Citizen Complaint Triage API",
    description="FastAPI backend for citizen complaint classification, routing, and SLA tracking.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("Database initialized.")


@app.get("/", response_model=HealthResponse, tags=["Health"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/analyze", response_model=TicketResponse, tags=["Tickets"])
def analyze_complaint(req: AnalyzeRequest) -> Dict[str, Any]:
    try:
        ticket = extract_ticket(req.text)
    except Exception as e:
        logger.exception("extract_ticket failed")
        raise HTTPException(status_code=500, detail="Internal error while analyzing complaint.")

    is_complete = len(ticket.get("missing_fields", [])) == 0
    if is_complete:
        try:
            ticket_id = insert_ticket(ticket)
            ticket["ticket_id"] = ticket_id
        except Exception as e:
            logger.exception("insert_ticket failed after analyze")
            raise HTTPException(status_code=500, detail="Internal error while saving ticket.")

    return ticket


@app.post("/api/clarify", response_model=TicketResponse, tags=["Tickets"])
def clarify_complaint(req: ClarifyRequest) -> Dict[str, Any]:
    logger.info(f"Clarify request: original='{req.original_text}' reply='{req.reply}'")
    try:
        ticket = clarify_ticket(req.original_text, req.reply)
    except Exception as e:
        logger.exception("clarify_ticket failed")
        raise HTTPException(status_code=500, detail="Internal error while processing clarification.")

    logger.info(f"Clarify result from ai_engine: {ticket}")

    is_complete = len(ticket.get("missing_fields", [])) == 0
    if is_complete:
        try:
            ticket_id = insert_ticket(ticket)
            ticket["ticket_id"] = ticket_id
            ticket["citizen_response_message"] = generate_citizen_response(ticket)
        except Exception as e:
            logger.exception("insert_ticket failed after clarify")
            raise HTTPException(status_code=500, detail="Internal error while saving ticket.")

    return ticket


@app.get("/api/tickets", response_model=TicketListResponse, tags=["Tickets"])
def list_tickets() -> TicketListResponse:
    try:
        tickets = get_all_tickets()
    except Exception as e:
        logger.exception("get_all_tickets failed")
        raise HTTPException(status_code=500, detail="Internal error while fetching tickets.")
    return TicketListResponse(tickets=tickets)


@app.get("/api/tickets/{ticket_id}", response_model=TicketResponse, tags=["Tickets"])
def get_single_ticket(ticket_id: str) -> Dict[str, Any]:
    try:
        ticket = get_ticket(ticket_id)
    except Exception as e:
        logger.exception(f"get_ticket failed for %s", ticket_id)
        raise HTTPException(status_code=500, detail="Internal error while fetching ticket.")
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


@app.patch("/api/tickets/{ticket_id}/status", response_model=TicketResponse, tags=["Tickets"])
def set_ticket_status(ticket_id: str, req: UpdateStatusRequest) -> Dict[str, Any]:
    existing = get_ticket(ticket_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    from constants import STATUS_CHOICES
    if req.status not in STATUS_CHOICES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {STATUS_CHOICES}.")

    try:
        updated = update_ticket_status(
            ticket_id=ticket_id,
            status=req.status,
            breached=req.breached,
            escalation_action=req.escalation_action,
        )
    except Exception as e:
        logger.exception(f"update_ticket_status failed for %s", ticket_id)
        raise HTTPException(status_code=500, detail="Internal error while updating ticket.")

    if updated is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return updated


@app.post("/api/check-breaches", response_model=TicketListResponse, tags=["Tickets"])
def trigger_breach_check() -> TicketListResponse:
    try:
        breached = check_and_flag_breaches()
    except Exception as e:
        logger.exception("check_and_flag_breaches failed")
        raise HTTPException(status_code=500, detail="Internal error while checking breaches.")
    return TicketListResponse(tickets=breached)


@app.get("/api/stats", response_model=StatsResponse, tags=["Dashboard"])
def dashboard_stats() -> StatsResponse:
    try:
        tickets = get_all_tickets()
    except Exception as e:
        logger.exception("get_all_tickets failed in stats")
        raise HTTPException(status_code=500, detail="Internal error while fetching stats.")

    by_category: Dict[str, int] = {cat: 0 for cat in DEPARTMENTS.keys()}
    by_department: Dict[str, int] = {}

    for t in tickets:
        cat = t.get("category", "Other")
        if cat in by_category:
            by_category[cat] += 1
        dept = t.get("department", "General Grievance Cell")
        by_department[dept] = by_department.get(dept, 0) + 1

    return StatsResponse(by_category=by_category, by_department=by_department)
