DEPARTMENTS = {
    "Water Supply": {
        "department": "Water Supply Board",
        "default_sla_hours": {"high": 4, "medium": 24, "low": 72},
    },
    "Electricity": {
        "department": "Electricity Department",
        "default_sla_hours": {"high": 2, "medium": 12, "low": 48},
    },
    "Roads & Potholes": {
        "department": "Public Works Department (PWD)",
        "default_sla_hours": {"high": 8, "medium": 48, "low": 120},
    },
    "Garbage & Sanitation": {
        "department": "Municipal Sanitation Department",
        "default_sla_hours": {"high": 6, "medium": 24, "low": 72},
    },
    "Streetlights": {
        "department": "Municipal Lighting Department",
        "default_sla_hours": {"high": 12, "medium": 48, "low": 120},
    },
    "Drainage & Sewage": {
        "department": "Drainage & Sewage Board",
        "default_sla_hours": {"high": 4, "medium": 24, "low": 72},
    },
    "Public Safety": {
        "department": "Local Police Department",
        "default_sla_hours": {"high": 1, "medium": 6, "low": 24},
    },
    "Noise Complaint": {
        "department": "Municipal Noise Control Cell",
        "default_sla_hours": {"high": 4, "medium": 24, "low": 72},
    },
    "Illegal Construction": {
        "department": "Town Planning & Building Department",
        "default_sla_hours": {"high": 24, "medium": 72, "low": 168},
    },
    "Other": {
        "department": "General Grievance Cell",
        "default_sla_hours": {"high": 12, "medium": 48, "low": 120},
    },
}

CATEGORY_CHOICES = list(DEPARTMENTS.keys())

URGENCY_CHOICES = ["low", "medium", "high"]

STATUS_CHOICES = ["open", "in_progress", "resolved", "breached"]

LOCATION_REQUIRED_CATEGORIES = [
    "Water Supply",
    "Electricity",
    "Roads & Potholes",
    "Garbage & Sanitation",
    "Streetlights",
    "Drainage & Sewage",
    "Illegal Construction",
]

TICKET_SCHEMA_FIELDS = [
    "ticket_id",
    "raw_text",
    "category",
    "department",
    "urgency",
    "sla_hours",
    "sla_deadline",
    "status",
    "breached",
    "location",
    "missing_fields",
    "clarification_question",
    "citizen_response_message",
    "created_at",
    "escalation_action",
]
