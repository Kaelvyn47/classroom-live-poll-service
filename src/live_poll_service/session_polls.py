from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field, model_validator


class PollOption(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=120)


class OpenPollRequest(BaseModel):
    course_id: str = Field(min_length=1, max_length=80)
    session_id: str = Field(min_length=1, max_length=80)
    poll_id: str = Field(min_length=1, max_length=80)
    educator_id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=300)
    options: list[PollOption] = Field(min_length=2, max_length=8)
    closes_at: datetime

    @model_validator(mode="after")
    def option_ids_are_unique(self) -> "OpenPollRequest":
        ids = [option.id for option in self.options]
        if len(ids) != len(set(ids)):
            raise ValueError("option ids must be unique")
        return self


class CastVoteRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=100)
    learner_id: str = Field(min_length=1, max_length=80)
    option_id: str = Field(min_length=1, max_length=40)


class PollSnapshot(BaseModel):
    poll_id: str
    question: str
    closes_at: datetime
    status: str
    total_votes: int
    counts: dict[str, int]


class EducatorReport(BaseModel):
    course_id: str
    session_id: str
    poll_id: str
    total_votes: int
    expected_learners: int
    participation_percent: float
    online_learners: int
    counts: dict[str, int]


class PollDecisionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PollState:
    request: OpenPollRequest
    votes: dict[str, str] = field(default_factory=dict)


class SessionPolls:
    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._polls: dict[str, PollState] = {}
        self._now = now or (lambda: datetime.now(timezone.utc))

    def open_poll(self, request: OpenPollRequest) -> PollSnapshot:
        closes_at = self._as_utc(request.closes_at)
        if closes_at <= self._now():
            raise PollDecisionError("deadline_passed", "closes_at must be in the future")
        if request.poll_id in self._polls:
            raise PollDecisionError("poll_exists", "poll_id is already in use")
        request.closes_at = closes_at
        self._polls[request.poll_id] = PollState(request=request)
        return self.snapshot(request.poll_id)

    def cast_vote(self, poll_id: str, vote: CastVoteRequest) -> PollSnapshot:
        state = self._get(poll_id)
        if self._now() >= state.request.closes_at:
            raise PollDecisionError("poll_closed", "the voting deadline has passed")
        option_ids = {option.id for option in state.request.options}
        if vote.option_id not in option_ids:
            raise PollDecisionError("unknown_option", "option_id is not part of this poll")
        state.votes[vote.learner_id] = vote.option_id
        return self.snapshot(poll_id)

    def snapshot(self, poll_id: str) -> PollSnapshot:
        state = self._get(poll_id)
        vote_counts = Counter(state.votes.values())
        counts = {option.id: vote_counts[option.id] for option in state.request.options}
        return PollSnapshot(
            poll_id=poll_id,
            question=state.request.question,
            closes_at=state.request.closes_at,
            status="closed" if self._now() >= state.request.closes_at else "open",
            total_votes=len(state.votes),
            counts=counts,
        )

    def report(
        self, poll_id: str, expected_learners: int, online_learners: int
    ) -> EducatorReport:
        state = self._get(poll_id)
        snapshot = self.snapshot(poll_id)
        percent = (snapshot.total_votes / expected_learners * 100) if expected_learners else 0
        return EducatorReport(
            course_id=state.request.course_id,
            session_id=state.request.session_id,
            poll_id=poll_id,
            total_votes=snapshot.total_votes,
            expected_learners=expected_learners,
            participation_percent=round(percent, 1),
            online_learners=online_learners,
            counts=snapshot.counts,
        )

    def educator_id(self, poll_id: str) -> str:
        return self._get(poll_id).request.educator_id

    @staticmethod
    def channel_for(poll_id: str) -> str:
        return f"course-poll:{poll_id}"

    def _get(self, poll_id: str) -> PollState:
        try:
            return self._polls[poll_id]
        except KeyError as exc:
            raise PollDecisionError("poll_missing", "poll_id was not found") from exc

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise PollDecisionError("timezone_required", "closes_at needs a timezone")
        return value.astimezone(timezone.utc)
