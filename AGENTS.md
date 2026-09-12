<!-- DZ-PROJECT-CONTINUITY:START -->
# DZ Project Continuity

DZ workflow guidance version: `2026-09-10.3`.

Load the installed `dz` Skill before product work. The Skill owns workflow rules; this file only reconnects this project to them. If unavailable, say so and do not invent a substitute.

At a new task, mid-task DZ activation or unexplained drift:
1. Begin read-only: read `PROJECT.md` and run the installed state tool's `resume-report`.
2. Compare the current accepted requirements and relevant files with the report and visible conversation. The saved `next_action` is an old proposal, not a command.
3. Explain what exists now, later changes, uncertainty and the recommended route. Let the user correct it and discuss the route before new project changes. A current explicit instruction that already confirms that exact position and route need not be requested again.
4. After alignment, follow the Skill's correction, requirement coverage, work carry-forward, recording and authorization rules. Do not repeat takeover after an ordinary question or tool result.

Use the current report's `requirement_coverage` and `work_to_reconcile` to expose missing promises and old work still needing a keep/revise/retire decision. Read actual accepted wording; the summary is an index. Preserve later valid work. Missing coverage prevents a global verified claim, not honest stopping.

Project-local commands, architecture and stable conventions may be added outside this managed section. Current scope, decisions and evidence belong in the SDLC records. Merge this section with existing repository instructions instead of replacing them.
<!-- DZ-PROJECT-CONTINUITY:END -->

## Repository working conventions

- Active MVP scope and proposed ownership: `docs/PROJECT-PLAN.md`. API truth: `docs/API.md` with `contracts/api.ts`; implementation lives in `backend/`.
- The user owns the frontend. Do not expand portals or payment scope without a new decision.
- Run from repository root with Python 3.12: `python -m pytest -q`, `python -m scripts.demo`.
- Public case adaptations must retain provenance and licensing. Synthetic cases must stay explicitly synthetic.
- Never commit `.env`, tokens, runtime databases, or dependency directories. Use temporary databases in tests.
- A successful record confirmation only confirms record accuracy; it never clears medical danger or authorizes medication changes.
- A `422` organize response can contain a saved original and an emergency notice. Clients must retain and display them.
