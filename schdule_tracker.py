from datetime import datetime, time
import sys
import time as time_module
import json
from pathlib import Path

# -------- CONFIG --------
DEFAULT_MODE = "wfh"  # wfh or office
EVENING_MEETING_DAYS = {"Mon", "Wed", "Fri"}
PM_MEETING_DAYS = {"Mon", "Wed"}

# -------- HELPERS --------
def now():
    return datetime.now()

def today():
    return now().strftime("%a")

def in_range(start, end, current):
    return start <= current < end

def get_icon(activity: str) -> str:
    text = activity.lower()
    mapping = [
        (["deep office work", "finish office work", "office work"], "💼"),
        (["morning routine"], "☀️"),
        (["pooja", "dhyaan", "meditation"], "🧘"),
        (["commute", "drive"], "🚗"),
        (["study", "design notes", "system design"], "📚"),
        (["breakfast"], "🍳"),
        (["short break", "break / walk", "break"], "☕️"),
        (["daily scrum", "scrum", "meeting with pm", "meeting"], "📅"),
        (["personal project", "build something"], "🚀"),
        (["gym"], "🏋️"),
        (["shower", "recovery"], "🚿"),
        (["pakhi", "family"], "👨‍👧"),
        (["dinner"], "🍽️"),
        (["free time", "decompress"], "🎧"),
        (["evening office meeting"], "🧑‍💼"),
        (["coding"], "💻"),
        (["reading"], "📖"),
        (["wind down", "sleep"], "🌙"),
    ]
    for keywords, icon in mapping:
        if any(k in text for k in keywords):
            return icon
    return "📌"

def format_duration(delta_seconds: int) -> str:
    hours = delta_seconds // 3600
    minutes = (delta_seconds % 3600) // 60
    parts = []
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)

def find_next_activity(schedule, current_time):
    # schedule items: (slot_id, start, end, activity)
    upcoming = [(slot_id, s, e, a) for (slot_id, s, e, a) in schedule if s > current_time]
    if not upcoming:
        return None
    upcoming.sort(key=lambda x: x[1])  # sort by start time
    return upcoming[0]

def parse_time_str(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))

def get_date_str() -> str:
    return now().strftime("%Y-%m-%d")

def load_overrides(plans_dir: Path, date_str: str) -> tuple[dict, dict]:
    """
    Load per-date overrides from plans/<YYYY-MM-DD>.json
    Schema (array of items), supports either ID-based or start-time-based overrides:
      [
        {"id": 4, "activity": "Prepare slides for demo"},
        {"id": 13, "activity": "Ship personal project MVP"},
        // legacy support:
        {"start": "07:30", "activity": "Prepare slides for demo"}
      ]
    Prefer 'id' when present.
    """
    overrides_path = plans_dir / f"{date_str}.json"
    if not overrides_path.exists():
        return {}, {}
    try:
        data = json.loads(overrides_path.read_text(encoding="utf-8"))
        by_id: dict[int, str] = {}
        by_start: dict[time, str] = {}
        for item in data:
            # ID-based override
            if "id" in item and "activity" in item:
                try:
                    by_id[int(item["id"])] = str(item["activity"])
                    continue
                except Exception:
                    pass
            # Start-time based override (legacy)
            start_str = item.get("start")
            activity = item.get("activity")
            if not start_str or not activity:
                continue
            try:
                start_t = parse_time_str(str(start_str))
                by_start[start_t] = str(activity)
            except Exception:
                # Skip malformed entries silently
                continue
        return by_id, by_start
    except Exception:
        # If file is malformed, ignore overrides
        return {}, {}

def merge_schedule_with_overrides(schedule, overrides_by_id: dict, overrides_by_start: dict):
    """
    Replace the activity of any default slot using ID-based overrides.
    Fall back to start-time overrides for legacy files.
    """
    merged = []
    for slot_id, start, end, activity in schedule:
        if slot_id in overrides_by_id:
            merged.append((slot_id, start, end, overrides_by_id[slot_id]))
        elif start in overrides_by_start:
            merged.append((slot_id, start, end, overrides_by_start[start]))
        else:
            merged.append((slot_id, start, end, activity))
    return merged

