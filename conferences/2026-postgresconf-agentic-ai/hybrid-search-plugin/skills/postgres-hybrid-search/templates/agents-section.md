## Hybrid search on {{schema}}.{{table}}

Keyword (`search_tsv`, GIN) and vector (`embedding vector({{dims}})`, HNSW) candidates are
fused with Reciprocal Rank Fusion in `{{schema}}.{{table}}_hybrid_search()`.

- **Embeddings:** {{embedding_model}}. Rows use input type `{{document_input_type}}`,
  questions use `{{query_input_type}}`. Never mix models or versions in the column; changing
  the model means re-embedding every row and the evaluation questions.
- **New or edited rows:** `search_tsv` updates itself (generated column). Embeddings do not:
  run `{{backfill_command}}` after bulk loads, or embed on write in the application.
- **Settings the function sets for itself:** `hnsw.ef_search = 100` (must be at least the
  candidate LIMIT of 50) and `hnsw.iterative_scan = relaxed_order` (filters still fill the
  candidate lists). Keep both if you copy the SQL elsewhere.
- **Filters** belong inside both candidate lists, before their LIMIT, never after fusion.
- **Measure before and after any change** to the SQL, weights, model, or indexes:
  `{{evaluate_command}}`. Last result ({{evaluation_date}}): {{evaluation_summary}}.
