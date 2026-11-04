# API_CONTRACT.md — AnchorDraft (Phase 3)

**Status:** DRAFT for review, revision 1. Planning document written on 3 Nov 2026, before the Round 2 build window opens (4 Nov 10:00). It contains no application code. Field tables describe request and response shapes; they are specifications, not implementations. Items marked **ASSUMPTION** are proposals to be tuned; items marked **VERIFY** must be checked against current documentation.

**Companion documents:** `ARCHITECTURE.md` (Phase 1), `DATA_MODEL.md` (Phase 2), `REVIEW_ENGINE.md` (Phase 4). Still to write: build plan (Phase 5), disclosure log (Phase 6).

---

## 1. Surfaces

AnchorDraft has three ways to read or change data. Keeping them separate is what keeps the Python service small.

| Surface | Used for | Authority |
|---|---|---|
| **Review service** (FastAPI, `/v1`) | Starting reviews, text import, kit lint, health | Service role key; verifies the caller itself |
| **Database functions** (Supabase RPC) | Every workflow state change | `SECURITY DEFINER` functions; check role and state themselves |
| **Direct reads** (Supabase client under RLS) | Lists, detail screens, insights, review status, comments | Row Level Security |

The browser never calls the model provider and never holds a service key.

## 2. Conventions

- **Base path:** `/v1`. Additive changes only within a version.
- **Format:** JSON, UTF-8. Field names are `snake_case`. IDs are UUIDs. Timestamps are ISO 8601 in UTC.
- **Request ID:** every request may carry `X-Request-Id`; the service generates one if absent and returns it in the header and in every error body.
- **Text offsets:** all offsets (`start_offset`, `end_offset`) count **Unicode code points**, not UTF-16 code units. JavaScript strings count UTF-16 units, so the web app must convert before highlighting text that contains emoji or other astral characters. End offsets are exclusive.
- **Line endings:** text is normalised to `\n` before storage and before review.
- **Size caps (ASSUMPTIONS):** revision body 20,000 characters; comment 2,000 characters; upload 5 MB and 20 pages; request body 6 MB.
- **API documentation:** the service publishes its OpenAPI description (FastAPI default). It contains no secrets and doubles as the "APIs used" disclosure.

## 3. Authentication and authorisation

### 3.1 Review service
1. The client sends `Authorization: Bearer <Supabase access token>`.
2. The service verifies the signature, expiry and audience of the token (VERIFY the current Supabase method for signing keys). Failure returns `401 unauthenticated`.
3. The service takes the user ID from the token only.
4. The service loads the target row with the service role key, **derives the organisation from that row**, and checks the caller's membership and roles itself. The request body never carries an `org_id`.
5. Rows belonging to another organisation return `404 not_found`, not `403`, so existence is not leaked.

### 3.2 Database functions
Called by the signed-in browser client. Each function reads `auth.uid()` itself and applies the hardening rules in `DATA_MODEL.md` section 8.4.

### 3.3 CORS
Only the deployed web origin and `http://localhost` development origins (configured, not hard-coded). No wildcard.

## 4. Error model

### 4.1 Review service
```json
{ "error": { "code": "conflict", "reason": "not_latest_revision", "message": "Only the latest revision can be reviewed.", "request_id": "…", "retry_after_seconds": null } }
```
`reason` and `retry_after_seconds` are present only when they apply. `message` is safe to show to a user and never contains provider error text, stack traces, draft text or guideline text.

| Code | HTTP | When |
|---|---|---|
| `unauthenticated` | 401 | missing, invalid or expired token |
| `forbidden` | 403 | member of the organisation but lacking the required role |
| `not_found` | 404 | no such row, or the row belongs to another organisation |
| `conflict` | 409 | state does not allow the action; see `reason` values below |
| `too_large` | 413 | body, file or text over the caps |
| `unsupported_media_type` | 415 | upload is not a PDF or DOCX |
| `validation_error` | 422 | malformed or out-of-range input |
| `rate_limited` | 429 | daily review cap, per-user rate limit, or model quota backoff |
| `upstream_unavailable` | 503 | the database cannot be reached |
| `internal_error` | 500 | unexpected failure; the request ID is the only detail returned |

