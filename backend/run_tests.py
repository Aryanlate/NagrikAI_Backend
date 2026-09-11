import os
import sys
import json
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = BACKEND_DIR
sys.path.insert(0, BACKEND_DIR)

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is not installed. Run: pip install requests")
    print("(It is already listed in requirements.txt — pip install -r requirements.txt)")
    sys.exit(2)

from constants import DEPARTMENTS, CATEGORY_CHOICES, TICKET_SCHEMA_FIELDS, URGENCY_CHOICES, STATUS_CHOICES

BASE_URL = "http://localhost:8000"

PASS_MARK = "\u2705"
FAIL_MARK = "\u274c"

REQUIRED_RESPONSE_FIELDS = [
    "raw_text",
    "category",
    "department",
    "urgency",
    "sla_hours",
    "sla_deadline",
    "status",
    "breached",
    "missing_fields",
    "clarification_question",
    "citizen_response_message",
    "created_at",
]


class TestResult:
    def __init__(self, name: str, passed: bool, detail: str = ""):
        self.name = name
        self.passed = passed
        self.detail = detail

    def line(self) -> str:
        prefix = PASS_MARK if self.passed else FAIL_MARK
        tail = f" — {self.detail}" if self.detail else ""
        return f"{prefix} {self.name}{tail}"


_results: List[TestResult] = []


def record(name: str, passed: bool, detail: str = "") -> bool:
    _results.append(TestResult(name, passed, detail))
    return passed


def section(title: str) -> None:
    print()
    sep = "=" * max(60, len(title) + 8)
    print(sep)
    print(f"  {title}")
    print(sep)


def truncate(text: str, n: int = 50) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= n:
        return text
    return text[: n - 3] + "..."


def _safe_get(url: str, **kwargs: Any) -> Optional[requests.Response]:
    try:
        return requests.get(url, timeout=15, **kwargs)
    except Exception as e:
        return None


def _safe_post(url: str, json_body: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Optional[requests.Response]:
    try:
        return requests.post(url, json=json_body, timeout=20, **kwargs)
    except Exception as e:
        return None


def _ensure_test_complaints_file() -> str:
    path = os.path.join(BACKEND_DIR, "test_complaints.json")
    if os.path.exists(path):
        return path

    backup = [
        {"id": 1, "tag": "simple_clear", "text": "Water pipe burst outside 14, Park Avenue, Sector 3. Water gushing out since morning and the road is flooded. Please send someone urgently."},
        {"id": 2, "tag": "simple_clear", "text": "The streetlight at the corner of 5th Main and 3rd Cross in Indiranagar is not working. It has been dark for two days."},
        {"id": 3, "tag": "simple_clear", "text": "There is a big pothole on the outer ring road service lane near Marathahalli bridge. Two bikers fell today."},
        {"id": 4, "tag": "simple_clear", "text": "Garbage bin opposite Shankar Mutt, Basavanagudi hasn't been emptied in 3 days. Flies and stench everywhere."},
        {"id": 5, "tag": "simple_clear", "text": "Someone is building an extra floor without permission on plot 42, sector 6. Construction going on at night too."},
        {"id": 6, "tag": "missing_info", "text": "no water supply for three days"},
        {"id": 7, "tag": "missing_info", "text": "Power cut since yesterday evening. Very frustrating in this heat."},
        {"id": 8, "tag": "missing_info", "text": "The sewage is overflowing and it's unbearable. Someone please help."},
        {"id": 9, "tag": "missing_info", "text": "There's a street light issue in my area."},
        {"id": 10, "tag": "missing_info", "text": "Stray dogs are creating a nuisance. Kids are scared to go out."},
        {"id": 11, "tag": "multi_issue", "text": "Sector 15 is a total mess. The main road has huge potholes, garbage hasn't been picked up all week, and the street lights don't work after dusk. Someone fell into a puddle last night because it was dark."},
        {"id": 12, "tag": "multi_issue", "text": "Near the railway station, there is water logging from an open drainage line, plus loud music from a nearby bar till 3am every night. We can't sleep and there are mosquitoes everywhere. An old man slipped and got hurt yesterday."},
        {"id": 13, "tag": "multi_issue", "text": "Ward 8 community park: the lights are broken, benches are broken, the water tap for plants is leaking and flooding the walkway, and local boys play extremely loud speakers every evening troubling senior citizens."},
        {"id": 14, "tag": "sarcastic_vague", "text": "Oh wow, another morning commute where I get to practice my off-roading skills on the 'road' outside my house. Excellent work, keep it up."},
        {"id": 15, "tag": "sarcastic_vague", "text": "Just wanted to say thank you for the free 24/7 private disco next door with the loud DJ. We didn't need to sleep anyway. The kids love doing homework to EDM beats at 2am."},
        {"id": 16, "tag": "sarcastic_vague", "text": "Is the garbage van on a holiday or is the bin a permanent decorative feature now? My apartment entrance looks beautiful with the mountain of trash."},
        {"id": 17, "tag": "repeat_escalation", "text": "This is the THIRD TIME I am complaining. The electric pole outside plot 7, MG Road is sparking and black smoke was coming yesterday. Your team came once, said it's fixed, and it started sparking again today. Someone is going to get electrocuted. DO SOMETHING NOW."},
        {"id": 18, "tag": "repeat_escalation", "text": "I have already registered two complaints about the drainage overflow behind 22, Nehru Nagar. It's been over a week and nobody has come. My children are falling sick. If nobody comes today I will go to the media and the corporator's office."},
        {"id": 19, "tag": "edge_case", "text": "Buy cheap watches at 70% off! Limited time offer, visit our website watchdeal.example"},
        {"id": 20, "tag": "edge_case", "text": "asdf qwerty 12345"},
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"meta": {"description": "generated fallback"}, "complaints": backup}, f, indent=2, ensure_ascii=False)
    return path


