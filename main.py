import os
from datetime import datetime, timedelta
from typing import Optional, List, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents

app = FastAPI(title="HealthLab API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========= Models for requests =========
class ChatMessage(BaseModel):
    user_id: Optional[str] = None
    text: str
    intent: Optional[str] = None  # optional client-supplied intent
    payload: Optional[dict] = None  # e.g., {test_code, scheduled_at, address}


class CreateTest(BaseModel):
    name: str
    code: str
    category: Optional[str] = "General"
    price: float
    description: Optional[str] = None
    preparation: Optional[str] = None


class CreateBooking(BaseModel):
    user_id: str
    test_code: str
    scheduled_at: datetime
    address: Optional[str] = None
    promo_code: Optional[str] = None


class UpdateBooking(BaseModel):
    scheduled_at: Optional[datetime] = None
    status: Optional[Literal["booked", "in_progress", "completed", "cancelled"]] = None
    address: Optional[str] = None


class ApplyPromo(BaseModel):
    code: str
    price: float


class ViewReport(BaseModel):
    booking_id: str
    pin: str


# ========= Utility =========
SYMPTOM_TO_TESTS = {
    "dizzy": ["CBC", "IRON"],
    "fever": ["CBC", "CRP"],
    "fatigue": ["IRON", "B12"],
    "jaundice": ["LFT"],
    "diabetes": ["FBS", "HBA1C"],
}

DEFAULT_TESTS = [
    {"name": "Complete Blood Count", "code": "CBC", "category": "Hematology", "price": 20.0,
     "preparation": "No fasting required"},
    {"name": "Iron Studies", "code": "IRON", "category": "Hematology", "price": 25.0,
     "preparation": "8-10 hours fasting preferred"},
    {"name": "Liver Function Test", "code": "LFT", "category": "Biochemistry", "price": 30.0,
     "preparation": "No alcohol 24h before"},
    {"name": "C-Reactive Protein", "code": "CRP", "category": "Biochemistry", "price": 22.0,
     "preparation": "No special preparation"},
    {"name": "Vitamin B12", "code": "B12", "category": "Vitamins", "price": 28.0,
     "preparation": "Fasting 6-8 hours"},
    {"name": "Fasting Blood Sugar", "code": "FBS", "category": "Diabetes", "price": 12.0,
     "preparation": "Overnight fasting"},
    {"name": "HbA1c", "code": "HBA1C", "category": "Diabetes", "price": 18.0,
     "preparation": "No fasting required"},
]


def ensure_seed_tests():
    if db is None:
        return
    if db["test"].count_documents({}) == 0:
        for t in DEFAULT_TESTS:
            create_document("test", t)


@app.get("/")
def read_root():
    return {"message": "HealthLab Backend is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Set"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# ========= Tests =========
@app.get("/api/tests")
def list_tests():
    ensure_seed_tests()
    items = get_documents("test") if db else DEFAULT_TESTS
    return {"items": items}


@app.post("/api/tests")
def create_test(payload: CreateTest):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    existing = db["test"].find_one({"code": payload.code})
    if existing:
        raise HTTPException(status_code=409, detail="Test code already exists")
    _id = create_document("test", payload.model_dump())
    return {"id": _id}


# ========= Bookings =========
@app.get("/api/bookings")
def list_bookings(user_id: Optional[str] = None):
    if db is None:
        return {"items": []}
    q = {"user_id": user_id} if user_id else {}
    items = get_documents("booking", q)
    return {"items": items}


@app.post("/api/bookings")
def create_booking(payload: CreateBooking):
    price = None
    if db is not None:
        t = db["test"].find_one({"code": payload.test_code})
        if not t:
            raise HTTPException(status_code=404, detail="Test not found")
        price = float(t.get("price", 0))
    booking_data = payload.model_dump()
    booking_data.update({
        "status": "booked",
        "payment_status": "pending",
        "price": price
    })
    booking_id = create_document("booking", booking_data)
    return {"id": booking_id, "message": "Booking created"}


@app.patch("/api/bookings/{booking_id}")
def update_booking(booking_id: str, payload: UpdateBooking):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    update["updated_at"] = datetime.utcnow()
    res = db["booking"].update_one({"_id": __import__('bson').ObjectId(booking_id)}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"message": "Updated"}


# ========= Promos =========
@app.post("/api/promos/apply")
def apply_promo(payload: ApplyPromo):
    code = payload.code.strip().upper()
    price = payload.price
    discount = 0.0
    message = ""
    if code == "NEWUSER10":
        discount = round(price * 0.10, 2)
        message = "New user 10% discount applied"
    elif code == "MEMBER5":
        discount = round(price * 0.05, 2)
        message = "Membership 5% discount applied"
    elif db is not None:
        promo = db["promo"].find_one({"code": code, "active": True})
        if promo:
            if promo.get("type") == "flat":
                discount = float(promo.get("value", 0))
            else:
                discount = round(price * float(promo.get("value", 0)) / 100.0, 2)
            message = promo.get("note", "Promo applied")
    total = max(price - discount, 0)
    return {"discount": discount, "total": total, "message": message or "No promo applied"}


# ========= Reports (PIN verification) =========
@app.post("/api/reports/view")
def view_report(payload: ViewReport):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    booking = db["booking"].find_one({"_id": __import__('bson').ObjectId(payload.booking_id)})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    user = db["user"].find_one({"_id": __import__('bson').ObjectId(booking["user_id"])}) if len(str(booking.get("user_id", ""))) == 24 else db["user"].find_one({"_id": booking.get("user_id")})
    if not user or str(user.get("pin")) != str(payload.pin):
        raise HTTPException(status_code=401, detail="Invalid PIN")
    report = db["report"].find_one({"booking_id": payload.booking_id})
    if not report:
        raise HTTPException(status_code=404, detail="Report not available yet")
    return {"report": report}


# ========= Chatbot =========
@app.post("/api/chat")
def chat(msg: ChatMessage):
    # Save user message to memory
    if db is not None and msg.user_id:
        create_document("message", {"user_id": msg.user_id, "role": "user", "text": msg.text})

    text = msg.text.lower()

    # intent: report access
    if "report" in text and ("view" in text or "show" in text):
        reply = {
            "type": "action_required",
            "action": "verify_pin",
            "message": "Please enter your 4-digit PIN to access your reports.",
        }
        _save_assistant(msg, reply)
        return reply

    # booking via structured payload
    if msg.intent == "book_test" and msg.payload:
        try:
            booking = CreateBooking(**{
                "user_id": msg.payload.get("user_id"),
                "test_code": msg.payload.get("test_code"),
                "scheduled_at": datetime.fromisoformat(msg.payload.get("scheduled_at")),
                "address": msg.payload.get("address")
            })
            result = create_booking(booking)
            reply = {
                "type": "booking_confirmed",
                "message": f"Your {booking.test_code} is booked for {booking.scheduled_at.strftime('%d %b %Y, %I:%M %p')}.",
                "booking_id": result["id"],
            }
            _save_assistant(msg, reply)
            return reply
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # symptom to test suggestions
    suggested = set()
    for symptom, tests in SYMPTOM_TO_TESTS.items():
        if symptom in text:
            suggested.update(tests)
    if not suggested and any(k in text for k in ["tired", "weak", "cold", "cough", "pain", "yellow", "sugar"]):
        # heuristics
        if any(k in text for k in ["tired", "weak"]):
            suggested.update(["CBC", "IRON", "B12"])
        if any(k in text for k in ["fever", "cold", "cough"]):
            suggested.update(["CBC", "CRP"])
        if "yellow" in text:
            suggested.add("LFT")
        if "sugar" in text:
            suggested.update(["FBS", "HBA1C"])

    if suggested:
        ensure_seed_tests()
        tests = list(db["test"].find({"code": {"$in": list(suggested)}})) if db else [t for t in DEFAULT_TESTS if t["code"] in suggested]
        reply = {
            "type": "suggestions",
            "message": "Here are some recommended tests based on your symptoms:",
            "tests": tests,
            "cta": "Would you like to book one of these?"
        }
        _save_assistant(msg, reply)
        return reply

    # default fallback
    reply = {
        "type": "text",
        "message": "I can help you book tests, suggest investigations from symptoms, apply promo codes, and fetch your reports securely. Try: 'I feel dizzy' or 'Book CBC tomorrow 10am'."
    }
    _save_assistant(msg, reply)
    return reply


def _save_assistant(msg: ChatMessage, reply: dict):
    if db is not None and msg.user_id:
        create_document("message", {"user_id": msg.user_id, "role": "assistant", "text": reply.get("message"), "context": reply})


# ========= Schema endpoint (for viewers/tools) =========
@app.get("/schema")
def get_schema():
    try:
        from schemas import User, Test, Booking, Report, Promo, Message
        return {
            "collections": [
                {"name": "user", "schema": User.model_json_schema()},
                {"name": "test", "schema": Test.model_json_schema()},
                {"name": "booking", "schema": Booking.model_json_schema()},
                {"name": "report", "schema": Report.model_json_schema()},
                {"name": "promo", "schema": Promo.model_json_schema()},
                {"name": "message", "schema": Message.model_json_schema()},
            ]
        }
    except Exception:
        return {"collections": []}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
