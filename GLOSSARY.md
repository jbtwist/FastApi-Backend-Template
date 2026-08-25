## Core

### docs-sync
An automated documentation maintenance process triggered after each merge to `main`. It uses the Gemini CLI to ensure documentation, docstrings, and TSDoc are kept in sync with code changes, using the `gemini-3.1-flash-lite` model for efficiency and quota management.

- **Used in:** `.github/workflows/docs-sync.yml`