def _ensure_seed_script() -> bool:
    seed_path = os.path.join(BACKEND_DIR, "seed_demo_data.py")
    if os.path.exists(seed_path):
        return True
    return False


# ---------------------------------------------------------------------------
# 1. Health check
# ---------------------------------------------------------------------------
def test_health() -> bool:
    section("1. HEALTH CHECK")
    resp = _safe_get(f"{BASE_URL}/")
    if resp is None:
        print(f"{FAIL_MARK} Backend not reachable at localhost:8000 — start it with: uvicorn main:app --reload --port 8000")
        print()
        print("Cannot proceed — all subsequent tests require a running server.")
        sys.exit(1)
    ok = resp.status_code == 200
    body_ok = False
    try:
        body = resp.json()
        body_ok = body.get("status") == "ok"
    except Exception:
        body = resp.text
    passed = record("GET / returns 200", ok, f"status={resp.status_code}")
    passed2 = record('GET / body {"status":"ok"}', body_ok, f"body={truncate(str(body), 80)}")
    return passed and passed2


# ---------------------------------------------------------------------------
# 2. Docs check
# ---------------------------------------------------------------------------
def test_docs() -> bool:
    section("2. DOCS CHECK")
    resp = _safe_get(f"{BASE_URL}/docs")
    ok = resp is not None and resp.status_code == 200
    detail = f"status={resp.status_code if resp else 'connection failed'}"
    return record("GET /docs returns 200", ok, detail)


