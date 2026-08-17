# UniHack — AI-Powered Product Intelligence for Industrial Commerce

## Challenge

Manufacturers publish product information across websites, catalogs, technical documents, and digital assets. This is fragmented and mostly manual to turn into structured, commerce-ready product data.

**Task:** Given minimal input (manufacturer part number, brand, short description — and possibly supporting datasets/documents), build an AI-powered solution that outputs rich, structured, commerce-ready product intelligence.

**Judged on:** understanding products from limited info, discovering/validating relevant information, generating structured output, improving data quality/consistency, explainable and traceable outputs, and scaling across large catalogs.

**Timeline:** 7–8 days to build.

---

## Architecture overview

```
                     ┌─────────────────────────┐
                     │   Streamlit UI           │
                     │  (input: MPN/brand/desc, │
                     │   or catalog upload)     │
                     └────────────┬─────────────┘
                                  │
                                  ▼
                     ┌─────────────────────────┐
                     │   FastAPI backend         │
                     │  (exposes agent endpoints)│
                     └────────────┬─────────────┘
                                  │
                                  ▼
              ┌─────────────────────────────────────┐
              │  deepagents (LangChain) orchestrator   │
              │  agent — LangGraph under the hood,     │
              │  delegates to subagents, calls shared   │
              │  tools (retrieve/save) directly          │
              └──────────────────┬──────────────────┘
                                  │
        ┌─────────────┬──────────┴───────────┐
        ▼             ▼                       ▼
  ┌───────────┐ ┌───────────────┐    ┌─────────────────┐
  │ Scraping   │ │ Parsing        │    │ Orchestrator's   │
  │ subagent   │ │ subagent       │    │ own tools:        │
  │ — web_     │ │ — parse_doc_   │    │ retrieve_similar_ │
  │ search(),  │ │ or_image()      │    │ products()        │
  │ fetch page │ │ (Qwen3-VL-4B    │    │ (hybrid RAG),      │
  │            │ │  via HF API)    │    │ save_structured_   │
  │            │ │                 │    │ output() (schema +  │
  │            │ │                 │    │ validation)          │
  └───────────┘ └───────────────┘    └─────────────────┘
        (each subagent call passes through the guardrail
         middleware layer, same as a direct tool call)
                                  │
                                  ▼
                     ┌─────────────────────────┐
                     │  Supabase Postgres        │
                     │  (persistent product DB)  │
                     └─────────────────────────┘

                     LangSmith traces every agent
                     run + tool call for observability
                     and evaluation.

              Deployment: single HF Space (Docker),
              Streamlit + FastAPI + agent all in one container.
```

---

## Components

### 1. Agent framework — deepagents + LangGraph
- One **orchestrator agent** using `deepagents`' native subagent support, rather than a flat single-agent toolbelt or a heavy custom multi-agent graph — this keeps the architecture simple while still isolating concerns.
- **Subagents:**
  - **Scraping subagent** — handles web search + fetching manufacturer/catalog pages.
  - **Parsing subagent** — handles document/image understanding via Qwen3-VL-4B (calls the HF Inference API).
- The orchestrator calls subagents for discovery/extraction work, and calls `retrieve_similar_products()` (hybrid RAG) and `save_structured_output()` directly as its own tools, since those are shared/cross-cutting rather than specific to scraping or parsing.
- LangGraph runs underneath `deepagents` for the loop/graph engineering; no custom graph was hand-built on top of it.

### 2. API layer — FastAPI
- FastAPI exposes the agent as HTTP endpoints (e.g. `/process-product`, `/batch`) that the Streamlit UI calls.
- Keeps the agent logic decoupled from the UI layer.

### 3. Document understanding — Qwen3-VL-4B-Instruct
- Vision-language model from Hugging Face, used for document/catalog parsing (reads PDFs, spec-table images, catalog screenshots and extracts structured content).
- Called via the **HF Inference API** — no local GPU hosting.
- Note: fine-tuning this model was discussed (transformers + peft/LoRA + trl, QLoRA on a free Colab/Kaggle GPU) as a possible stretch goal if base-model accuracy is insufficient on real catalog data — but a fine-tuned/custom checkpoint is **not servable via the free HF Serverless Inference API**, so this would require a paid Inference Endpoint or self-hosting (e.g. HF Space with GPU) if pursued.

### 4. Retrieval — Hybrid Agentic RAG
- "Agentic" — the agent decides *when* to retrieve (e.g. on an unfamiliar product), rather than always retrieving.
- "Hybrid" — combines two retrieval strategies inside one `retrieve_similar_products()` tool:
  - **Sparse/exact leg:** exact MPN lookup (SQLite) — handles the fact that part numbers are lexical codes, not semantic concepts.
  - **Dense leg:** semantic similarity search over product descriptions/specs (ChromaDB) — fallback when there's no exact match.
  - Simple merge rule: exact MPN match wins (high confidence); otherwise fall back to top-k semantic results.
- Vector store grows as validated products are saved, so retrieval gets more useful (and processing gets cheaper) as the catalog run progresses — supports the "scale" and "consistency" judging criteria.

### 5. Guardrails — LangChain middlewares
- AI guardrails for data security implemented as LangChain middleware wrapping tool calls / agent I/O:
  - Input sanitization on scraped/uploaded content before it reaches the agent's context (basic prompt-injection hygiene).
  - Output schema validation on `save_structured_output` (reject/flag anything that doesn't match the target schema).
  - No secrets/PII forwarded into LangSmith traces.

### 6. Observability & evaluation — LangSmith
- Tracing enabled from Day 1 (env vars only, near-zero setup cost).
- Used to debug agent tool-selection behavior and loop performance during testing.
- Also used for evaluation of agent performance (accuracy/consistency of structured outputs across test runs).

### 7. Persistence — Supabase
- Supabase Postgres stores processed product records and the exact-match (MPN) lookup used by the sparse retrieval leg.
- This replaces local SQLite so catalog data is durable outside the app container and easier to inspect during judging.
- The products table stores normalized lookup columns plus the validated structured payload as JSONB. A future pgvector column or companion table can power dense semantic retrieval directly in Supabase.

### 8. Deployment — HF Spaces (Docker)
- Single Space, Docker-based, hosting Streamlit UI + FastAPI backend + agent together.
- Supabase provides durable persistence, so the app no longer depends on HF Spaces attached storage for product data.

---

## Toolbelt

| Owner | Tool | Purpose |
|---|---|---|
| Scraping subagent | `web_search()` | Discover manufacturer pages/catalogs for a given product |
| Parsing subagent | `parse_doc_or_image()` | Extract structured content from PDFs/images via Qwen3-VL-4B (HF Inference API) |
| Orchestrator | `retrieve_similar_products()` | Hybrid (exact + semantic) lookup against previously processed products |
| Orchestrator | `save_structured_output()` | Validates against target schema, writes to SQLite, embeds into ChromaDB for future retrieval |

All tool/subagent calls pass through the guardrail middleware layer.

---

## Open items / not yet decided
- Exact structured-output schema (fields, categories, units) — not finalized in discussion.
- Whether fine-tuning Qwen3-VL-4B will actually be pursued, and if so, how the fine-tuned checkpoint will be served (Endpoint vs self-hosted Space with GPU).
- Full FastAPI endpoint list.
- Final day-by-day build schedule incorporating all components above (last full draft covered VLM + hybrid RAG additions but predates the FastAPI layer and guardrail middleware specifics).