def build_schedule(mode, day):
    # Each slot has a stable numeric ID (1-based)
    slots = [

        # Morning
        (time(5,30), time(6,30), "Morning routine: tea, freshen up, shower"),
        (time(6,30), time(6,40), "Pooja / Dhyaan"),

        # Commute / Study
        (time(6,45), time(7,30),
            "Commute to office" if mode == "office"
            else "Light study (reading / design notes)"),

        # Work block 1
        (time(7,30), time(8,30), "Deep office work (focus block)"),
        (time(8,30), time(9,0), "Breakfast"),

        # Work block 2
        (time(9,0), time(10,0), "Office work"),
        (time(10,0), time(10,10), "Short break"),
        (time(10,10), time(11,0), "Office work"),
        (time(11,0), time(11,5), "Short break"),
        (time(11,5), time(11,55), "Finish office work"),

        # Scrum
        (time(12,0), time(12,30), "Daily scrum + connects"),

        # Return / Reset
        (time(12,30), time(13,45),
            "Drive back home" if mode == "office"
            else "Chill / food prep / reset"),

        # Personal growth
        (time(13,45), time(14,45), "Personal project (build something real)"),
        (time(15,0), time(16,0), "System design study (diagram / trade-offs)"),

        # PM Meeting / Break
        (time(16,30), time(17,0),
            "Meeting with PM" if day in PM_MEETING_DAYS
            else "Break / walk / light rest"),

        # Gym
        (time(17,0), time(18,0), "Gym"),
        (time(18,0), time(18,30), "Shower + recovery"),

        # Family
        (time(18,30), time(19,0), "Pakhi reading time"),
        (time(19,0), time(20,0), "Dinner prep + dinner"),

        # Evening
        (time(20,0), time(20,30), "Free time / decompress"),

        # Evening meeting / Coding
        (time(20,30), time(21,15),
            "Evening office meeting" if day in EVENING_MEETING_DAYS
            else "Light coding / one problem"),

        # Reading
        (time(21,15), time(22,15), "Reading (monthly book goal)"),
        (time(22,15), time(23,59), "Wind down / sleep prep"),
    ]
    # Attach stable slot IDs (1-based)
    schedule_with_ids = []
    for idx, (s, e, a) in enumerate(slots, start=1):
        schedule_with_ids.append((idx, s, e, a))
    return schedule_with_ids

def print_current_activity(mode):
    current_time = now().time()
    day = today()
    schedule = build_schedule(mode, day)

    # Per-date plan overrides
    plans_dir = Path(__file__).parent / "plans"
    date_str = get_date_str()
    overrides_by_id, overrides_by_start = load_overrides(plans_dir, date_str)
    schedule = merge_schedule_with_overrides(schedule, overrides_by_id, overrides_by_start)
    for slot_id, start, end, activity in schedule:
        if in_range(start, end, current_time):
            print(f"🔥 NOW {get_icon(activity)} {current_time.strftime('%H:%M')} → {activity}")
            break
    else:
        print("😴 Sleep time or off-schedule")

    # Next activity (today)
    next_item = find_next_activity(schedule, current_time)
    if next_item:
        _next_slot_id, next_start, _next_end, next_activity = next_item
        now_dt = now()
        next_dt = datetime.combine(now_dt.date(), next_start)
        remaining_seconds = max(0, int((next_dt - now_dt).total_seconds()))
        print(f"➡️ Next {next_dt.strftime('%H:%M')} ({format_duration(remaining_seconds)}) {get_icon(next_activity)} → {next_activity}")
    else:
        print("➡️ Next: none today")

# -------- MODE --------
mode = sys.argv[1].lower() if len(sys.argv) > 1 else DEFAULT_MODE
if mode not in {"wfh", "office"}:
    print("Usage: python schedule.py [wfh|office]")
    sys.exit(1)

# -------- LOOP OUTPUT (every 96 seconds) --------
if __name__ == "__main__":
    try:
        while True:
            print_current_activity(mode)
            sys.stdout.flush()
            time_module.sleep(96)
    except KeyboardInterrupt:
        pass