# ---------------------------------------------------------------------------
# 3. Analyze test — all 20 complaints
# ---------------------------------------------------------------------------
def validate_ticket_schema(body: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in REQUIRED_RESPONSE_FIELDS:
        if field not in body:
            errors.append(f"missing field '{field}'")
    if "category" in body and body["category"] not in CATEGORY_CHOICES:
        errors.append(f"category '{body.get('category')}' not in fixed list")
    if "urgency" in body and body["urgency"] not in URGENCY_CHOICES:
        errors.append(f"urgency '{body.get('urgency')}' invalid")
    if "status" in body and body["status"] not in STATUS_CHOICES:
        errors.append(f"status '{body.get('status')}' invalid")
    if "sla_hours" in body:
        if not isinstance(body["sla_hours"], int) or body["sla_hours"] <= 0:
            errors.append("sla_hours must be positive integer")
    if "missing_fields" in body:
        mf = body["missing_fields"]
        if not isinstance(mf, list):
            errors.append("missing_fields must be a list")
        elif len(mf) > 0:
            cq = body.get("clarification_question")
            if not isinstance(cq, str) or len(cq.strip()) == 0:
                errors.append("missing_fields non-empty but clarification_question is blank")
    return errors


def test_analyze_all() -> Tuple[int, int]:
    section("3. ANALYZE TEST (all 20 complaints)")
    path = _ensure_test_complaints_file()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    complaints = data.get("complaints", [])
    total = 0
    passed = 0
    for c in complaints:
        total += 1
        cid = c.get("id", "?")
        tag = c.get("tag", "")
        text = c.get("text", "")
        label = f"[#{cid:>2} {tag:<16}] {truncate(text, 50)}"
        resp = _safe_post(f"{BASE_URL}/api/analyze", json_body={"text": text})
        if resp is None:
            detail = "connection/request exception"
            record(label, False, detail)
            continue
        if resp.status_code != 200:
            detail = f"HTTP {resp.status_code} {truncate(resp.text, 60)}"
            record(label, False, detail)
            continue
        try:
            body = resp.json()
        except Exception as e:
            record(label, False, f"bad JSON body: {e}")
            continue

        errors = validate_ticket_schema(body)
        cat = body.get("category", "?")
        urg = body.get("urgency", "?")
        mf = body.get("missing_fields", [])
        note = f"cat={cat} | urg={urg} | missing={mf}"
        ok = len(errors) == 0
        if not ok:
            note = note + " | ERRORS: " + "; ".join(errors[:3])
        if record(label, ok, note):
            passed += 1
    print(f"  (Subtotal: {passed}/{total} individual complaint checks passed)")
    return passed, total


# ---------------------------------------------------------------------------
# 4. Clarify loop test
# ---------------------------------------------------------------------------
def test_clarify_loop() -> Dict[str, Any]:
    section("4. CLARIFY LOOP TEST (water supply example)")
    original = "no water supply for three days"
    reply = "Koregaon Park, Pune"

    ctx: Dict[str, Any] = {"clarify_ok": False, "ticket_id": None}

    # Step A: analyze, expect missing_fields and clarification_question
    resp_a = _safe_post(f"{BASE_URL}/api/analyze", json_body={"text": original})
    a_ok = resp_a is not None and resp_a.status_code == 200
    try:
        body_a = resp_a.json() if a_ok else {}
    except Exception:
        body_a = {}

    cq = body_a.get("clarification_question") if isinstance(body_a, dict) else None
    mf = body_a.get("missing_fields") if isinstance(body_a, dict) else []
    a_has_cq = isinstance(cq, str) and len(cq.strip()) > 0 and isinstance(mf, list) and len(mf) > 0
    step_a = record(
        "POST /api/analyze returns clarification_question + missing_fields",
        a_ok and a_has_cq,
        (f"HTTP {resp_a.status_code if resp_a else 'fail'} | cq={'set' if cq else 'empty/null'} | missing={mf}"),
    )

    # Step B: clarify
    resp_b = _safe_post(
        f"{BASE_URL}/api/clarify",
        json_body={"original_text": original, "reply": reply},
    )
    b_ok = resp_b is not None and resp_b.status_code == 200
    try:
        body_b = resp_b.json() if b_ok else {}
    except Exception:
        body_b = {}

    tid = body_b.get("ticket_id") if isinstance(body_b, dict) else None
    mf_b = body_b.get("missing_fields") if isinstance(body_b, dict) else None
    msg = body_b.get("citizen_response_message") if isinstance(body_b, dict) else None

    checks_b = [
        b_ok,
        isinstance(tid, str) and len(tid.strip()) > 0,
        isinstance(mf_b, list) and len(mf_b) == 0,
        isinstance(msg, str) and len(msg.strip()) > 0,
    ]
    detail = (
        f"HTTP {resp_b.status_code if resp_b else 'fail'} | ticket_id={tid} | "
        f"missing={mf_b} | response_msg={'set' if (isinstance(msg, str) and msg.strip()) else 'empty/null'}"
    )
    step_b = record(
        "POST /api/clarify returns ticket_id, empty missing_fields, citizen_response_message",
        all(checks_b),
        detail,
    )

    ctx["clarify_ok"] = step_a and step_b
    ctx["ticket_id"] = tid
    ctx["original_text"] = original
    ctx["reply"] = reply
    return ctx


# ---------------------------------------------------------------------------
# 5. Persistence test
# ---------------------------------------------------------------------------
def test_persistence(ticket_id: Optional[str]) -> bool:
    section("5. PERSISTENCE TEST (ticket from clarify loop appears in /api/tickets)")
    if not ticket_id:
        return record("Clarify-loop ticket present in GET /api/tickets", False, "no ticket_id from step 4")
    resp = _safe_get(f"{BASE_URL}/api/tickets")
    if resp is None or resp.status_code != 200:
        return record(
            "Clarify-loop ticket present in GET /api/tickets",
            False,
            f"GET /api/tickets HTTP {resp.status_code if resp else 'fail'}",
        )
    try:
        body = resp.json()
    except Exception as e:
        return record("Clarify-loop ticket present in GET /api/tickets", False, f"bad JSON: {e}")
    tickets = body.get("tickets", []) if isinstance(body, dict) else []
    ids = [t.get("ticket_id") for t in tickets if isinstance(t, dict)]
    present = ticket_id in ids
    return record(
        "Clarify-loop ticket present in GET /api/tickets",
        present,
        f"looking for {ticket_id} | returned {len(tickets)} tickets",
    )


# ---------------------------------------------------------------------------
# 6. Stats test
# ---------------------------------------------------------------------------
def test_stats() -> bool:
    section("6. STATS TEST (/api/stats returns non-empty dicts)")
    resp = _safe_get(f"{BASE_URL}/api/stats")
    if resp is None or resp.status_code != 200:
        return record("GET /api/stats 200 OK", False, f"HTTP {resp.status_code if resp else 'fail'}")
    try:
        body = resp.json()
    except Exception as e:
        return record("GET /api/stats 200 OK", False, f"bad JSON: {e}")
    by_cat = body.get("by_category") if isinstance(body, dict) else None
    by_dept = body.get("by_department") if isinstance(body, dict) else None
    cat_ok = isinstance(by_cat, dict) and len(by_cat) > 0
    dept_ok = isinstance(by_dept, dict) and len(by_dept) > 0
    detail = f"by_category keys={len(by_cat) if isinstance(by_cat, dict) else 'bad'} | by_department keys={len(by_dept) if isinstance(by_dept, dict) else 'bad'}"
    return record("GET /api/stats returns non-empty by_category + by_department", cat_ok and dept_ok, detail)


# ---------------------------------------------------------------------------
# 7. Seed + breach test
# ---------------------------------------------------------------------------
def _run_seed_script() -> Tuple[bool, str]:
    seed_path = os.path.join(BACKEND_DIR, "seed_demo_data.py")
    if not os.path.exists(seed_path):
        return False, "seed_demo_data.py not found"
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = BACKEND_DIR + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable, seed_path],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        ok = result.returncode == 0
        detail = truncate((result.stdout + result.stderr).strip(), 200) or "(no output)"
        return ok, detail
    except Exception as e:
        return False, f"subprocess failed: {type(e).__name__}: {e}"


