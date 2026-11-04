# AGENTS.md — operating instructions for the coding agent

This file governs how you work in this repository. Read it fully before doing anything, and re-read it at the start of every session.

## 0. The project in three sentences
AnchorDraft is a pre-publication brand-governance platform for startups: a Guideline Owner loads numbered rules and approved facts, creators submit drafts, and a review engine returns findings that each cite a real rule or fact and a real quote from the draft. Humans decide every finding and approve content through a role-based workflow. This repository is a solo hackathon entry (team "Axial", CodeNexus India 2026, problem by Inkloom AI); the build window is 4 Nov 10:00 to 7 Nov 10:00.

## 1. The specification
These documents in `docs/` are the specification. **They win over your assumptions and your habits.**
1. `ARCHITECTURE.md` — objectives, components, trust boundaries, decisions, build slices.
2. `DATA_MODEL.md` — tables, invariants, access control, workflow functions.
3. `API_CONTRACT.md` — review service endpoints, error model, database function contract.
4. `REVIEW_ENGINE.md` — pipeline, deterministic checks, prompt, validator, provider adapter.

If something is missing, ambiguous or looks wrong, **stop and ask**. Do not silently fill gaps. If you believe the specification should change, say so and propose the change; do not make it yourself.

## 2. Who decides
The architect (the human, Siddhartha) decides. You propose and implement. Any deviation from the specification needs his explicit approval and must be recorded in `docs/ai-log/decisions.md` (date, what, why, who approved).

## 3. How we work: one slice at a time
The slices are in `ARCHITECTURE.md` section 5.3. For each slice:
1. **Plan.** Restate the slice's acceptance criteria and your plan in ten lines or fewer. **Wait for approval.**
2. **Branch.** Work on `slice-<n>-<short-name>`.
3. **Implement with tests.** Write tests alongside the code (section 7).
4. **Report.** Summarise: what changed, which commands you ran and their real output, what you did *not* verify, risks, and "how it works" in five bullets so the architect can explain it to a judge.
5. **Stop.** Do not start the next slice until the architect has reviewed and merged.

## 4. Commits
- Small, reviewable commits (aim for under about 300 changed lines). No large dumps of unreviewed code.
- Conventional messages: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.
- Never rewrite history, never backdate, never force-push shared branches. Commit history is evidence for the judges.
- Never commit secrets, `.env` files, keys, tokens or personal data.

## 5. Truthfulness (non-negotiable)
- **Never claim something works unless you ran it.** Show the command and the real output.
- **Never invent** library names, versions, API parameters, model names, SQL features or configuration keys. Look them up from the real package index or official documentation, and cite where you looked. Items marked **VERIFY** in the specification must be verified before use. If you cannot verify, say so plainly.
- Pin dependency versions only from what the package index actually reports.
- If a test fails or you are unsure, report it. Do not hide it, skip it or weaken it.

## 6. Security rules (non-negotiable)
1. No secrets in the repository. `.env.example` lists variable **names only**.
2. The service role key and the LLM provider key exist only in the review service's environment. The browser never holds them and never calls the LLM.
3. The review service never accepts `org_id` or a role from the client. It derives them from the verified token and the database.
4. Every table has Row Level Security. All workflow state changes go through the database functions in `DATA_MODEL.md` section 8.4, following all nine hardening rules. Users have no direct write access to workflow tables.
5. **Never log draft text, guideline text, quotes, suggestions or model responses.** Logs hold IDs, counts, durations and error types only. A test enforces this.
6. Draft and guideline text are untrusted data. Never put them where they could act as instructions. The prompt uses per-request nonce boundaries (see `REVIEW_ENGINE.md` section 6.2).
7. Render model explanations and suggestions as plain text, never as HTML.
8. Demo and test data are fictional. Do not add real company or personal data.

## 7. Testing requirements
- Build and test the **citation validator and the deterministic checks first**, against the fake provider, before any real model call.
- Every database function has negative tests: wrong role, wrong organisation, wrong state.
- Property tests for the validator invariants (`REVIEW_ENGINE.md` section 7.4).
- Run the full test suite before every report and include the result.

## 8. Scope guard
- Build **Tier 1 and Tier 2 only** (`ARCHITECTURE.md` and `DATA_MODEL.md`). Tier 3 items and Round 3 features (visual review, redaction layer, guideline-gap clustering) are **not to be built**, even if easy.
- No extra features, no speculative abstractions, no "while I'm here" refactors.
- **Allowed stack:** React 19, Vite, TypeScript, Tailwind CSS 4, Supabase (Postgres, Auth, Storage, Realtime), FastAPI, Pydantic, pypdf, python-docx, pytest, Vitest. A new dependency needs approval, with a one-line reason and its licence.
- External services allowed: Supabase, Vercel, Render, the chosen LLM provider. Nothing else. No analytics or telemetry.

## 9. Code style
- The architect must be able to **explain every line to a judge**. Prefer plain, readable code over clever code.
- TypeScript strict mode. Python with type hints and Pydantic models. Small modules. Feature folders in the web app. Inject clients (Supabase, provider) so they can be faked in tests.
- Comments only where the reason is not obvious from the code.
- Every external call has a timeout and an explicit failure path.

## 10. Records you must keep up to date
- `docs/ai-log/log.md`: after each slice, append an entry (date and time, what you generated, a summary of the key prompts, what the architect changed or rejected).
- `docs/ai-log/decisions.md`: every deviation or new decision.
- `docs/DISCLOSURE.md`: every library, service, template and piece of reused material as it is added. Be accurate; the disclosure is part of the competition rules.

## 11. When you are blocked
Ask one concise question, list the options, and give your recommendation. Do not guess and continue.

## 12. Things you must never do
- Never start coding before the slice plan is approved.
- Never modify the specification documents without approval.
- Never claim a feature is complete if any acceptance criterion is unverified.
- Never paste or request real API keys in conversation; they live in local environment files that are not committed.
