---
name: mkdocs-python-docs
description: Generates and maintains this Python project's technical documentation using MkDocs (Material), organized around the Diataxis framework (tutorials, how-to guides, reference, explanation), with ADRs for architecture decisions, auto-generated API reference via mkdocstrings, a domain glossary, and Mermaid diagrams. ALWAYS use this skill when the user asks to document the project, create or update docs/, add a guide or tutorial, record an architecture decision (ADR), generate or update API reference, add an architecture diagram, keep docstrings in sync with a change, update or check the project glossary (`/GLOSSARY.md`), or mentions MkDocs, mkdocs.yml, Diataxis, mkdocstrings, or "technical documentation" in the context of this project — even if they don't use those exact words.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Technical documentation with MkDocs (Python project)

This skill treats documentation as a product of the codebase: it should describe the current behavior and guarantees of the system, not just narrate what one change did. It maintains docs following Diataxis (separation by content type), versioned architecture decisions (ADRs), a domain glossary for ubiquitous language, API reference generated from code (never hand-written), and diagrams as code (Mermaid).

The project does not have a fixed domain model yet (it's early-stage, still being built) — nothing in this skill should assume specific entities, a database, or a particular web framework unless the user has actually introduced them. Domain-specific examples referenced below live in `references/examples.md` and are explicitly from a different project — use them only as a shape to imitate, never as this project's actual concepts.

## 0. Core principles

- **Documentation is a product of the codebase, not of a single change.** Describe current behavior, not the implementation history of one PR.
- **Accuracy over completeness.** Less documentation that's correct beats more documentation based on assumptions.
- **Do not guess.** If behavior can't be established from the code, tests, or existing docs, don't invent an explanation — leave `<!-- TODO: confirm ... -->` and say so to the user.
- **Minimal coherent change.** Update only what's actually affected. Don't rewrite existing docs for stylistic preference alone, and don't create a new page when an existing one can be updated instead.
- **The docs are for humans; never mention the AI tooling in them.** Pages under `docs/` (and docstrings/TSDoc, which publish into the reference) describe the code and how a person works with it. They must not mention or send the reader to anything that exists for the AI assistants: `.claude/` and its skills, templates and `GLOSSARY.md`, `CLAUDE.md`, `taskify/`, or the conventions those files define (glossary-first naming, TDD stop points, docstring style, and so on). The people maintaining this project may change those rules at any time. When a how-to would include such a step ("add the name to the glossary"), leave the step out, and keep following the rule yourself. When something only exists in AI tooling (an ADR template under `.claude/`), describe what the reader needs inline instead of linking to it.

## 1. Before writing: figure out what's actually affected

Before creating or editing anything:

1. Read the existing docs relevant to the area you're touching, the relevant source code, and `/GLOSSARY.md` if it exists.
2. Read `mkdocs.yml` to see the current theme, plugins, and `nav` — edit it incrementally, never overwrite it.
3. Decide what kind of update this is:
   - New or changed public function/class → **reference** (regenerate via mkdocstrings, don't hand-write).
   - New or changed user/dev workflow → **guide** or **tutorial**.
   - New or meaningfully changed architecture decision → **ADR**.
   - New or changed domain concept/term → **glossary**.
4. A change with no observable behavior difference (a pure refactor) usually needs **no** documentation update — don't touch docs just because code changed.

## 2. Folder structure (Diataxis + extras)

Only create what's missing; don't reorganize existing content without confirming with the user first.

```
docs/
├── index.md                   # Landing page: what the project is, quick install, links
├── getting-started/           # TUTORIALS: learn by doing, step by step
├── guides/                    # HOW-TO: solve a specific problem
├── reference/                 # REFERENCE: auto-generated with mkdocstrings, never edit by hand
├── architecture/
│   ├── overview.md            # EXPLANATION: system overview (+ diagrams)
│   └── decisions/             # Numbered ADRs: 0001-title.md, 0002-title.md...
└── operations/                # Runbooks, deployment, troubleshooting

GLOSSARY.md                    # Domain terminology, at the repo root
```

Quick rule for deciding where new content goes:
- Does it teach someone new to accomplish something end to end? → `getting-started/`
- Does it solve a specific task for someone who already knows the basics? → `guides/`
- Is it the exact signature of a function/class/endpoint? → `reference/` (auto-generated)
- Does it explain the "why" behind a decision or the overall design? → `architecture/`
- Is it the meaning of a domain term? → `/GLOSSARY.md`

See `references/diataxis-cheatsheet.md` for the full decision table and Mermaid syntax examples.

## 3. `mkdocs.yml` configuration

Use `assets/mkdocs.yml.example` as a reference for the target configuration (Material theme, mkdocstrings, Mermaid). Merge in only the sections missing from the user's actual `mkdocs.yml`; don't overwrite existing custom configuration.

Key pieces it should have:
- `theme: material`, with tabbed navigation if the project grows large.
- `plugins: [search, mkdocstrings]` with the `python` handler.
- `markdown_extensions` with `pymdownx.superfences` configured for ` ```mermaid ` blocks, plus `admonition` and `toc` with permalinks.
- A `nav` in sync with the actual folders — every new file under `docs/` must be added here or it becomes "orphaned".

## 4. API reference — ALWAYS auto-generated

Never hand-copy docstrings into a `.md` file. For every new or changed public module:

1. Create (or update) `docs/reference/<module>.md` with:
   ```markdown
   # package.module

   ::: package.module
   ```
2. Add the corresponding entry to `nav` in `mkdocs.yml` if it's a new module.
3. Write or fix the actual docstring in the source file — it's the only source for the reference section. See `references/docstrings-guide.md` for how to write docstrings that are actually worth reading (document behavior and invariants, not the obvious).

## 5. ADRs (Architecture Decision Records)

When the user makes or mentions a significant architecture decision (library choice, pattern, data store, etc.):

1. Copy `assets/adr-template.md` to `docs/architecture/decisions/NNNN-short-title.md`, where `NNNN` is the next sequential number (check the existing files in that folder).
2. Fill in Context, Decision, Alternatives Considered, and Consequences.
3. ADRs are immutable once accepted: if a decision later changes, create a new ADR that replaces it and mark the old one as `Superseded by ADR-000X` — don't edit it in place.
4. Add the ADR to `nav` under `architecture/decisions/`.

## 6. Diagrams — Mermaid as code

Use ` ```mermaid ` code blocks directly in markdown (not exported images, so they're versioned as text). `flowchart` for processes, `sequenceDiagram` for interactions, `classDiagram`/subgraphed `flowchart` for architecture. Examples in `references/diataxis-cheatsheet.md`.

## 7. Domain glossary (`/GLOSSARY.md`)

A term must mean the same thing in code, docs, comments, and conversation. Use `assets/glossary-template.md` to start the file if it doesn't exist yet.

- Organize by bounded context. **This project doesn't have clear bounded contexts yet** — keep everything under a single `## Core` heading until real boundaries emerge from the code; don't force a taxonomy prematurely.
- When a change introduces a new domain concept → add it, with its invariants and where it's used.
- When a change alters an existing concept → update its definition/invariants/use-sites.
- When a change just *uses* an existing term → reuse the glossary's exact wording. Don't invent a synonym.
- **Naming discrepancies are a flag, not an editing opportunity.** If the code calls something `Client` and the glossary calls it `Customer`, don't silently rename either one — mark it in the glossary (`⚠️ Naming discrepancy — code uses X, glossary defines Y`) and tell the user; renaming a domain term is a decision for a human, not for this skill to make unilaterally.

## 8. Writing style

Draft → Edit → Polish. Lead with the action, not the topic ("Set the base URL before running the app", not "Configuration"). Full style rules, do's/don'ts, and a quick-reference table are in `references/writing-style.md` — read it before writing prose-heavy pages (guides, tutorials, architecture overviews).

## 9. Tutorials vs. guides

- **Tutorial** (`getting-started/`): didactic tone, a single happy path, no branching, ends with something verifiably working.
- **How-to guide** (`guides/`): assumes basic knowledge, goes straight to the steps, may include variants ("if you're using X, do this instead").

## 10. Documentation consistency

Before creating a new page, search for existing documentation covering the same concept. Prefer, in order: update an existing page → link to an existing page → create a new page only if the content has a genuinely distinct purpose. Avoid duplicate explanations, conflicting instructions, and orphan pages with no link pointing to them.

## 11. Maintenance and verification

Before considering any documentation task done:

```bash
mkdocs build --strict
```

This fails on warnings (broken links, pages missing from `nav`, mkdocstrings references that don't resolve) — fix everything it reports before finishing.

Other useful commands: `mkdocs serve` (local preview at `http://127.0.0.1:8000`), `mkdocs gh-deploy` (publish to GitHub Pages, if the project uses it).

Golden rule: documentation gets updated in the same change that touches the related code, not afterward.

## 12. Post-merge guardrails (automated docs-sync)

`.github/workflows/docs-sync.yml` runs this skill unattended, against a small
model, right after a PR merges to `main`. No human reviews the prompt before
it acts, so this run is deliberately narrower than an interactive session:

- **Scope of reading**: only the diff of the merged PR (`gh pr diff <number>`
  or the PR's own commits) plus whatever existing docs/glossary files it
  needs to edit accurately. Don't re-derive the whole architecture from
  scratch each run.
- **Scope of writing**: only files under `docs/`, `mkdocs.yml`'s `nav`,
  `.claude/skills/docs/GLOSSARY.md`, Python docstrings, and TSDoc comments
  (`/** */`) in `.ts`/`.tsx` files. Never edit application logic, tests, or
  CI/workflow files — this is a restriction on *which files you may touch*,
  not a shortcut for deciding whether to act. A diff that adds or changes a
  public endpoint, function, or workflow **does** need a doc update even
  though the change itself lives in a logic file: write about it in
  `docs/`/docstrings, don't edit the logic file. Example: a new `/version`
  endpoint added to `main.py` is a behavior change worth a line in the
  architecture overview or a reference page — you'd edit the doc, not
  `main.py`.
- **When to actually do nothing**: only when the diff itself has no
  observable behavior difference for a user or developer — CI config,
  tooling, permissions, dependency bumps, pure refactors. That's rule 0.4,
  and it's about the *nature of the change*, not which file it's in. When
  in doubt and nothing else in this section resolves it, do nothing — this
  run has no one to ask for clarification, so a skipped update is cheap to
  catch later; an invented one (e.g. treating a CI/tooling change as a new
  domain concept) is not.
- **Branch naming**: use `docs/update-after-<PR_NUMBER>`. The workflow's
  own trigger explicitly excludes branches with this prefix from
  re-triggering the job, which is what stops this automation from looping
  on the PRs it opens about itself.
- **Finishing the job**: the workflow's checkout already carries a
  `GITHUB_TOKEN` with `contents: write` / `pull-requests: write` — pushing
  the branch and running `gh pr create` needs no further approval or
  confirmation. A run that edits files but stops before pushing and
  opening the PR has not completed the task; leaving changes uncommitted
  in the runner accomplishes nothing, since the runner is discarded when
  the job ends.

## Included resources

- `assets/adr-template.md` — ready-to-copy ADR template.
- `assets/glossary-template.md` — starting skeleton for `/GLOSSARY.md`.
- `assets/mkdocs.yml.example` — full reference configuration (Material + mkdocstrings + Mermaid).
- `references/diataxis-cheatsheet.md` — quick reference for which document type to use, with Mermaid examples.
- `references/writing-style.md` — Draft → Edit → Polish process, style dos/don'ts, quick-reference table.
- `references/docstrings-guide.md` — how to write Python docstrings worth generating reference pages from.
- `references/examples.md` — **illustrative examples from a different, unrelated project** (domain glossary entry, docstring, PR workflow). Shapes to imitate, not this project's actual content.