def test_seed_and_breach() -> bool:
    section("7. SEED + BREACH TEST")

    if not _ensure_seed_script():
        return record("Run seed_demo_data.py", False, "seed script missing")

    seed_ok, seed_detail = _run_seed_script()
    record("Run seed_demo_data.py", seed_ok, seed_detail)

    resp = _safe_get(f"{BASE_URL}/api/tickets")
    tickets: List[Dict[str, Any]] = []
    if resp is not None and resp.status_code == 200:
        try:
            body = resp.json()
            tickets = body.get("tickets", []) if isinstance(body, dict) else []
        except Exception:
            tickets = []

    breached_with_esc = [
        t for t in tickets
        if isinstance(t, dict)
        and t.get("status") == "breached"
        and t.get("breached") is True
        and isinstance(t.get("escalation_action"), str)
        and t["escalation_action"].strip()
    ]
    step_b = record(
        "At least 1 breached ticket with non-null escalation_action in /api/tickets",
        len(breached_with_esc) >= 1,
        f"found {len(breached_with_esc)} | total tickets={len(tickets)}",
    )

    resp_c = _safe_post(f"{BASE_URL}/api/check-breaches", json_body={})
    step_c_ok = resp_c is not None and resp_c.status_code == 200
    try:
        body_c = resp_c.json() if step_c_ok else {}
        n = len(body_c.get("tickets", [])) if isinstance(body_c, dict) else "?"
    except Exception:
        n = "bad JSON"
    step_c = record(
        "POST /api/check-breaches returns 200",
        step_c_ok,
        f"HTTP {resp_c.status_code if resp_c else 'fail'} | breached_count={n}",
    )

    return seed_ok and step_b and step_c


# ---------------------------------------------------------------------------
# 8. CORS check
# ---------------------------------------------------------------------------
def test_cors() -> bool:
    section("8. CORS CHECK (simulate frontend origin)")
    origin = "http://localhost:5173"
    resp = _safe_get(f"{BASE_URL}/api/tickets", headers={"Origin": origin})
    if resp is None:
        return record("GET /api/tickets with Origin header returns Access-Control-Allow-Origin", False, "connection failed")
    acao = resp.headers.get("Access-Control-Allow-Origin")
    detail = f"Origin={origin} | ACAO header={acao!r}"
    ok = acao in ("*", origin)
    return record(
        "GET /api/tickets with Origin header returns Access-Control-Allow-Origin",
        ok,
        detail,
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def print_summary_and_exit() -> None:
    section("TEST SUMMARY")
    total = len(_results)
    passed = sum(1 for r in _results if r.passed)
    fails = [r for r in _results if not r.passed]

    for r in _results:
        print(r.line())

    print()
    print(f"{passed}/{total} checks passed")
    if fails:
        print()
        print("Failures:")
        for r in fails:
            reason = r.detail or "no detail"
            print(f"  - {r.name}: {reason}")
        sys.exit(1)
    else:
        print("All checks passed!")
        sys.exit(0)


def main() -> None:
    print("NagrikAI Backend Test Suite")
    print(f"Target: {BASE_URL}")
    print(f"Started: {datetime.now().isoformat(timespec='seconds')}")

    test_health()
    test_docs()
    test_analyze_all()
    ctx = test_clarify_loop()
    test_persistence(ctx.get("ticket_id"))
    test_stats()
    test_seed_and_breach()
    test_cors()

    print_summary_and_exit()


if __name__ == "__main__":
    main()
