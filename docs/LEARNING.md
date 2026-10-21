# Build Vintagecat hands-on

The app under `app/` is an assistant-built reference prototype. Your learning implementation starts in `learning/main.py`. You do not need to read the full reference implementation to begin.

## How we will work

For each checkpoint:

1. Understand the user behavior we need and why the design matters.
2. Write a small implementation yourself.
3. Run it and inspect real requests, outputs and errors.
4. Share your code or error for review. Ask for a hint, a walkthrough or a full example as needed.
5. Explain the design in your own words, then commit your work before moving on.

We will track what you implemented, what was assisted, and what you can explain. The reference app's 23 passing tests do not establish that your own implementation is complete. Its first-party model and provider accuracy are still untested.

## Checkpoint 1: create and retrieve a garment

**User behavior:** save a garment's title, brand and size, then retrieve the same garment by ID.

**Learn:** HTTP request/response, JSON, Pydantic validation, optional values, generated identity, status codes, and the lifetime of in-memory state.

Set up Python and the virtual environment using the main README, then install the development requirements. Start YOUR app instead of the reference app:

Mac:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn learning.main:app --reload --host 127.0.0.1 --port 8001
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn learning.main:app --reload --host 127.0.0.1 --port 8001
```

Visit http://127.0.0.1:8001/health and http://127.0.0.1:8001/docs. The health route is provided to establish that your environment works. No GPU, Ollama or API key is needed at this checkpoint.

### Your contract

Implement only these pieces in `learning/main.py`:

| Piece | Expected behavior |
|---|---|
| `ItemCreate` | A Pydantic model; `title` is required, 1–120 characters; `brand` and `size` are optional strings defaulting to `None` |
| `POST /items` | Accept the model, generate a fresh string ID, store a JSON-friendly dict in `items`, return it with HTTP 201 |
| `GET /items/{item_id}` | Return that item; use HTTP 404 when the ID is unknown |

Example request:

```json
{"title":"Brown work jacket","brand":"Carhartt","size":"L"}
```

The response contains the same three fields plus a generated `id`. Different physical garments may have identical titles, so titles must not be the storage key. Do not guess an unknown brand or size.

Start by writing `ItemCreate` alone and showing it to me. We can then work on the POST route, and finally GET. You do not need to solve all three at once.

Hints if needed:

- `Field` can express length constraints.
- `str | None` permits an unknown value; a default controls whether the field must be supplied.
- `model_dump()` produces a dict from a validated model.
- The imported `uuid4` can generate a fresh ID.
- Route decorators can set a response status code.
- Raising `HTTPException` lets the route communicate a missing item.

### Check your work

Mac:

```bash
.venv/bin/python -m pytest learning/test_checkpoint_01.py -q
```

Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest learning/test_checkpoint_01.py -q
```

These checks intentionally fail until you implement the routes. One missing-item check may pass before implementation because an unimplemented route also returns 404; the other checks establish the real behavior. The reference suite runs separately with `python -m pytest -q`.

Definition of done: valid create/read works, unknown attributes remain null, invalid titles return 422, unknown IDs return 404, and identical titles get distinct IDs. Restart the server and observe what happens to the items.

Be ready to explain: Who validates the request? Why use an ID instead of the title? Why is null different from an empty string? Why do the records disappear after a restart?

Suggested first commit after it works: `feat: create and retrieve validated garment records`.

## Later checkpoints — one at a time

| Checkpoint | What you implement | What you learn |
|---|---|---|
| 2 | Persist items in SQLite | Schemas, SQL, transactions and restart behavior |
| 3 | Upload and retrieve garment images | Multipart requests, file validation, IDs versus filenames |
| 4 | One image-to-Ollama request | HTTP clients, base64, timeouts and structured outputs |
| 5 | Separate AI suggestions from approved facts | Human review, provenance and validation |
| 6 | Add comps and filter evidence | Source quality, sold versus asking prices, deterministic statistics |
| 7 | Optional provider adapter | API keys, quotas, caching, provider contracts and errors |
| 8 | Background jobs and failure recovery | Concurrency, idempotency and durable state |
| 9 | Evaluate actual garments | Held-out examples, unsupported claims and measured latency |
| 10 | First authorized eBay publication | OAuth, marketplace schemas, ambiguous timeouts and reconciliation |

Revisit framework/database choices as you learn. There is no need to implement microservices, train a custom model or build five connectors before the first meaningful workflow is proven.
