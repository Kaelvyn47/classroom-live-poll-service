from datetime import datetime, timedelta, timezone

import pytest

from live_poll_service.session_polls import (
    CastVoteRequest,
    OpenPollRequest,
    PollDecisionError,
    PollOption,
    SessionPolls,
)


NOW = datetime(2026, 9, 6, 9, 0, tzinfo=timezone.utc)


def poll_request() -> OpenPollRequest:
    return OpenPollRequest(
        course_id="editing-101",
        session_id="lesson-07",
        poll_id="opening-check",
        educator_id="educator-mira",
        question="Which opening keeps the lesson moving?",
        options=[
            PollOption(id="scene", label="Open on a concrete scene"),
            PollOption(id="summary", label="Start with a summary"),
        ],
        closes_at=NOW + timedelta(minutes=5),
    )


def test_vote_is_rejected_once_the_learner_deadline_passes() -> None:
    clock = {"now": NOW}
    session = SessionPolls(now=lambda: clock["now"])
    session.open_poll(poll_request())
    clock["now"] = NOW + timedelta(minutes=5)

    with pytest.raises(PollDecisionError) as rejected:
        session.cast_vote(
            "opening-check",
            CastVoteRequest(
                request_id="request-after-close",
                learner_id="learner-42",
                option_id="scene",
            ),
        )

    assert rejected.value.code == "poll_closed"
    assert session.snapshot("opening-check").total_votes == 0


def test_changed_vote_counts_once_in_the_educator_report() -> None:
    session = SessionPolls(now=lambda: NOW)
    session.open_poll(poll_request())
    session.cast_vote(
        "opening-check",
        CastVoteRequest(
            request_id="request-first-choice",
            learner_id="learner-42",
            option_id="scene",
        ),
    )
    session.cast_vote(
        "opening-check",
        CastVoteRequest(
            request_id="request-changed-choice",
            learner_id="learner-42",
            option_id="summary",
        ),
    )

    report = session.report("opening-check", expected_learners=4, online_learners=3)

    assert report.total_votes == 1
    assert report.counts == {"scene": 0, "summary": 1}
    assert report.participation_percent == 25.0
