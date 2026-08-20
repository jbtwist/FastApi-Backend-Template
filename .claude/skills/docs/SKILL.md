---
name: docs-write
description: >-
  Write and update project documentation (narrative docs, Python docstrings,
  TSDoc comments) following a consistent conversational style and the project's
  ubiquitous language. Use after a PR is merged to main, or when explicitly
  asked to create/edit documentation, docstrings, or TSDoc comments.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Documentation Writing Skill

Covers narrative docs (README, guides, changelog) and in-code docs (Python
docstrings, TSDoc) that feed `mkdocstrings`/TypeDoc. Runs unattended after
merges to `main`.

## Scope

- Manual invocation → only the requested file/topic.
- Auto invocation (post-merge) → only the diff of that PR. Never touch
  business logic, only docs/docstrings/TSDoc/`/docs`.
- Read `/GLOSSARY.md` first. Doesn't exist? Create it (§4).

## Narrative docs

**Ask first:** Who's reading this? What do they need? What would trip up a
new contributor?

**Draft → Edit → Polish:**
- Draft like you're telling a colleague. Lead with the action, explain after.
  Headings state a point ("Set the base URL before running" not "Config").
- Edit: sound like a person, not a memo. One purpose per paragraph. Cut
  anything that doesn't help the reader. Verify examples against the diff.
- Polish: descriptive links (never "here"), backticks for code, **bold** for
  UI elements, American spelling, avoid numbers that will age badly.

**Avoid:** calling things "easy", corporate filler ("utilize", "leverage"),
burying the action in a paragraph, inventing behavior not in the diff.

## Python docstrings (FastAPI / Pydantic)

Google-style, written for the rendered `mkdocstrings` page:

- Path operations: one-line imperative summary + non-obvious error codes.
- Pydantic fields: `Field(..., description=...)` for anything non-obvious —
  don't restate the type.
- **Aggregate Roots** (`Booking`, `Session`, etc.): document the *invariant*
  each validator protects, not just the check. "Prevents booking a session
  that's already started" — not "must be in the future".

```python
class BookingRequest(BaseModel):
    session_id: int = Field(
        ..., description="Session to book. Must not have started yet — "
        "this is what prevents booking sessions already in progress."
    )

@router.post("/bookings", response_model=BookingResponse)
async def create_booking(payload: BookingRequest) -> BookingResponse:
    """Create a booking. Enforces "no overbooking": 409 if the session is
    full, 422 if it's in the past."""
```

## TSDoc (React Native / TypeScript)

Same rule, feeds TypeDoc:

- Every exported component/hook/util gets a one-line `/** */` summary.
- Components: document non-obvious props and side effects (navigation,
  storage, network).
- Hooks: what triggers a re-render, and any cleanup.
- Only add `@param`/`@returns` when the name/type isn't enough alone.

```ts
/**
 * Counts down to a booked session; auto-cancels if the user doesn't
 * check in within the grace period.
 */
export function useBookingCountdown(graceMinutes: number) { ... }
```

## Ubiquitous language & `/GLOSSARY.md`

A term must mean the same thing everywhere — code, docs, comments. This
skill owns the glossary and keeps it current.

**Structure**, organized by bounded context (a term can mean different
things in different contexts):

```markdown
## Booking

### Session
A bookable time slot led by a host. Not to be confused with an auth session.

- **Invariants:** can't be booked once started; capacity fixed at creation.
- **Used in:** `app/domain/booking/models.py`, `screens/SessionDetail.tsx`
```

No clear contexts yet? Use one `## Core` section until boundaries emerge.

**Keep it updated:** new domain concept in the diff → add an entry. Existing
concept touched → update its invariants/use sites. Already-defined term →
always use the glossary's wording.

**Discrepancy found** (code says `Client`, glossary says `Customer`)? This
is a flag, not an edit:
- Never rename anything, in code or in the glossary, to reconcile it.
- Mark the entry: `> ⚠️ Naming discrepancy — code uses "Client", glossary
  defines "Customer". Needs a dedicated PR.`
- Put it first in the PR description (§ below) — before the summary.
- Renaming a glossary term is human-only, via its own dedicated PR.

## Post-merge guardrails

1. Read only the merged PR's diff.
2. Update docstrings/TSDoc/narrative docs it touches, and `/GLOSSARY.md`.
3. Never: touch logic, invent behavior, merge your own PR, rename a
   glossary term.
4. Unclear something? Leave a `TODO`, don't guess.
5. Open the PR yourself:
   ```
   git checkout -b docs/update-after-<pr-number>
   git add <changed files>
   git commit -m "docs: update after #<pr-number>"
   git push -u origin HEAD
   gh pr create --title "docs: sync after #<pr-number>" \
     --body "⚠️ Naming discrepancies: <list, or 'none'>. Summary: <...>. \
   TODOs: <list, or 'none'>."
   ```
   Discrepancies go first in the body, always.

## Quick reference

| Write This | Not This |
|---|---|
| Set the base URL before running | Configuration |
| Check out [the API docs](link) | Click [here](link) |
| Fails with 409 if already booked | (undocumented error code) |
| `Customer` (matches glossary) | `Client`/`User` interchangeably |
| Flag a discrepancy in the PR | Rename it yourself to "fix" it |