**`conflict` reasons:** `not_editable`, `not_latest_revision`, `no_active_kit`, `kit_too_large`, `no_extractable_text`.

### 4.2 Database functions
A function raises an exception whose message starts with a code, optionally followed by a reason, for example `conflict:pending_signoffs`.

| Message prefix | Meaning |
|---|---|
| `unauthenticated` | no signed-in user |
| `forbidden` | wrong role for this organisation |
| `not_found` | row missing |
| `conflict:<reason>` | state does not allow it |
| `validation:<field>` | bad input |

**Function `conflict` reasons:** `not_editable`, `not_latest_review`, `not_submitted`, `findings_undecided`, `changes_pending_apply`, `llm_failed`, `no_review`, `pending_signoffs`, `no_changes`, `not_draft_kit`, `empty_kit`.

VERIFY how these exceptions surface in the browser client, then add a small mapping layer in the web app.

## 5. Review service endpoints

### 5.1 `POST /v1/reviews` — start a review

| | |
|---|---|
| Who | a member with the `creator` role |
| Purpose | review one revision against the active kit |
| Idempotent | yes (see below) |

**Request**

| Field | Type | Rules |
|---|---|---|
| `revision_id` | uuid | required |

**Checks, in order**
1. Token valid; revision found; caller is a member and has `creator` (`401`, `404`, `403`).
2. The revision is the latest revision of its content, and the content status is `draft` or `changes_requested` (`409 not_latest_revision` or `not_editable`).
3. The organisation has an active kit (`409 no_active_kit`) and the kit fits the prompt cap (`409 kit_too_large`).
4. Idempotency: if a review for this revision is `queued` or `running`, or the latest one is `done` with `llm_status` of `ok` or `skipped`, return it with `deduplicated: true` and HTTP `200`. A new review is created only if there is none, or the latest one failed or has `llm_status = failed`.
5. The organisation is under `DAILY_REVIEW_CAP` and the user is under the per-user rate limit (`429` with `retry_after_seconds`). Deduplicated responses do not count against the cap.

**Response** — `202` for a new review, `200` when deduplicated.

| Field | Type | Notes |
|---|---|---|
| `review_id` | uuid | |
| `status` | string | `queued`, `running` or `done` |
| `deduplicated` | boolean | |
| `kit_id` | uuid | the kit version this review uses |
| `kit_version` | int | |

The service creates the `reviews` row, returns immediately, and runs the pipeline in a background task (stages and the validator are specified in Phase 4).

### 5.2 `POST /v1/imports/text` — extract text from a file

| | |
|---|---|
| Who | a member with the `creator` or `owner` role |
| Purpose | turn an uploaded PDF or DOCX into plain text for a draft |
| State | none: nothing is stored and nothing is logged |

**Request:** `multipart/form-data` with one field, `file`, plus `org_id` as a form field used **only** to check that the caller is a member of that organisation with a suitable role.

**Response `200`**

| Field | Type | Notes |
|---|---|---|
| `text` | string | normalised, control characters removed, at most 20,000 characters |
| `pages` | int | |
| `char_count` | int | length of `text` |
| `truncated` | boolean | true when the text was cut to the cap |
| `warnings` | string[] | for example "no text found on page 3 (possibly scanned)" |

**Errors:** `413 too_large`, `415 unsupported_media_type`, `409 no_extractable_text` (for example a scanned PDF), `422 validation_error`.

### 5.3 `POST /v1/kits/{kit_id}/lint` — check a draft kit

| | |
|---|---|
| Who | a member with the `owner` role in the kit's organisation |
| Purpose | find problems before activation |
| State | read-only |

**Response `200`**

| Field | Type | Notes |
|---|---|---|
| `ok` | boolean | false if any issue has severity `error` |
| `issues` | object[] | `{severity: "error" or "warning", code, ref_key or null, message}` |
| `stats` | object | `{rules, facts, llm_rules, deterministic_rules, prompt_chars_estimate, prompt_chars_cap}` |

