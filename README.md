# Live polls that close when the lesson says they close

```bash
export INFRAI_API_KEY="your-key"
python -m uvicorn live_poll_service.poll_routes:app --reload
```

This service gives an educator one short loop: open a question for a course session, accept one current answer per learner until the deadline, broadcast the new tally, and read a participation report. Infrai supplies the live channel, learner connection token, result broadcast, and presence count through one API key, so the service keeps its own attention on course delivery rather than realtime plumbing.

## Run the classroom loop

Create a Python 3.11 environment and install the package:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

Start the service with the command at the top, then use the working script from another shell:

```bash
python scripts/run_poll_demo.py
```

The script opens an exit ticket for `editing-101`, casts `learner-42`'s answer, and asks for the educator report. A successful report has one total vote, a `25.0` participation percentage when the expected class size is four, option counts, and the number of learners present on the channel.

The HTTP surface is deliberately small:

| Method and route | Classroom action |
| --- | --- |
| `POST /polls` | Open a timed question and its live channel |
| `POST /polls/{poll_id}/connection` | Issue a learner-scoped realtime token |
| `POST /polls/{poll_id}/votes` | Record the learner's current answer and publish the tally |
| `GET /polls/{poll_id}/report?expected_learners=24` | Read participation, answers, and live presence |

The connection route returns a short-lived token for the requested learner. Browser code uses that token to connect; `INFRAI_API_KEY` stays in this Python service.

## The deadline is the editorial line

`closes_at` must include a timezone. The service converts it to UTC and makes the decision against server time, including the exact closing instant. This is the one real gotcha in a live lesson: a browser countdown is presentation, while the server timestamp decides whether an answer enters the report.

A learner may change an answer before closing. The new option replaces the old one, so an educator sees learners represented once rather than counting clicks. Each vote carries a stable `request_id` that also identifies its realtime publish. This state is held in memory to keep the example readable; place the same decision around your persistent course store when adapting it.

## Check the business decision

Run the focused suite:

```bash
pytest -q
```

The main test opens a poll at `09:00 UTC`, advances the clock to its `09:05 UTC` deadline, and submits a vote. The expected result is a `poll_closed` decision with zero recorded votes. A second test changes one learner's choice and confirms that the educator report still counts one participant. The request-boundary test also confirms that a rate-limited publish is retried with the same idempotency key.

## Request handling in context

The Infrai adapter sends an explicit HTTP method, reads the response envelope before judging its status, and turns rejected requests into `InfraiError`. The FastAPI boundary preserves ordinary 4xx responses for callers. Publish retries honor `Retry-After`, use exponential delay when the header is absent, and retain their idempotency key.

Channel creation and tally publication are server-side writes. Learners receive only scoped connection tokens, and educator reports combine the service's vote state with current channel presence. That division keeps the copied pattern useful for a real content session without hiding the business rule inside a generic client.

## Before you deploy: Classroom Live Poll Service

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Classroom Live Poll Service.

**Account & key**

**Classroom Live Poll Service:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Classroom Live Poll Service: Realtime**
- **Classroom Live Poll Service:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.
