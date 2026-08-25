# Illustrative examples (from an unrelated project)

> ⚠️ Everything in this file comes from a **different, fictional project** (a booking app with a FastAPI backend and a database). This project doesn't have that domain, that framework, or a database yet. Nothing here should be copied as-is — use it only to see the *shape* a good glossary entry, docstring, or workflow can take once this project actually has the equivalent pieces.

## Glossary entry example

```markdown
## Booking

### Session

A bookable time slot led by a host. Not to be confused with an authentication session.

- **Invariants:** cannot be booked once started; capacity is fixed at creation.
- **Used in:** `app/domain/booking/models.py`, `screens/SessionDetail.tsx`
```

## Docstring example (FastAPI endpoint)

```python
@router.post("/bookings", response_model=BookingResponse)
async def create_booking(payload: BookingRequest) -> BookingResponse:
    """Create a booking.

    Enforces the no-overbooking invariant: returns 409 if the session
    is full and 422 if the session has already started.
    """
```

Note what this docstring does *not* do: it doesn't restate that `payload` is a `BookingRequest` (the signature already says that), and it doesn't describe how the check is implemented — just the guarantee it provides.

## Optional: opening a docs PR

If and when this project wants documentation changes to go through their own branch/PR instead of being edited in place, a generic shape looks like:

```bash
git checkout -b docs/update-<short-topic>
git add <changed documentation files>
git commit -m "docs: <short summary>"
git push -u origin HEAD
# then open a PR through whatever tool/workflow this project actually uses
```

This is a placeholder shape, not a prescribed workflow — adapt it (or drop it entirely) to match how this project actually manages branches and PRs when that's decided.
