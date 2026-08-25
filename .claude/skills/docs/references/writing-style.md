# Writing style guide

## Draft → Edit → Polish

### Draft
Write naturally, like explaining something to a competent colleague who has never touched this part of the system. Lead with the action or conclusion, explain the reason afterward.

Prefer:
> Set the base URL before running the application.

Over:
> Configuration

### Edit
- One purpose per paragraph.
- Remove information that doesn't help the reader.
- Avoid unnecessary repetition.
- Verify examples against the actual source code — don't write example output you haven't confirmed.
- Preserve useful existing structure instead of rewriting from scratch.

### Polish
- Use descriptive link text, never "here" or "this link".
- Use backticks for code, commands, paths, variables, identifiers, and API names.
- Use **bold** for UI elements the reader needs to click or find.
- Prefer stable descriptions over values likely to age badly (avoid hardcoding version numbers or dates in prose when a link to the source of truth would do).

## Avoid

- Weasel words: "easy", "simple", "just", "obviously" — if it were obvious, it wouldn't need documenting; if it's not obvious, calling it "simple" undermines the reader's confidence when it isn't.
- Corporate filler: "utilize" (use "use"), "leverage" (use "use"), "seamlessly".
- Burying the action in prose — say what to do first, then why.
- Unnecessary passive voice ("the file is created by the script" → "the script creates the file").
- Invented behavior or speculation about what the system "probably" does.

## Quick reference

| Write this | Not this |
|---|---|
| Set the base URL before running | Configuration |
| See [the API reference](link) | Click [here](link) |
| Fails with `409` if the resource is already locked | Undocumented error behavior |
| Flag a naming discrepancy in the glossary | Rename the term yourself |
| Update the existing guide | Create a duplicate guide |
| Document observable behavior | Document assumptions |
| Lead with the action | Bury the action in prose |
