from __future__ import annotations

from typing import Any
from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .infrai_realtime import InfraiError, InfraiRealtime
from .session_polls import (
    CastVoteRequest,
    EducatorReport,
    OpenPollRequest,
    PollDecisionError,
    PollSnapshot,
    SessionPolls,
)


class LearnerConnectionRequest(BaseModel):
    learner_id: str = Field(min_length=1, max_length=80)


polls = SessionPolls()


def get_realtime() -> InfraiRealtime:
    client = InfraiRealtime()
    try:
        yield client
    finally:
        client.close()


def create_poll_service() -> FastAPI:
    service = FastAPI(title="Classroom live poll service", version="0.1.0")

    @service.exception_handler(PollDecisionError)
    async def domain_error(_: Request, exc: PollDecisionError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"code": exc.code, "message": exc.message})

    @service.exception_handler(InfraiError)
    async def infrai_error(_: Request, exc: InfraiError) -> JSONResponse:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        return JSONResponse(status_code=status, content={"code": exc.code, "detail": exc.detail})

    @service.post("/polls", response_model=PollSnapshot, status_code=201)
    def open_poll(
        body: OpenPollRequest,
        realtime: InfraiRealtime = Depends(get_realtime),
    ) -> PollSnapshot:
        snapshot = polls.open_poll(body)
        realtime.create_channel(polls.channel_for(body.poll_id), f"open-{body.poll_id}")
        return snapshot

    @service.post("/polls/{poll_id}/connection")
    def learner_connection(
        poll_id: str,
        body: LearnerConnectionRequest,
        realtime: InfraiRealtime = Depends(get_realtime),
    ) -> dict[str, Any]:
        polls.snapshot(poll_id)
        return realtime.issue_learner_token(body.learner_id, polls.channel_for(poll_id))

    @service.post("/polls/{poll_id}/votes", response_model=PollSnapshot)
    def cast_vote(
        poll_id: str,
        body: CastVoteRequest,
        realtime: InfraiRealtime = Depends(get_realtime),
    ) -> PollSnapshot:
        snapshot = polls.cast_vote(poll_id, body)
        realtime.publish_result(
            polls.channel_for(poll_id),
            snapshot.model_dump(mode="json"),
            polls.educator_id(poll_id),
            body.request_id,
        )
        return snapshot

    @service.get("/polls/{poll_id}/report", response_model=EducatorReport)
    def educator_report(
        poll_id: str,
        expected_learners: int = Query(ge=0),
        realtime: InfraiRealtime = Depends(get_realtime),
    ) -> EducatorReport:
        presence = realtime.get_presence(polls.channel_for(poll_id))
        members = presence.get("members", [])
        online = len(members) if isinstance(members, list) else 0
        return polls.report(poll_id, expected_learners, online)

    return service


app = create_poll_service()
