import os
import json
import re
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from constants import DEPARTMENTS, CATEGORY_CHOICES, LOCATION_REQUIRED_CATEGORIES

logger = logging.getLogger(__name__)

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

_model = None
_genai = None
_genai_available = False

try:
    try:
        import google.genai as genai_new
        _genai = genai_new
        _genai_available = True
        if GOOGLE_API_KEY:
            try:
                client = _genai.Client(api_key=GOOGLE_API_KEY)
                _model = client.models.GenerativeModel(GEMINI_MODEL)
            except Exception:
                _model = None
    except ImportError:
        import google.generativeai as genai_legacy
        _genai = genai_legacy
        _genai_available = True
        if GOOGLE_API_KEY:
            try:
                _genai.configure(api_key=GOOGLE_API_KEY)
                _model = _genai.GenerativeModel(GEMINI_MODEL)
            except Exception:
                _model = None
except ImportError:
    _genai = None
    _genai_available = False


def _is_legacy_sdk() -> bool:
    return _genai is not None and hasattr(_genai, "configure")


CATEGORIES_LIST = "\n".join([f"- {c}" for c in CATEGORY_CHOICES])

SYSTEM_PROMPT_EXTRACT = f"""You are an AI assistant for a municipal citizen complaint triage system.
Your job is to analyze complaint text and return STRICTLY VALID JSON with exactly the schema specified below.
DO NOT include any preamble, explanations, markdown fences, or extra text — ONLY the JSON object.

CATEGORIES (you MUST pick exactly ONE, fall back to "Other" if truly unclear):
{CATEGORIES_LIST}

Rules for classification and extraction:
1. category: Pick the single best matching category from the list above. If a complaint has multiple issues, pick the MOST URGENT one as the primary category.
2. urgency: "low" | "medium" | "high". Bump UP to higher urgency if:
   - Safety risk (electrical spark, gas leak, falling debris, violence, fire hazard)
   - Duration >= 3 days mentioned ("three days", "since Monday", "for a week")
   - Escalation language ("this is unacceptable", "nobody is responding", "I've complained before", "third time")
   - Vulnerable people mentioned (elderly, children, sick, disabled)
   - Infrastructure failure that blocks essential services
   Otherwise, use medium for standard complaints, low for minor/non-urgent.
3. location: Extract address, area name, landmark, street, sector, ward, pincode if mentioned. If NO location is mentioned, use null.
4. missing_fields: Array of required field names that are missing. For categories in LOCATION_REQUIRED_CATEGORIES, location is mandatory. If the category requires a location and none was provided, include "location" in missing_fields. If all required fields are present, return empty array [].
5. clarification_question: If missing_fields is non-empty, write a SHORT, polite, specific natural-language question asking for the missing info. Example: "Could you please share the exact address or area where the water supply is cut off?" If missing_fields is empty, use null.

Final output MUST be valid JSON matching this exact schema (no ticket_id, no DB-only fields — those are added later):
{{
  "category": "string",
  "department": "string",
  "urgency": "low|medium|high",
  "location": "string or null",
  "missing_fields": ["field1"],
  "clarification_question": "string or null",
  "secondary_issue": "string or null"
}}

Tone handling: If the complaint is sarcastic or vague, infer the REAL underlying problem rather than taking words literally.
If the text is complete nonsense or non-civic (e.g. marketing spam, gibberish), use category="Other", urgency="medium", and ask for clarification.
"""

