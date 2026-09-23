from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx


def main() -> None:
    base = os.environ.get("POLL_SERVICE_URL", "http://127.0.0.1:8000")
    poll_id = f"exit-ticket-{int(datetime.now(timezone.utc).timestamp())}"
    poll = {
        "course_id": "editing-101",
        "session_id": "lesson-07",
        "poll_id": poll_id,
        "educator_id": "educator-mira",
        "question": "Which opening keeps the lesson moving?",
        "options": [
            {"id": "scene", "label": "Open on a concrete scene"},
            {"id": "summary", "label": "Start with a summary"},
        ],
        "closes_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    }
    with httpx.Client(base_url=base, timeout=10.0) as client:
        opened = client.request(method="POST", url="/polls", json=poll)
        opened.raise_for_status()
        voted = client.request(
            method="POST",
            url=f"/polls/{poll_id}/votes",
            json={
                "request_id": f"demo-vote-{poll_id}-learner-42",
                "learner_id": "learner-42",
                "option_id": "scene",
            },
        )
        voted.raise_for_status()
        report = client.request(
            method="GET",
            url=f"/polls/{poll_id}/report",
            params={"expected_learners": 24},
        )
        report.raise_for_status()
        print(report.json())


if __name__ == "__main__":
    main()
