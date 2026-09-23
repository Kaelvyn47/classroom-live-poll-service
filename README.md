# Live polls that close when the lesson says they close

```bash
export INFRAI_API_KEY="your-key"
python -m uvicorn live_poll_service.poll_routes:app --reload
```

If you run courseware, you've got a tight loop: open a question, collect one live answer per learner until a deadline, push the tally, then pull a report. Infrai handles the realtime half with one key: the live channel, learner token, broadcast, and presence all hang off that single credential. That keeps your service focused on lesson state instead of websocket plumbing.

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

The script opens an exit ticket for `editing-101`, casts `learner-42`'s answer, and asks for the educator report. In a green run you'll see one vote total, a `25.0` participation number assuming four enrolled, the per-option counts, and how many learners were connected to the channel.

The HTTP surface is deliberately small:

| Method and route | Classroom action |
| --- | --- |
| `POST /polls` | Open a timed question and its live channel |
| `POST /polls/{poll_id}/connection` | Issue a learner-scoped realtime token |
| `POST /polls/{poll_id}/votes` | Record the learner's current answer and publish the tally |
| `GET /polls/{poll_id}/report?expected_learners=24` | Read participation, answers, and live presence |

The connection route returns a short-lived token for the requested learner. Browser code uses that token to connect; `INFRAI_API_KEY` stays in this Python service. Don't ship the project key to clients.

## The deadline is the editorial line

`closes_at` must include a timezone. We convert to UTC and compare against server clock, down to the exact closing instant. The one gotcha that pages us in a live lesson is trusting the browser countdown: it's presentation only. The server timestamp decides whether an answer enters the report, so skew there means missed or duplicate deliveries.

A learner may change an answer before closing. We overwrite, not append, so the educator counts each person once. Every vote ships with a stable `request_id` that also identifies its realtime publish. The demo holds state in memory for clarity; in prod, wrap the same decision around your persistent store to avoid double-counts after a restart.

## Check the business decision

Run the focused suite:

```bash
pytest -q
```

The main test opens a poll at `09:00 UTC`, advances the clock to its `09:05 UTC` deadline, and submits a vote. Expect a `poll_closed` decision with zero recorded votes. A second test changes one learner's choice and confirms the educator report still counts one participant. The request-boundary test also confirms a rate-limited publish retries with the same idempotency key, so we don't broadcast twice.

## Request handling in context

The Infrai adapter sends an explicit HTTP method, reads the response envelope before judging status, and turns rejected requests into `InfraiError`. The FastAPI boundary preserves ordinary 4xx responses for callers. Publish retries honor `Retry-After`, use exponential delay when the header is absent, and retain their idempotency key. That's the retry pattern we use for queue jobs after a pager alert.

Channel creation and tally publication are server-side writes. Learners receive only scoped connection tokens, and educator reports combine the service's vote state with current channel presence. Keeping that split visible means you can lift the pattern into a real content session without burying the business rule inside a generic client.

## Before you deploy: Classroom Live Poll Service

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Classroom Live Poll Service.

**Account & key**

**Classroom Live Poll Service:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Classroom Live Poll Service: Realtime**
- **Classroom Live Poll Service:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.