SYSTEM_PROMPT_CLARIFY = f"""You are an AI assistant for a municipal citizen complaint triage system.
This is a FOLLOW-UP CLARIFICATION step. The citizen previously submitted a complaint that was missing required fields.
The citizen has now replied with the additional information you asked for.

Your job is to analyze the MERGED text (original complaint + citizen's clarification reply) and return STRICTLY VALID JSON with exactly the schema specified below.
DO NOT include any preamble, explanations, markdown fences, or extra text — ONLY the JSON object.

IMPORTANT INSTRUCTIONS FOR THIS FOLLOW-UP:
- You MUST extract information from BOTH the "Original complaint" section AND the "Additional info from citizen reply" section.
- The citizen's reply section contains the answers to your earlier clarification questions — treat these answers as FACTUAL DATA that fills previously-missing fields.
- For example, if the citizen's reply says "Koregaon Park, Pune", that is the LOCATION for the complaint — extract it into the "location" field.
- Re-evaluate ALL required fields from scratch using the COMBINED information. Do NOT treat any fields as "still missing" if the combined text now provides them.

CATEGORIES (you MUST pick exactly ONE, fall back to "Other" if truly unclear):
{CATEGORIES_LIST}

Rules for classification and extraction:
1. category: Pick the single best matching category from the list above. If a complaint has multiple issues, pick the MOST URGENT one as the primary category.
2. urgency: "low" | "medium" | "high". Bump UP to higher urgency if:
   - Safety risk (electrical spark, gas leak, falling debris, violence, fire hazard)
   - Duration >= 3 days mentioned ("three days", "since Monday", "for a week")
   - Escalation language ("this is unacceptable", "nobody is responding", "I've complained before", "third time")
   - Vulnerable people mentioned (elderly, children, sick, disabled)
   - Infrastructure failure that blocks essential services
   Otherwise, use medium for standard complaints, low for minor/non-urgent.
3. location: Extract address, area name, landmark, street, sector, ward, pincode IF MENTIONED ANYWHERE in the merged text (original complaint OR citizen reply). If NO location is mentioned anywhere, use null.
4. missing_fields: Array of required field names that are STILL missing after evaluating the ENTIRE merged text. For categories in LOCATION_REQUIRED_CATEGORIES, location is mandatory. If the category requires a location and NONE was provided in EITHER section, include "location" in missing_fields. If all required fields are now present from the merged text, return empty array [].
5. clarification_question: If missing_fields is STILL non-empty after checking merged text, write a SHORT, polite, specific natural-language question asking for the still-missing info. If missing_fields is empty, use null.

Final output MUST be valid JSON matching this exact schema (no ticket_id, no DB-only fields — those are added later):
{{
  "category": "string",
  "department": "string",
  "urgency": "low|medium|high",
  "location": "string or null",
  "missing_fields": ["field1"],
  "clarification_question": "string or null",
  "secondary_issue": "string or null"
}}

Tone handling: If the complaint is sarcastic or vague, infer the REAL underlying problem rather than taking words literally.
If the text is complete nonsense or non-civic (e.g. marketing spam, gibberish), use category="Other", urgency="medium", and ask for clarification.
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _find_json_object(text: str) -> Optional[Dict[str, Any]]:
    start = text.find("{")
    if start == -1:
        return None
    end = text.rfind("}")
    if end == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _fallback_extract(raw_text: str, reason: str = "") -> Dict[str, Any]:
    return {
        "category": "Other",
        "department": DEPARTMENTS["Other"]["department"],
        "urgency": "medium",
        "location": None,
        "missing_fields": ["location"],
        "clarification_question": "To help us route your complaint correctly, could you please share the location and a brief description of the issue?",
        "secondary_issue": None,
        "_fallback_reason": reason,
    }


def _normalize_extract_result(parsed: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    category = parsed.get("category", "Other")
    if category not in DEPARTMENTS:
        category = "Other"

    department = parsed.get("department")
    valid_depts = [v["department"] for v in DEPARTMENTS.values()]
    if not department or department not in valid_depts:
        department = DEPARTMENTS[category]["department"]

    urgency = parsed.get("urgency", "medium")
    if urgency not in ("low", "medium", "high"):
        urgency = "medium"

    location = parsed.get("location")
    if isinstance(location, str):
        location = location.strip()
        if location.lower() in ("", "null", "none", "n/a", "unknown"):
            location = None
    else:
        location = None

    missing_fields = parsed.get("missing_fields", [])
    if not isinstance(missing_fields, list):
        missing_fields = []
    missing_fields = [str(f).strip() for f in missing_fields if str(f).strip()]

    if category in LOCATION_REQUIRED_CATEGORIES and location is None and "location" not in missing_fields:
        missing_fields.append("location")

    clarification_question = parsed.get("clarification_question")
    if not isinstance(clarification_question, str):
        clarification_question = None
    if missing_fields and not clarification_question:
        if "location" in missing_fields:
            clarification_question = (
                "Could you please share the exact location (address, area, or landmark) "
                "for this complaint so we can route it to the correct team?"
            )
        else:
            clarification_question = (
                "Could you please provide a bit more detail so we can assist you better?"
            )
    if not missing_fields:
        clarification_question = None

    secondary_issue = parsed.get("secondary_issue")
    if not isinstance(secondary_issue, str):
        secondary_issue = None

    return {
        "category": category,
        "department": department,
        "urgency": urgency,
        "location": location,
        "missing_fields": missing_fields,
        "clarification_question": clarification_question,
        "secondary_issue": secondary_issue,
    }


def _call_gemini_json(system_prompt: str, user_text: str, max_retries: int = 1) -> Dict[str, Any]:
    if not _genai_available or _model is None:
        return _fallback_extract(user_text, reason="google-genai not available or API key not set")

    attempt = 0
    last_error = ""
    full_prompt = f"{system_prompt}\n\nComplaint text:\n{user_text}"

    while attempt <= max_retries:
        attempt += 1
        try:
            legacy = _is_legacy_sdk()
            if legacy:
                if hasattr(_genai, "types"):
                    cfg = _genai.types.GenerationConfig(
                        temperature=0.1,
                        response_mime_type="application/json",
                        max_output_tokens=1024,
                    )
                else:
                    cfg = {
                        "temperature": 0.1,
                        "response_mime_type": "application/json",
                        "max_output_tokens": 1024,
                    }
                response = _model.generate_content(full_prompt, generation_config=cfg)
            else:
                cfg = _genai.types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                    max_output_tokens=1024,
                )
                response = _model.generate_content(full_prompt, config=cfg)
            raw_answer = ""
            if hasattr(response, "text"):
                raw_answer = response.text or ""
            elif hasattr(response, "parts"):
                for part in response.parts or []:
                    if hasattr(part, "text"):
                        raw_answer += part.text or ""
            cleaned = _strip_fences(raw_answer)
            parsed = _find_json_object(cleaned)
            if parsed is None:
                try:
                    parsed = json.loads(cleaned)
                except json.JSONDecodeError:
                    last_error = f"could not parse JSON response (attempt {attempt})"
                    continue
            return _normalize_extract_result(parsed, user_text)
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            continue

    return _fallback_extract(user_text, reason=last_error or "unknown gemini error")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _derive_sla_fields(category: str, urgency: str, created_at_iso: str) -> Dict[str, Any]:
    dept_info = DEPARTMENTS.get(category, DEPARTMENTS["Other"])
    sla_hours = dept_info["default_sla_hours"].get(urgency, dept_info["default_sla_hours"]["medium"])
    try:
        created = datetime.fromisoformat(created_at_iso)
    except ValueError:
        created = datetime.now(timezone.utc).replace(tzinfo=None)
    deadline = created + timedelta(hours=sla_hours)
    return {
        "sla_hours": sla_hours,
        "sla_deadline": deadline.isoformat(),
    }


def extract_ticket(text: str) -> Dict[str, Any]:
    raw_text = (text or "").strip()
    if not raw_text:
        parsed = _fallback_extract("", reason="empty input text")
    else:
        parsed = _call_gemini_json(SYSTEM_PROMPT_EXTRACT, raw_text)

    created_at = _utcnow_iso()
    sla = _derive_sla_fields(parsed["category"], parsed["urgency"], created_at)

    is_complete = len(parsed.get("missing_fields", [])) == 0

    ticket = {
        "ticket_id": None,
        "raw_text": raw_text,
        "category": parsed["category"],
        "department": parsed["department"],
        "urgency": parsed["urgency"],
        "sla_hours": sla["sla_hours"],
        "sla_deadline": sla["sla_deadline"],
        "status": "open",
        "breached": False,
        "location": parsed["location"],
        "missing_fields": parsed["missing_fields"],
        "clarification_question": parsed["clarification_question"],
        "citizen_response_message": None,
        "created_at": created_at,
        "escalation_action": None,
    }

    if is_complete:
        ticket["citizen_response_message"] = generate_citizen_response(ticket)

    return ticket


def clarify_ticket(original_text: str, reply: str) -> Dict[str, Any]:
    combined_text = (
        f"Original complaint: {original_text.strip()}\n"
        f"Additional info from citizen reply: {(reply or '').strip()}"
    )
    logger.info(f"Combined text for clarify: {combined_text}")

    raw_text = combined_text.strip()
    if not raw_text:
        parsed = _fallback_extract("", reason="empty input text")
    else:
        parsed = _call_gemini_json(SYSTEM_PROMPT_CLARIFY, raw_text)

    created_at = _utcnow_iso()
    sla = _derive_sla_fields(parsed["category"], parsed["urgency"], created_at)

    is_complete = len(parsed.get("missing_fields", [])) == 0

    ticket = {
        "ticket_id": None,
        "raw_text": raw_text,
        "category": parsed["category"],
        "department": parsed["department"],
        "urgency": parsed["urgency"],
        "sla_hours": sla["sla_hours"],
        "sla_deadline": sla["sla_deadline"],
        "status": "open",
        "breached": False,
        "location": parsed["location"],
        "missing_fields": parsed["missing_fields"],
        "clarification_question": parsed["clarification_question"],
        "citizen_response_message": None,
        "created_at": created_at,
        "escalation_action": None,
    }

    if is_complete:
        ticket["citizen_response_message"] = generate_citizen_response(ticket)

    return ticket


SYSTEM_PROMPT_RESPONSE = """You are a polite, concise civic customer-service bot for a municipal government.
Given a ticket JSON, write a short (1-3 sentence) friendly confirmation message in plain language.
Include:
- The ticket ID (if present, otherwise omit it gracefully)
- Which department the complaint has been routed to
- The expected response timeframe in plain language (e.g. "within 4 hours", "within 1 business day")
- Reassurance that the team is on it.

