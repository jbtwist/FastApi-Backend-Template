# Python docstrings for mkdocstrings

Docstrings are the only source of truth for `docs/reference/` — they get rendered directly via the `::: package.module` directive (see main SKILL.md, section 4). Write them for the rendered page, not just for someone reading the source file.

Use Google-style docstrings (matches the `docstring_style: google` option in `assets/mkdocs.yml.example`). If the project later adopts a different style consistently, switch both the docstrings and that config option together — don't mix styles.

## What to document

- A one-line imperative summary ("Create a booking", not "Creates a booking" or "This function creates...").
- Non-obvious behavior — anything a reader couldn't infer from the function name and signature alone.
- Non-obvious error conditions (what triggers them, not just that they exist).
- Business constraints and invariants the function enforces.

## What NOT to document

- Anything the type hints and parameter names already say clearly.
- Implementation details that could change without affecting the contract (which data structure is used internally, which helper it calls).

## Document the invariant, not the validation mechanism

For domain models, prefer describing the business rule being protected over restating what the code checks:

Prefer:
> Prevents modifying a record after it has been finalized.

Over:
> Checks that `status != "finalized"` before allowing changes.

The first tells the reader *why* the check exists and survives the check being refactored; the second is just a narration of the code that will drift out of sync.

## Fields with a `description=` argument (e.g. Pydantic-style models)

Only add a description when it adds information beyond the type:

Prefer:
```python
timeout_seconds: int = Field(..., description="Must be positive; requests are aborted after this many seconds.")
```

Over:
```python
timeout_seconds: int = Field(..., description="An integer timeout in seconds.")
```

A concrete worked example (with a fictional endpoint from a different project) is in `references/examples.md` — use it as a shape to imitate, not as this project's actual code.
