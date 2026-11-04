# Agent Instructions

This repository follows the operating instructions in **`docs/AGENTS.md`**.

That file is the authoritative source for how coding agents should work in this repository. All agents must read it fully before doing any work.

## Quick Reference

- **Specification documents** (in `docs/`): ARCHITECTURE.md, DATA_MODEL.md, API_CONTRACT.md, REVIEW_ENGINE.md
- **Work process**: One slice at a time, plan → approve → implement → test → report → stop
- **Commits**: Small, conventional messages, never rewrite history
- **Truthfulness**: Never claim something works unless you ran it; never invent versions or APIs
- **Security**: No secrets in repo; browser never holds service keys; all state changes via DB functions

See `docs/AGENTS.md` for complete instructions.