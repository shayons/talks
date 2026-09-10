# Streaming and catalog integration

The browser and FastAPI share an origin. Provider credentials stay on the server.

## Startup

- `GET /api/customers`: customer IDs, names, and summaries. Use the returned names; stable IDs also map to portraits and prompts.
- `GET /api/chat/config`: default route and model metadata. `configured` checks for the direct OpenAI key; it does not probe AWS permissions.
- `GET /api/health`: database connectivity.
- `GET /api/search/status`: catalog and index readiness.

## Search and catalog

The shell serves `/`, `/catalog`, `/experiments`, and `/concierge`. Navigation keeps loaded views in memory, including the active chat stream and draft. Each page loads its JavaScript module on first use.

`GET /api/catalog` returns `products`, `total`, `truncated`, and `embedding_model`. The list is bounded to 200 products and includes descriptions and embedding dimension counts. `GET /api/catalog/{bean_id}` returns one public product plus `weighted_fields`, its stored `search_document`, and the numeric `embedding`. Unknown IDs return 404; database failures return a generic 503. Neither endpoint exposes customer context.

`POST /api/search` accepts:

```json
{
  "query": "bergamot",
  "budget": 2000,
  "roasts": [],
  "origins": [],
  "stock_only": true,
  "fuzzy": false,
  "candidates": 8,
  "rrf_k": 60,
  "min_cosine": null,
  "explain": false
}
```

Budget is in cents; null removes the cap. Candidate depth is 1–100, RRF k is 1–200, and optional minimum cosine is −1 to 1. Eligibility filters precede candidate limits. The cosine threshold removes semantic candidates before fusion, preserving any independent lexical contribution.

The response includes fused `results` with independent lexical/semantic ranks and scores, canonical product fields, highlighted text tokens, `eligible_count`, `parsed_query`, lexical `excluded` rows and reasons, `settings`, actual parameterized `sql`, diagnostic SQL, timings, and model ID. Lists are views of those ranks; the browser does not recompute similarities. Counts and diagnostics share the comparison's repeatable-read snapshot. `explain: true` adds a real `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` plan from a second execution.

## Conference experiments

`GET /api/experiments/status` reports whether presenter controls are enabled, durable price-demo state, and fixture readiness. Blind judging uses ordinary read-only search requests; choices stay in browser memory.

The following JSON POST routes require `ENABLE_STAGE_CONTROLS=1` and reject cross-origin requests:

| Route | Body | Effect |
| --- | --- | --- |
| `/api/experiments/price` | `{"action":"raise"}` or `{"action":"restore"}` | Reversible $19/$24 change to `b_ethiopia_yirg`, with conflict detection and durable undo state. |
| `/api/experiments/index/prepare` | `{}` | Idempotently creates the separate 12,000-row, 384-dimensional synthetic fixture and its HNSW index. |
| `/api/experiments/index/compare` | `{"ef_search":40,"filtered":true,"iterative":false}` | Read-only exact/HNSW execution comparison with neighbor IDs, recall @20, timings, and actual plans. |

`ef_search` is bounded to 20–400. The filtered fixture selects one of twenty categories. The response reports whether `points_hnsw` was actually used and explains cache/order effects and the difference between neighbor recovery and relevance. No experiment touches customer conversations, approvals, or inventory quantities.

## Chat request

`POST /api/query/stream` accepts:

```json
{
  "customer_id": "u_marco",
  "query": "Floral coffee under $25",
  "session_id": null,
  "model_route": "bedrock-openai"
}
```

Queries are limited to 2,000 characters; whitespace-only requests are rejected. Sessions use UUIDs and must belong to the customer. `POST /api/query` retains the completed JSON response for other clients.

| Event | Meaning |
| --- | --- |
| `session` | Server-issued session ID and actual model IDs |
| `status` | Progress text |
| `plan`, `step`, `panel` | Workflow and SQL/model telemetry |
| `text_delta` | Response text, potentially including partial formatting |
| `response` | Complete text, citations, coverage heuristic, verified products |
| `done` | Pipeline and assistant-message persistence completed |
| `error` | Request failed; do not report success |

The client requires `done`; a closed connection is not enough. Product cards appear after terminal success. Failures are never automatically replayed because an approval may already have been committed. Customer, session, model, and send controls remain disabled during a request.

The server uses a bounded queue and a worker thread, emits keep-alives, enforces a 180-second deadline, and signals cancellation on disconnect. Cancellation is checked at model and pipeline boundaries and does not undo earlier commits.

## Product contract

`response.products` is built from catalog rows after eligibility verification. Example shape:

```json
{
  "id": "b_ethiopia_yirg",
  "name": "Ethiopia Yirgacheffe",
  "origin": "Yirgacheffe, Ethiopia",
  "roast_level": "medium-light",
  "process": "washed",
  "flavor_notes": ["jasmine", "lemon", "bergamot", "honey"],
  "price_cents": 1900,
  "in_stock": 42,
  "currency": "USD",
  "image_url": "/static/products/coffee-light.webp"
}
```

The UI renders the current response values, not this example. Model prose cannot set product names, prices, stock, or artwork. Empty verified results produce no cards. Completed assistant turns retain product details as historical snapshots.

## Model configuration

`CHAT_MODEL_ROUTE` defaults to `bedrock-openai`; alternatives are `bedrock-claude` and `openai`.

| Provider route | Intent override | Response override |
| --- | --- | --- |
| Bedrock OpenAI | `BEDROCK_INTENT_MODEL` | `BEDROCK_RESPONSE_MODEL` |
| Bedrock Claude | `BEDROCK_HAIKU_MODEL` | `BEDROCK_SONNET_MODEL` |
| OpenAI API | `OPENAI_INTENT_MODEL` | `OPENAI_RESPONSE_MODEL` |

The older `BEDROCK_OPUS_MODEL` setting is not used by this route system.

Use AWS credentials available to the server and the chosen `AWS_REGION`. Bedrock's [ConverseStream API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ConverseStream.html) requires `bedrock:InvokeModelWithResponseStream` access to the model or inference profile. Direct OpenAI requires `OPENAI_API_KEY`. Model calls can incur provider charges.

If startup succeeds but a reply fails, inspect the server log and session trace. Check credentials, model access, and structured-intent validation. Before resending an order request, inspect the session's approval rows.