Do NOT use markdown. Do NOT output JSON. Just the plain text message.
"""


def generate_citizen_response(ticket: Dict[str, Any]) -> str:
    sla_hours = ticket.get("sla_hours", 24)
    dept = ticket.get("department", "the concerned department")
    ticket_id = ticket.get("ticket_id")

    if sla_hours <= 4:
        timeframe = "within a few hours"
    elif sla_hours <= 12:
        timeframe = "within the same day"
    elif sla_hours <= 24:
        timeframe = "within 24 hours"
    elif sla_hours <= 72:
        timeframe = "within 2-3 business days"
    else:
        timeframe = "as soon as capacity allows"

    id_line = f" (Reference: {ticket_id})" if ticket_id else ""
    base = (
        f"Thank you for reaching out{id_line}. Your complaint has been registered with the {dept}. "
        f"A team member will follow up with you {timeframe}. "
        f"We appreciate your patience as we work to resolve this."
    )

    if not _genai_available or _model is None:
        return base

    try:
        ticket_json = json.dumps(ticket, indent=2, default=str)
        full_prompt = f"{SYSTEM_PROMPT_RESPONSE}\n\nTicket JSON:\n{ticket_json}"
        legacy = _is_legacy_sdk()
        if legacy:
            cfg = {
                "temperature": 0.3,
                "max_output_tokens": 300,
            }
            if hasattr(_genai, "types"):
                cfg = _genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=300,
                )
            response = _model.generate_content(full_prompt, generation_config=cfg)
        else:
            cfg = _genai.types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=300,
            )
            response = _model.generate_content(full_prompt, config=cfg)
        message_text = ""
        if hasattr(response, "text"):
            message_text = (response.text or "").strip()
        elif hasattr(response, "parts"):
            for part in response.parts or []:
                if hasattr(part, "text"):
                    message_text += (part.text or "")
            message_text = message_text.strip()
        if message_text:
            return message_text
    except Exception:
        pass

    return base