**Checks:** deterministic rule `config` is valid; the kit fits the prompt cap; facts past `valid_until`; rules with empty guideline text; a kit with no rules. Activation (`activate_kit`) enforces only structural conditions in the database; the web app runs lint first and shows the result.

### 5.4 `GET /v1/health` — liveness and warm-up

Public. Returns `{status: "ok", version, time}`. With `?deep=1` it also reports `{database: true or false}` and never calls the model provider (cost). Deep checks are rate-limited. The web app calls this on load to wake a cold free-tier instance.

## 6. Review lifecycle

```
POST /v1/reviews → reviews.status = queued → running → done | failed
                                       llm_status: ok | skipped | failed
```

| Situation | `status` | `llm_status` | Findings | `warnings` |
|---|---|---|---|---|
| Everything worked | `done` | `ok` | deterministic + validated model findings | empty |
| Kit has no model-checked rules | `done` | `skipped` | deterministic only | empty |
| Model call failed or timed out | `done` | `failed` | deterministic only | "model unavailable: deterministic checks only" |
| Revision could not be loaded or a database error stopped the run | `failed` | `failed` | none | safe error text in `error` |

- **How the browser follows progress:** it reads the `reviews` row through Supabase and subscribes to Realtime changes for that row. If Realtime is unavailable it polls every 3 seconds (ASSUMPTION).
- **Retry:** call `POST /v1/reviews` again. A new review row is created when the last one failed or has `llm_status = failed`.
- **Timeouts (ASSUMPTIONS):** 90 seconds for the whole review, 45 seconds for the model call, one retry on a transient model error.
- **Concurrency (ASSUMPTION):** at most 2 simultaneous model calls across the service, FIFO. Extra reviews wait as `queued`. Free-tier model quotas are low (VERIFY), and a quota error is treated like any model failure.
- **Stuck jobs:** a review in `running` for more than 5 minutes is marked `failed` by the startup sweep and by a lazy check on read.
- **Reproducibility:** each review stores the kit, `model`, `prompt_version` and `engine_version`.

## 7. Database function contract

All functions are atomic, run as `SECURITY DEFINER`, and follow the hardening rules in `DATA_MODEL.md` section 8.4. Parameters are named as shown. "Content editable" means status `draft` or `changes_requested`.

### 7.1 `create_content`
`create_content(_org uuid, _title text, _channel text, _purpose text, _body text) → {content_id, revision_id}`
- Role: `creator` in `_org`.
- Guards: title 1–200 characters; channel in the allowed list; purpose 1–1,000 characters; body 1–20,000 characters.
- Effect: inserts the content (`draft`) and revision 1 (source `manual`).

### 7.2 `create_revision`
`create_revision(_content_id uuid, _body text) → {revision_id, version}`
- Role: `creator`.
- Guards: content editable; body 1–20,000 characters and different from the latest revision.
- Effect: inserts the next revision (source `manual`, parent = latest). If the status was `changes_requested`, it becomes `draft`.

### 7.3 `record_decision`
`record_decision(_finding_id uuid, _action decision_action, _reason text default null, _edited_text text default null) → {decision_id}`
- Role: `creator`.
- Guards: content editable; the finding belongs to the **latest review of the latest revision**; `dismiss` needs a non-empty reason (at most 1,000 characters); `edit` needs `_edited_text` (at most 2,000 characters); `accept` needs the finding to have a suggestion.
- Effect: appends a decision. A finding may be decided again; the latest decision wins.
- It does not create a revision.

### 7.4 `apply_decisions`
`apply_decisions(_content_id uuid) → {revision_id, version, applied, skipped[]}` where each skipped item is `{finding_id, reason}`.
- Role: `creator`.
- Guards: content editable; at least one pending accepted or edited decision (`409 no_changes` otherwise).
- Effect, inside one transaction with the content row locked:
  1. Collect the latest decision per finding from the latest review of the latest revision where the action is `accept` or `edit` and `resulting_revision_id` is null.
  2. Order by `start_offset` descending.
  3. For each, confirm the text at `[start_offset, end_offset)` still equals the finding's `quote`. If not, skip with reason `text_changed`. If its range overlaps one already applied, skip with reason `overlap`.
  4. Replace the range with the suggestion (`accept`) or the creator's edited text (`edit`).
  5. Insert the new revision (source `accepted_suggestion`, parent = latest), set `resulting_revision_id` on the applied decisions, and move `changes_requested` to `draft`.
  6. Reject the whole call (`validation:body`) if the new text would exceed the cap.
