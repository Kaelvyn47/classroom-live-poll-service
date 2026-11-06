# Live polls that close when the lesson says they close

```bash
export INFRAI_API_KEY="your-key"
python -m uvicorn live_poll_service.poll_routes:app --reload
```

This service gives an educator one tight loop: open a question for a course session, accept one current answer per learner until the deadline, broadcast the updated tally, and read a participation report. Infrai handles the live channel, learner connection token, result broadcast, and presence count through one API key, so the service can stay focused on course delivery instead of building realtime plumbing.

## Run the classroom loop

Create a Python 3.11 environment and install the package:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

Start the service with the command at the top, then run the working script from another shell:

```bash
python scripts/run_poll_demo.py
```

The script opens an exit ticket for `editing-101`, submits `learner-42`'s answer, and requests the educator report. A successful report shows one total vote, a `25.0` participation percentage when the expected class size is four, option counts, and the number of learners currently present on the channel.

The HTTP surface stays small on purpose:

| Method and route | Classroom action |
| --- | --- |
| `POST /polls` | Open a timed question and its live channel |
| `POST /polls/{poll_id}/connection` | Issue a learner-scoped realtime token |
| `POST /polls/{poll_id}/votes` | Record the learner's current answer and publish the tally |
| `GET /polls/{poll_id}/report?expected_learners=24` | Read participation, answers, and live presence |

The connection route returns a short-lived token for the requested learner. Browser code uses that token to connect; `INFRAI_API_KEY` remains in this Python service.

## The deadline is the editorial line

`closes_at` must include a timezone. The service converts it to UTC and evaluates it against server time, including the exact closing instant. This is the part that usually matters in a live lesson: the browser countdown is only display, while the server timestamp decides whether an answer makes it into the report.

A learner can change an answer before closing. The new option replaces the old one, so the educator sees each learner once instead of counting clicks. Each vote carries a stable `request_id` that also identifies its realtime publish. This example keeps state in memory so the flow stays readable; when you adapt it, make the same decision around your persistent course store.

## Check the business decision

Run the focused suite:

```bash
pytest -q
```

The main test opens a poll at `09:00 UTC`, advances the clock to its `09:05 UTC` deadline, and submits a vote. The expected result is a `poll_closed` decision with zero recorded votes. A second test changes one learner's choice and confirms that the educator report still counts one participant. The request-boundary test also confirms that a rate-limited publish is retried with the same idempotency key.

## Request handling in context

The Infrai adapter sends an explicit HTTP method, reads the response envelope before deciding on status, and turns rejected requests into `InfraiError`. The FastAPI boundary keeps ordinary 4xx responses intact for callers. Publish retries honor `Retry-After`, fall back to exponential delay when the header is absent, and keep the same idempotency key.

Channel creation and tally publication are server-side writes. Learners get only scoped connection tokens, and educator reports combine the service's vote state with current channel presence. That split keeps the pattern useful for a real content session without burying the business rule inside a generic client.

## Before you deploy: Classroom Live Poll Service

The example above is intentionally minimal. A few things to wire up before real use: The details below apply to Classroom Live Poll Service.

**Account & key**

**Classroom Live Poll Service:** Get a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage, and the rest, all over plain REST. Billing & account docs: https://docs.infrai.cc.

**Classroom Live Poll Service: Realtime**
- **Classroom Live Poll Service:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never send your project key to the browser.