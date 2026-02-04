---
name: Use Gemini Batch API for validation
overview: Implement the real Gemini Batch API in ValidationAgent (instead of the current stub that falls back to concurrent online requests). Use it for large batches (e.g. 100+ files) to get 50% cost savings and higher throughput, with ~24h target turnaround. Keep concurrent online path for small batches and real-time needs.
todos: []
isProject: false
---

# Plan: Use Gemini Batch API for validation

## Summary from Google docs

- **Batch API** ([ai.google.dev/gemini-api/docs/batch-api](https://ai.google.dev/gemini-api/docs/batch-api)): async, **50% cost** vs standard, target **24h** turnaround (often faster).
- **Submit:** Inline list of `GenerateContentRequest` (under 20MB) **or** a **JSONL file** (each line: `{"key": "id", "request": GenerateContentRequest}`) uploaded via File API; max input file **2GB**.
- **Create job:** `client.batches.create(model="models/gemini-2.5-flash", src=inline_list | uploaded_jsonl.name, config={'display_name': "..."})`.
- **Poll:** `client.batches.get(name=job_name)` until `state` in `JOB_STATE_SUCCEEDED`, `JOB_STATE_FAILED`, `JOB_STATE_CANCELLED`, `JOB_STATE_EXPIRED`.
- **Results:** Inline: `batch_job.dest.inlined_responses`; file input: `batch_job.dest.file_name` then `client.files.download(file=...)` (JSONL: each line is response or error for that key).
- **Structured output** and **system instruction** are supported per request. **Multimodal:** requests can reference files uploaded to the File API.

## Current state (ValidationAgent)

- [concurrent_processor.py](C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent\concurrent_processor.py): `should_use_batch_api(len(file_ids))` (threshold 100) calls `process_with_batch_api`, which is a **stub** that falls back to `worker.process_batch()` (concurrent online `generate_content` per file).
- [validate_gemini.py](C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent\validate_gemini.py): Per-file flow: download gs:// → upload PDF to File API → `client.models.generate_content(..., contents=[uploaded_file, user_prompt], config=...)` → cleanup temp and file. Uses [validation_schema.py](C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent\validation_schema.py) (`VALIDATION_SCHEMA`, `validate_result`).

## Target behavior

- **Large batches (e.g. file_count >= 100):** Use **real** Gemini Batch API: build batch input (inline or JSONL), create job, poll until done, then parse results and write to DB (validation_results + optional scraped_files). No per-file online `generate_content` in that path.
- **Small batches or when job_id is missing:** Keep existing concurrent path (online `generate_content` per file).
- **Revalidation script** ([revalidate_missing_metadata.py](C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent\revalidate_missing_metadata.py)): Currently always uses concurrent (calls `validate_with_retry` per row). Optionally add a **batch mode** that submits one Batch API job for all rows (or chunks of e.g. 1000), then polls and patches DB when the job completes (run as a long-lived or scheduled step).

## Implementation outline

### 1. Batch request builder (ValidationAgent)

- **Input:** List of items with `(vr_id, scraped_file_id, gcs_uri, filename)` (or similar).
- **Steps:**
  - For each item: download from gs:// to temp → upload PDF to File API → keep `(key, file_name)` and temp path for later cleanup.
  - Build one `GenerateContentRequest` per item: `contents` = [file part referencing `file_name`, text part = prompt], `config` = response_mime_type `application/json`, response_schema = VALIDATION_SCHEMA, system_instruction, temperature 0. Map key to vr_id (and scraped_file_id, filename) for result handling.
  - If total size of request list &lt; ~20MB: use **inline** `src=inline_requests`. Else: write **JSONL** (each line `{"key": vr_id, "request": {...}}`), upload JSONL to File API, use `src=uploaded_jsonl.name`.
- **Output:** Either `(None, inline_requests, key_to_meta)` or `(uploaded_jsonl_name, None, key_to_meta)`; plus list of uploaded PDF file names (and temp paths) for cleanup. Use google-genai SDK types so each request matches the format expected by `client.batches.create()` (see [Batch API docs](https://ai.google.dev/gemini-api/docs/batch-api) for exact request shape; file references in contents as per “reference other uploaded files within your JSONL”).

### 2. Create batch job and poll (ValidationAgent)

- **New helper** (e.g. in [validate_gemini.py](C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent\validate_gemini.py) or a new `batch_validation.py`): `create_validation_batch_job(client, model, src_inline_or_file_name) -> job_name`; then `poll_batch_job(client, job_name, poll_interval_sec=60) -> batch_job`.
- Use `client.batches.create(model=..., src=..., config={'display_name': 'validation-...'})` and `client.batches.get(name=job_name)` in a loop until state is terminal. Optionally update Firebase/DB “job status” with current batch state (e.g. RUNNING) for UI.

### 3. Parse results and update DB (ValidationAgent)

- **Input:** Completed `batch_job` (state SUCCEEDED), `key_to_meta` (key → vr_id, scraped_file_id, filename).
- **Inline:** Iterate `batch_job.dest.inlined_responses`; order matches request order, so match by index to key if needed, or use metadata in request to embed key.
- **File:** Download result file via `client.files.download(file=batch_job.dest.file_name)`; parse JSONL line by line; each line has key and either response or error. Map key → validation result (parse JSON, run `validate_result`), then for each key update `validation_results` (and optionally `scraped_files`) using existing patch logic from [revalidate_missing_metadata.py](C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent\revalidate_missing_metadata.py) `_process_one` (grade, subject, year, etc.). Record failed keys for retry or manual review.

### 4. Wire into concurrent_processor (ValidationAgent)

- Replace the stub in [concurrent_processor.py](C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent\concurrent_processor.py) `process_with_batch_api`: call the new batch flow (build requests → create job → poll → parse → update DB). Pass `file_ids` and resolve to (gcs_uri, filename) via existing Supabase/build_gcs_uri; for validation worker the “file_id” may map to vr_id or scraped_file_id depending on how the queue payload is shaped — ensure key_to_meta has what’s needed for DB update.
- **Async behavior:** Batch API is async (24h target). So “process_with_batch_api” in the worker can either: (A) **submit and exit:** create job, store job_name in DB/Firebase linked to job_id, return immediately; a separate **polling job or cron** later fetches results and updates DB; or (B) **submit and block:** create job, poll in a loop until done (may run hours), then parse and update DB. Prefer (A) for a worker that should not block for hours; document that “batch_processing” means “job submitted, results will be applied when batch completes.”

### 5. Revalidation script optional batch mode (ValidationAgent)

- Add a flag e.g. `--use-batch-api` to [revalidate_missing_metadata.py](C:\Users\theoc\Desktop\Work\Academy Scrapper\Scapper.Console\ValidationAgent\revalidate_missing_metadata.py): when set, fetch all rows (or up to limit), build one Batch API job (or chunk into multiple jobs by size/count), submit, then either poll until done and patch DB, or write job_name to a file and exit (with instructions to run a “collect batch results” script later). Prefer polling in script for a one-off “revalidate all” run so the same run can apply results.

### 6. Cleanup and errors

- After building batch input: delete temp PDF files; optionally delete uploaded PDFs from File API after job is created (or leave for expiry) to avoid quota. Delete uploaded JSONL file after job creation if desired.
- **Per-request failures:** In Batch API output, some lines may be errors. Map key → error, skip DB update for that key, append to `revalidate_failed_ids.txt` or equivalent. Optionally retry failed keys with concurrent path.

### 7. Dependencies and config

- ValidationAgent already uses `google-genai`; ensure version supports `client.batches.create` and `client.batches.get` (docs indicate GA). No new runtime deps. Optional env: `BATCH_API_THRESHOLD` (default 100), `BATCH_POLL_INTERVAL_SEC` (default 60).

## Order of work (suggested)

1. **Batch request builder + create/poll helpers** in ValidationAgent (new module or validate_gemini): build N requests (download + upload PDF, build GenerateContentRequest with file ref + prompt + schema), create job (inline or JSONL), poll until terminal.
2. **Result parser and DB updater:** From batch_job result (inline or file), parse responses, run validate_result, update validation_results (and scraped_files) per key; collect failures.
3. **Replace stub in concurrent_processor:** `process_with_batch_api` calls the new batch flow; decide submit-and-exit vs submit-and-poll and implement (submit-and-exit + separate collector recommended for worker).
4. **Optional: revalidate_missing_metadata.py --use-batch-api** for one-off full revalidation using Batch API with in-run polling and DB patch.

## Risks / notes

- **24h SLO:** Batch is not for real-time; use only when “process within hours” is acceptable.
- **Idempotency:** Creating a batch job is not idempotent; avoid double-submit for the same logical job.
- **Schema/request format:** Confirm with google-genai SDK how to express file reference + response_schema in a Batch API request (inline and JSONL); docs show `response_mime_type`/`response_schema` in request config.
- **Quota:** Large batches may hit Batch API rate limits; see [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits#batch-mode). Chunking (e.g. 1000 requests per job) keeps single job size manageable.

