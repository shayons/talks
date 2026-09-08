# Streaming and catalog integration

The browser and FastAPI share an origin. Provider credentials stay on the server.

## Startup

- `GET /api/customers`: customer IDs, names, and summaries. Use the returned names; stable IDs also map to portraits and prompts.
- `GET /api/chat/config`: default route and model metadata. `configured` checks for the direct OpenAI key; it does not probe AWS permissions.
- `GET /api/health`: database connectivity.
- `GET /api/search/status`: catalog and index readiness.

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