- The server builds the new text; the client never sends it, so it cannot be tampered with.
- The web app then calls `POST /v1/reviews` for the new revision.

### 7.5 `submit_content`
`submit_content(_content_id uuid) → void`
- Role: `creator`. Status must be `draft`.
- Guards: the latest revision has a review (`conflict:no_review`) that is `done` with `llm_status` of `ok` or `skipped` (`conflict:llm_failed`); every finding in it has a decision (`conflict:findings_undecided`); no accepted or edited decision is waiting to be applied (`conflict:changes_pending_apply`).
- Effect: status becomes `submitted`; audit row written.

### 7.6 `request_changes`
`request_changes(_content_id uuid, _note text) → void`
- Role: `manager`. Status must be `submitted`. Note 1–2,000 characters.
- Effect: appends an approval row (`request_changes`) and sets status `changes_requested`.

### 7.7 `record_signoff`
`record_signoff(_finding_id uuid, _action approval_action, _note text default null) → void`
- Role: `reviewer`. `_action` must be `signoff` or `reject_claim`.
- Guards: content status `submitted`; the finding has `needs_reviewer` and belongs to the latest review of the latest revision; `reject_claim` needs a note.
- Effect: appends an approval row. `reject_claim` also sets status `changes_requested`.

### 7.8 `approve_content`
`approve_content(_content_id uuid) → void`
- Role: `manager`. Status must be `submitted` (`conflict:not_submitted`).
- Guards: no pending sign-offs (`conflict:pending_signoffs`). Sign-offs are required for every `needs_reviewer` finding in the latest review, whatever the creator decided.
- Effect: appends an approval row (`approve`) for the latest revision and sets status `approved`.

### 7.9 `clone_kit`
`clone_kit(_kit_id uuid) → {kit_id, version}`
- Role: `owner`.
- Effect: creates a new `draft` kit with `version = max + 1`, `source_kit_id` set, and copies of all rules and facts (same keys).

### 7.10 `activate_kit`
`activate_kit(_kit_id uuid) → void`
- Role: `owner`. Kit must be `draft` (`conflict:not_draft_kit`) with at least one rule (`conflict:empty_kit`).
- Effect: archives the previous active kit, sets this kit `active` and stamps `activated_at`.

### 7.11 Service-only function (review service, not callable by users)
`engine_complete_review(_review_id, _status, _llm_status, _warnings, _raw, _dropped, _validator_stats, _model, _prompt_version, _findings jsonb)` writes all findings and the review result in one transaction; a failure form marks a review `failed` with a safe error. Execute permission is granted only to the service role (VERIFY). Specified in `REVIEW_ENGINE.md` section 8.

## 8. Direct reads and writes from the browser

Under RLS, with no custom endpoint:

| Need | How |
|---|---|
| Content list and detail | `select` on `contents`, `revisions` (or `v_latest_revision`) |
| Findings with current state | `select` on `v_finding_state` |
| Review status | `select` on `reviews` plus a Realtime subscription on the row |
| Kit, rules, facts | `select`; the owner writes `rules` and `approved_facts` of **draft** kits directly |
| Comments | `insert` on `comments` as the signed-in user; `select` |
| Insights | `select` on `v_rule_stats`, plus aggregate queries on `reviews` for the validator-drop rate |
| Audit trail | `select` on `audit_log` (managers and owners) |

## 9. Data shapes inside the review service

Specified here so Phase 4 and the tests share one definition. They are internal; the browser reads the stored rows.

### 9.1 Pipeline `Finding` (what the validator hands to the writer)

