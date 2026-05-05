"""
Seed the database with sample students for development/testing.
Run: python seed_data.py
"""
from app.database import init_db, SessionLocal
from app.models import StudentTriggerData

STUDENTS = [
    # High-risk: multiple hw behind, low effort, inactive
    {"UserID": 1001, "FirstName": "Alice",   "LastName": "Johnson",  "Email": "alice@example.com",   "PhoneNumber": "+15550001001", "PathName": "SQL",  "HWsBehind": 4, "AvgEffRating": 2.1, "LastActivityDays": 10},
    {"UserID": 1002, "FirstName": "Bob",     "LastName": "Williams", "Email": "bob@example.com",     "PhoneNumber": "+15550001002", "PathName": "SSRS", "HWsBehind": 3, "AvgEffRating": 2.4, "LastActivityDays": 8},
    # Medium-risk: borderline thresholds
    {"UserID": 1003, "FirstName": "Carol",   "LastName": "Davis",    "Email": "carol@example.com",   "PhoneNumber": "+15550001003", "PathName": "SSIS", "HWsBehind": 2, "AvgEffRating": 2.9, "LastActivityDays": 6},
    {"UserID": 1004, "FirstName": "David",   "LastName": "Martinez", "Email": "david@example.com",   "PhoneNumber": "+15550001004", "PathName": "SQL",  "HWsBehind": 2, "AvgEffRating": 3.1, "LastActivityDays": 7},
    # Low-risk / borderline eligible
    {"UserID": 1005, "FirstName": "Eva",     "LastName": "Garcia",   "Email": "eva@example.com",     "PhoneNumber": "+15550001005", "PathName": "SSRS", "HWsBehind": 2, "AvgEffRating": 3.0, "LastActivityDays": 5},
    # Below threshold — should NOT be contacted
    {"UserID": 1006, "FirstName": "Frank",   "LastName": "Lee",      "Email": "frank@example.com",   "PhoneNumber": "+15550001006", "PathName": "SQL",  "HWsBehind": 0, "AvgEffRating": 4.5, "LastActivityDays": 1},
    # No phone — email only
    {"UserID": 1007, "FirstName": "Grace",   "LastName": "Taylor",   "Email": "grace@example.com",   "PhoneNumber": None,           "PathName": "SSIS", "HWsBehind": 3, "AvgEffRating": 2.3, "LastActivityDays": 9},
    # No contact info — should be skipped
    {"UserID": 1008, "FirstName": "Henry",   "LastName": "Brown",    "Email": None,                  "PhoneNumber": None,           "PathName": "SQL",  "HWsBehind": 5, "AvgEffRating": 1.8, "LastActivityDays": 15},
    # Post-completion track
    {"UserID": 1009, "FirstName": "Iris",    "LastName": "Wilson",   "Email": "iris@example.com",    "PhoneNumber": "+15550001009", "PathName": "POST_COMPLETION", "HWsBehind": 0, "AvgEffRating": 4.2, "LastActivityDays": 2},
    {"UserID": 1010, "FirstName": "James",   "LastName": "Anderson", "Email": "james@example.com",   "PhoneNumber": "+15550001010", "PathName": "SQL",  "HWsBehind": 3, "AvgEffRating": 2.6, "LastActivityDays": 8},
]


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        for s in STUDENTS:
            existing = db.get(StudentTriggerData, s["UserID"])
            if existing:
                print(f"  skip  student {s['UserID']} (already exists)")
                continue
            db.add(StudentTriggerData(**s))
            print(f"  added student {s['UserID']} — {s['FirstName']} {s['LastName']}")
        db.commit()
        print(f"\nSeeded {len(STUDENTS)} students.")
    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding database...")
    seed()
