"""Generate contribution charts without a third-party image service."""

import json
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path


DAYS = 31
WIDTH = 1000
HEIGHT = 300
LEFT = 55
RIGHT = 25
TOP = 55
BOTTOM = 45


def render_activity(username, days, dark=False):
    if len(days) != DAYS:
        raise ValueError("Expected 31 contribution days")
    for day in days:
        if type(day["contributionCount"]) is not int or day["contributionCount"] < 0:
            raise ValueError("Invalid contribution count")

    background, text, line, point = (
        ("#0d1117", "#58a6ff", "#1f6feb", "#58a6ff") if dark else
        ("#ffffff", "#000000", "#9be9a8", "#40c463")
    )
    chart_width = WIDTH - LEFT - RIGHT
    chart_height = HEIGHT - TOP - BOTTOM
    maximum = max(4, max(day["contributionCount"] for day in days))
    maximum = ((maximum + 3) // 4) * 4
    coordinates = [
        (LEFT + index * chart_width / (DAYS - 1),
         HEIGHT - BOTTOM - day["contributionCount"] * chart_height / maximum)
        for index, day in enumerate(days)
    ]
    points = " ".join(f"{x:.2f},{y:.2f}" for x, y in coordinates)
    total = sum(day["contributionCount"] for day in days)
    title = f"{username}'s Contribution Activity"
    description = (f"{total} contributions from {days[0]['date']} "
                   f"to {days[-1]['date']}")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
        f'height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
        'aria-labelledby="title description">',
        f'<title id="title">{escape(title)}</title>',
        f'<desc id="description">{escape(description)}</desc>',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{background}"/>',
        f'<g fill="{text}" font-family="Arial, sans-serif" font-size="12">',
        f'<text x="{LEFT}" y="30" font-size="20">{escape(title)}</text>',
    ]
    for index in range(5):
        y = HEIGHT - BOTTOM - index * chart_height / 4
        parts.append(f'<path d="M {LEFT} {y} H {WIDTH - RIGHT}" '
                     f'stroke="{text}" stroke-opacity="0.15"/>')
        parts.append(f'<text x="{LEFT - 10}" y="{y + 4}" '
                     f'text-anchor="end">{index * maximum // 4}</text>')
    for index in range(0, DAYS, 6):
        x, _ = coordinates[index]
        parts.append(f'<text x="{x}" y="{HEIGHT - 18}" '
                     f'text-anchor="middle">{escape(days[index]["date"][5:])}</text>')
    parts.extend([
        f'<polygon points="{LEFT},{HEIGHT - BOTTOM} {points} '
        f'{WIDTH - RIGHT},{HEIGHT - BOTTOM}" fill="{line}" fill-opacity="0.18"/>',
        f'<polyline points="{points}" fill="none" stroke="{line}" stroke-width="2"/>',
    ])
    for day, (x, y) in zip(days, coordinates):
        label = f"{day['date']}: {day['contributionCount']} contributions"
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" '
                     f'fill="{point}"><title>{escape(label)}</title></circle>')
    parts.append('</g></svg>')
    return "\n".join(parts)


async def generate_activity(stats):
    end = datetime.now(timezone.utc)
    start = (end - timedelta(days=DAYS - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    query = f"""query {{
      user(login: {json.dumps(stats.username)}) {{
        contributionsCollection(from: {json.dumps(start.isoformat())},
                                to: {json.dumps(end.isoformat())}) {{
          contributionCalendar {{
            weeks {{ contributionDays {{ date contributionCount }} }}
          }}
        }}
      }}
    }}"""
    result = await stats.queries.query(query)
    calendar = result["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = sorted(
        (day for week in calendar["weeks"] for day in week["contributionDays"]
         if start.date().isoformat() <= day["date"] <= end.date().isoformat()),
        key=lambda day: day["date"],
    )
    expected_dates = [(start + timedelta(days=index)).date().isoformat()
                      for index in range(DAYS)]
    if [day["date"] for day in days] != expected_dates:
        raise ValueError("GitHub returned an incomplete contribution calendar")
    output = Path("generated")
    output.mkdir(exist_ok=True)
    for dark, filename in ((False, "activity.svg"), (True, "activity-dark.svg")):
        (output / filename).write_text(
            render_activity(stats.username, days, dark), encoding="utf-8")
