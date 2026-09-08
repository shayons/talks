# Coffee & queries

Coffee & queries is a conference demo and learning application about hybrid search in PostgreSQL, shown through an agentic coffee concierge. It accompanies **Hybrid Search in PostgreSQL: Combining Vector and Full-Text for Real-World Applications** at **Postgres Summit US 2026** in New York City. A specialty-coffee concierge gives the audience a familiar task: find beans that fit a customer's tastes, budget, brewing method, and purchase history.

Shayon Sanyal presents the [Summit session](https://postgresql.us/events/postgressummitus2026/schedule/session/2349-hybrid-search-in-postgresql-combining-vector-and-full-text-for-real-world-applications/) on September 30, 2026, 10:30–11:20 EDT in Letterpress at Convene, 555 Broadway.

The conversation helps a customer choose coffee. The accompanying trace lets developers see the queries, filters, model calls, and checks behind the answer.

## Audience and purpose

The primary audience is PostgreSQL developers, application engineers, and conference attendees exploring agent architecture. Presenters can run the scenarios live; attendees can clone the project and inspect the same implementation locally.

Success means someone can follow a recommendation back to catalog rows, understand how memory informs a follow-up, and see where an action stops for approval.

## Experience

Choose a regular, select a configured model route, and describe a coffee. The application streams the reply and shows database work alongside it. Completed recommendations include illustrated coffee bags with catalog facts.

Follow-up questions reuse the customer's session. A new session clears the visible conversation without erasing history. An order request creates a pending approval record. A catalog miss produces no product cards.

Names, prices, stock, and eligibility belong to the database. Generated language explains the results; it does not supply product-card fields.

## Architecture

FastAPI connects the browser to a Python-controlled pipeline. Strands invokes models for structured intent and response synthesis. PostgreSQL holds profiles, products, embeddings, conversation history, tools, audits, checkpoints, and approvals.

Hybrid retrieval combines full-text and vector ranking. Relational eligibility filters run before candidate limits. Before synthesis, the coordinator re-reads candidates and drops products that no longer qualify.

A structured response supplies canonical product fields and local artwork paths. The client consumes server-sent events, restricts generated HTML formatting, and marks interrupted replies incomplete.

## Design direction

The GitHub Coffee & queries design is the adopted foundation: cream paper, coffee-brown controls, forest-green accents, Fraunces headings, Source Sans 3 interface text, and IBM Plex Mono for SQL and measurements. The regulars' portraits and conversation/telemetry layout remain central.

Packaging artwork is illustrative and shared across light, medium, and dark roast families. Product identity, price, and availability stay in live text beside the image. The interface serves both conference screens and attendees' phones.

## Boundaries

This is an educational local application, not a production storefront. It has no authentication, payment processing, fulfillment worker, or automatic workflow replay. Order requests currently queue one bag. Model access depends on server credentials and account availability.

Canonical verification reduces one class of error; it does not prove every generated sentence. The data-coverage score is a teaching heuristic, not calibrated answer confidence.

## Implemented capabilities

- Customer conversations and session ownership checks.
- Configurable Bedrock and direct OpenAI routes through Strands.
- Live reply and trace streaming with explicit completion and failure handling.
- PostgreSQL hybrid retrieval, history, audits, and pending approvals.
- Canonical product cards with local coffee artwork.
- Read-only MCP tools and programmatic search/experiment APIs.
- Regression checks for SQL eligibility, streaming, session boundaries, browser recovery, and safe rendering.

See [README.md](README.md) for setup and [docs/STREAMING.md](docs/STREAMING.md) for the API contract.
