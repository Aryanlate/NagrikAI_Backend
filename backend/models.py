from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw complaint text from citizen")


class ClarifyRequest(BaseModel):
    original_text: str = Field(..., description="Original complaint text")
    reply: str = Field(..., description="Citizen's reply to clarification question")


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., description="New status: open | in_progress | resolved | breached")
    breached: Optional[bool] = Field(False, description="Whether ticket has breached SLA")
    escalation_action: Optional[str] = Field(None, description="Escalation action if breached")


class TicketResponse(BaseModel):
    ticket_id: Optional[str] = Field(None, description="Unique ticket ID, e.g. TKT-0001")
    raw_text: str = Field(..., description="Original complaint text")
    category: str = Field(..., description="One of 10 fixed categories")
    department: str = Field(..., description="Responsible department name")
    urgency: str = Field(..., description="low | medium | high")
    sla_hours: int = Field(..., description="SLA hours based on category and urgency")
    sla_deadline: str = Field(..., description="ISO 8601 deadline datetime")
    status: str = Field(..., description="open | in_progress | resolved | breached")
    breached: bool = Field(False, description="True if past SLA deadline")
    location: Optional[str] = Field(None, description="Location string or null")
    missing_fields: List[str] = Field(default_factory=list, description="Fields still missing")
    clarification_question: Optional[str] = Field(None, description="Question if missing_fields non-empty")
    citizen_response_message: Optional[str] = Field(None, description="Polite confirmation once complete")
    created_at: str = Field(..., description="ISO 8601 creation datetime")
    escalation_action: Optional[str] = Field(None, description="Recommended action if breached")


class TicketListResponse(BaseModel):
    tickets: List[TicketResponse] = Field(default_factory=list, description="List of tickets")


class StatsResponse(BaseModel):
    by_category: Dict[str, int] = Field(default_factory=dict, description="Ticket counts by category")
    by_department: Dict[str, int] = Field(default_factory=dict, description="Ticket counts by department")


class HealthResponse(BaseModel):
    status: str = "ok"
