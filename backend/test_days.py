from datetime import datetime, timezone, timedelta

def test(created_at_str):
    # Simulate Tortoise ORM behavior (parsing ISO string to datetime)
    # Assuming it returns a timezone-aware datetime if DB has timezone
    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
    
    print(f"Created at: {created_at}")
    
    now = datetime.now(tz=timezone.utc) if created_at.tzinfo else datetime.now()
    print(f"Now: {now}")
    
    delta = now.date() - created_at.date()
    print(f"Delta days: {delta.days}")
    
    register_days = max(delta.days + 1, 1)
    print(f"Register days: {register_days}")
    print("-" * 20)

test("2025-12-09T10:02:48.977Z")
test("2026-01-07T12:03:40.680Z")
