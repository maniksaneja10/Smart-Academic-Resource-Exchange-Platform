import csv
import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

app = FastAPI(title="Smart Academic Resource Exchange - Bennett University (Group 5)")

# Enable CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "resources.csv")
FIELDNAMES = [
    "item_id", "title", "course_code", "price",
    "condition", "hostel_block", "seller_contact", "status"
]
VALID_CONDITIONS = {"New", "Good", "Fair"}
VALID_HOSTELS = {"A", "B", "C", "D"}

# Adjacent hostel mapping for the 20-point proximity rule
ADJACENT_HOSTELS = {
    "A": {"B"},
    "B": {"A", "C"},
    "C": {"B", "D"},
    "D": {"C"},
}

# --- Pydantic Validation Models ---
class ResourceCreate(BaseModel):
    title: str = Field(..., min_length=2)
    course_code: str = Field(..., min_length=6)
    price: float = Field(..., ge=0)
    condition: str
    hostel_block: str
    seller_contact: str

    @field_validator("course_code")
    @classmethod
    def validate_course(cls, v: str) -> str:
        code = v.strip().upper()
        if len(code) < 6 or not code.isalnum():
            raise ValueError("Course code must be at least 6 alphanumeric characters (e.g., 2026CSAE100).")
        return code

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: str) -> str:
        val = v.strip().capitalize()
        if val not in VALID_CONDITIONS:
            raise ValueError(f"Condition must be one of {VALID_CONDITIONS}.")
        return val

    @field_validator("hostel_block")
    @classmethod
    def validate_hostel(cls, v: str) -> str:
        val = v.strip().upper()
        if val not in VALID_HOSTELS:
            raise ValueError(f"Hostel block must be one of {VALID_HOSTELS}.")
        return val

    @field_validator("seller_contact")
    @classmethod
    def validate_contact(cls, v: str) -> str:
        digits = v.strip()
        if not digits.isdigit() or len(digits) != 10:
            raise ValueError("Seller contact must be a valid 10-digit mobile number.")
        return digits


class StatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        val = v.strip().capitalize()
        if val not in {"Available", "Reserved"}:
            raise ValueError("Status must be 'Available' or 'Reserved'.")
        return val


class MatchRequest(BaseModel):
    target_course: str
    max_budget: float = Field(..., ge=0)
    buyer_hostel: str
    preferred_condition: Optional[str] = "Good"


# --- CSV Persistence Layer (Sub-Problem 1) ---
def seed_initial_data() -> List[dict]:
    """Pre-populate with the exact benchmark dataset from Milestone 2 Report if CSV doesn't exist."""
    return [
        {"item_id": "RES-101", "title": "Python Think Python 2e", "course_code": "2026CSAE100", "price": 450.0, "condition": "Good", "hostel_block": "C", "seller_contact": "9811045210", "status": "Available"},
        {"item_id": "RES-102", "title": "Computational Thinking Notes", "course_code": "2026CSAE100", "price": 250.0, "condition": "New", "hostel_block": "D", "seller_contact": "9871230984", "status": "Available"},
        {"item_id": "RES-103", "title": "Python Lab Workbook", "course_code": "2026CSAE100", "price": 550.0, "condition": "Fair", "hostel_block": "C", "seller_contact": "9811987654", "status": "Reserved"},
        {"item_id": "RES-104", "title": "Thomas Calculus 14th Ed", "course_code": "2026MASE101", "price": 350.0, "condition": "Good", "hostel_block": "B", "seller_contact": "9810011223", "status": "Available"},
        {"item_id": "RES-105", "title": "Digital Electronics Lab Kit", "course_code": "2026ECSE102", "price": 600.0, "condition": "New", "hostel_block": "C", "seller_contact": "9899887766", "status": "Available"},
    ]


