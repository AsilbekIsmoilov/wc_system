import re
from datetime import timedelta

def parse_schedule(schedule):
    schedule = schedule.replace(".", "")

    m = re.match(r"(\d{1,2})-(\d{1,2})", schedule)
    if not m:
        return None

    return int(m.group(1)), int(m.group(2))


def calculate_login_time(now, duration_sec):
    return now - timedelta(seconds=duration_sec)