| Field | Type | Rules |
|---|---|---|
| `source` | `deterministic` or `llm` | |
| `rule_key` or `fact_key` | string | exactly one; must exist in the review's kit |
| `category`, `severity` | enums | copied from the rule (facts use category `fact`) |
| `quote` | string | 4 to 300 characters for model findings (deterministic findings are exempt from the minimum); must occur in the revision body |
| `start_offset`, `end_offset` | int | computed by the server in code points; `0 <= start < end <= len(body)` |
| `explanation` | string | non-empty |
| `suggestion` | string or null | |
| `confidence` | float or null | 0.0 to 1.0 |
| `needs_human` | boolean | true when low-confidence or ambiguous |
| `needs_reviewer` | boolean | true for claim and fact findings (from the rule, or always for facts) |

### 9.2 Validator outcome
Each candidate finding is either **kept** or **dropped** with one reason: `schema_invalid`, `unknown_ref`, `ref_mismatch`, `quote_not_found`, `duplicate`, `too_many`. The counts feed `llm_findings_raw`, `llm_findings_dropped` and `validator_stats` on the review. A quote that appears more than once is anchored to the first occurrence not already used by another finding with the same key (`REVIEW_ENGINE.md` section 7.2).

## 10. Limits and controls (ASSUMPTIONS, configurable)

| Control | Value |
|---|---|
| Reviews per organisation per day | 20 (`DAILY_REVIEW_CAP`) |
| Requests per user per minute on the review service | 10 |
| Simultaneous model calls | 2 |
| Whole-review timeout / model-call timeout | 90 s / 45 s |
| Revision body / comment length | 20,000 / 2,000 characters |
| Upload size / pages | 5 MB / 20 pages |
| Kit prompt cap | set in Phase 4 after measuring a realistic kit |

## 11. Privacy and logging contract

- Logs contain request IDs, user and organisation IDs, durations, counts and error codes. **They never contain draft text, guideline text, quotes, suggestions or model responses.**
- Uploaded files are processed in memory and discarded.
- The only data sent to the model provider is the revision text, the stated purpose, and the rules and facts of the active kit. Sending is disclosed in the interface and in the project documentation.
- Error messages shown to users never include provider or database internals.

## 12. Contract tests to write

- Authentication: missing, malformed and expired tokens return `401`.
- Cross-organisation access returns `404`, and a wrong role returns `403`.
- `POST /v1/reviews`: not-latest revision; content not editable; no active kit; deduplication; cap reached; `llm_status = failed` creates a new review on retry.
- Partial result: with a fake provider that fails, the review ends `done` with deterministic findings and a warning.
- Every database function has negative tests for wrong role, wrong organisation and wrong state.
- `apply_decisions`: several accepted findings, overlapping ranges, text that changed since review, and text containing emoji (code-point offsets).
- `submit_content` and `approve_content` guards, including pending sign-offs and `llm_failed`.
- Logging: a test that fails if draft text appears in log output.

## 13. Open questions

- **Q1 — Who may start a review.** Currently only `creator`. *Keep, for Tier 1.*
- **Q2 — Quote that appears more than once.** *Decided in Phase 4: first unused occurrence for the same key.*
- **Q3 — Realtime or polling.** *Use Realtime, with polling as a fallback.*
- **Q4 — Multi-organisation users.** `create_content` takes `_org`; the web app needs an organisation switcher only if a user belongs to more than one. *Single organisation in the demo.*

## 14. Items to VERIFY

1. How the service should verify Supabase tokens (current signing-key approach).
2. How raised database exceptions reach the browser client.
3. Realtime delivery with RLS on the `reviews` table.
4. Free-tier Render behaviour: background tasks after the response, and cold starts.
5. Gemini quotas, model names and the current Python SDK (settled at the provider spike, `REVIEW_ENGINE.md` section 3).

## 15. Review checklist (for the architect)

- [ ] Can I explain every endpoint and function and say why it exists?
- [ ] Is there any way to change workflow state that bypasses the ten functions?
- [ ] Does each error path avoid leaking draft text, provider errors or other organisations' data?
- [ ] Does the partial-result path work when the model is down at demo time?
- [ ] Can the web app render highlights correctly from code-point offsets?
- [ ] Is every ASSUMPTION either accepted or replaced with a measured value?