def load_inventory(filepath: str = CSV_FILE) -> List[dict]:
    if not os.path.exists(filepath):
        initial = seed_initial_data()
        save_inventory(initial, filepath)
        return initial

    inventory = []
    with open(filepath, mode="r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            row["price"] = float(row["price"])
            inventory.append(row)
    return inventory


def save_inventory(inventory: List[dict], filepath: str = CSV_FILE) -> None:
    with open(filepath, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for item in inventory:
            writer.writerow(item)


def generate_next_id(inventory: List[dict]) -> str:
    if not inventory:
        return "RES-101"
    max_num = max(int(item["item_id"].split("-")[1]) for item in inventory)
    return f"RES-{max_num + 1}"


# --- Core Computational Feature: Weighted Compatibility Matcher (40/30/20/10) ---
def extract_dept_prefix(course_code: str) -> str:
    # Extracts alphabetic department code (e.g., '2026CSAE100' -> 'CSAE')
    return "".join(ch for ch in course_code.upper() if ch.isalpha())


def calculate_compatibility(item: dict, req: MatchRequest) -> dict:
    # 1. Course Match (40 pts)
    target_course = req.target_course.strip().upper()
    item_course = item["course_code"].upper()
    if item_course == target_course:
        course_pts = 40.0
    elif extract_dept_prefix(item_course) == extract_dept_prefix(target_course) and extract_dept_prefix(target_course) != "":
        course_pts = 15.0
    else:
        course_pts = 0.0

    # 2. Price vs. Budget Fit (30 pts)
    price = float(item["price"])
    budget = float(req.max_budget)
    if price <= budget:
        budget_pts = 30.0
    elif budget > 0 and price <= budget * 1.25:
        # Linear decay down to 0 up to 25% over budget
        over_ratio = (price - budget) / (0.25 * budget)
        budget_pts = round(30.0 * (1.0 - over_ratio), 1)
    else:
        budget_pts = 0.0

    # 3. Hostel Proximity (20 pts)
    buyer_h = req.buyer_hostel.strip().upper()
    seller_h = item["hostel_block"].upper()
    if seller_h == buyer_h:
        hostel_pts = 20.0
    elif seller_h in ADJACENT_HOSTELS.get(buyer_h, set()):
        hostel_pts = 10.0
    else:
        hostel_pts = 5.0

    # 4. Item Condition (10 pts)
    cond_map = {"New": 10.0, "Good": 8.0, "Fair": 5.0}
    cond_pts = cond_map.get(item["condition"], 5.0)

    total_score = round(course_pts + budget_pts + hostel_pts + cond_pts, 1)
    return {
        "total_score": total_score,
        "breakdown": {
            "course": course_pts,
            "budget": budget_pts,
            "hostel": hostel_pts,
            "condition": cond_pts,
        }
    }


# --- API Endpoints ---
@app.get("/")
def serve_frontend():
    # index.html lives in the same directory as main.py (flat layout)
    candidate_paths = [
        os.path.join(BASE_DIR, "index.html"),
        os.path.join(os.getcwd(), "index.html"),
        os.path.join(BASE_DIR, "frontend", "index.html"),
        os.path.join(os.getcwd(), "frontend", "index.html"),
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            return FileResponse(path)
    return {"message": "API is running. Open index.html in your browser."}


@app.get("/api/resources")
def get_resources(keyword: Optional[str] = "", course: Optional[str] = "", max_price: Optional[float] = None):
    inventory = load_inventory()
    results = []
    kw = keyword.strip().lower() if keyword else ""
    crs = course.strip().upper() if course else ""

    for item in inventory:
        if kw and kw not in item["title"].lower():
            continue
        if crs and crs != item["course_code"].upper():
            continue
        if max_price is not None and item["price"] > max_price:
            continue
        results.append(item)
    return results


@app.post("/api/resources")
def add_resource(payload: ResourceCreate):
    inventory = load_inventory()
    new_item = {
        "item_id": generate_next_id(inventory),
        "title": payload.title.strip(),
        "course_code": payload.course_code,
        "price": round(payload.price, 2),
        "condition": payload.condition,
        "hostel_block": payload.hostel_block,
        "seller_contact": payload.seller_contact,
        "status": "Available",
    }
    inventory.append(new_item)
    save_inventory(inventory)
    return new_item


@app.patch("/api/resources/{item_id}/status")
def toggle_status(item_id: str, payload: StatusUpdate):
    inventory = load_inventory()
    for item in inventory:
        if item["item_id"] == item_id:
            item["status"] = payload.status
            save_inventory(inventory)
            return item
    raise HTTPException(status_code=404, detail="Resource ID not found.")


@app.delete("/api/resources/{item_id}")
def delete_resource(item_id: str):
    inventory = load_inventory()
    updated = [item for item in inventory if item["item_id"] != item_id]
    if len(updated) == len(inventory):
        raise HTTPException(status_code=404, detail="Resource ID not found.")
    save_inventory(updated)
    return {"deleted": item_id}


@app.post("/api/match")
def match_resources(req: MatchRequest):
    inventory = load_inventory()
    matches = []
    for item in inventory:
        # Decision Tree Root Gate: Prune Reserved items
        if item["status"] != "Available":
            continue
        score_data = calculate_compatibility(item, req)
        matches.append({
            **item,
            "score": score_data["total_score"],
            "breakdown": score_data["breakdown"]
        })
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches


@app.get("/api/report")
def get_summary_report():
    inventory = load_inventory()
    total = len(inventory)
    available = sum(1 for i in inventory if i["status"] == "Available")
    reserved = total - available
    avg_price = round(sum(i["price"] for i in inventory) / total, 2) if total > 0 else 0.0

    # Course-wise distribution
    course_stats = {}
    for item in inventory:
        c = item["course_code"]
        if c not in course_stats:
            course_stats[c] = {"course_code": c, "listed": 0, "available": 0, "total_price": 0.0}
        course_stats[c]["listed"] += 1
        if item["status"] == "Available":
            course_stats[c]["available"] += 1
        course_stats[c]["total_price"] += item["price"]

    breakdown = []
    for c, data in course_stats.items():
        breakdown.append({
            "course_code": c,
            "listed": data["listed"],
            "available": data["available"],
            "avg_price": round(data["total_price"] / data["listed"], 2)
        })

    return {
        "total_listings": total,
        "available_count": available,
        "reserved_count": reserved,
        "average_price": avg_price,
        "estimated_savings_pct": 50.4,  # Benchmark campus savings metric
        "course_breakdown": breakdown
    }
