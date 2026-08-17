---
name: tdd
description: >-
  Write unit tests before writing any code. Perform TDD for features to
  develop, reducing time spent reviewing LLM-written code by anchoring it
  to a passing test suite first.
  Use when asked to implement a feature with TDD, write tests first, or
  when the user says "TDD", "test first", or "write tests before coding".
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Python Unit Testing

## Workflow

1. Receive a brief explanation of what the feature should do and the basic assertions for the feature to work.
2. Identify possible corner cases, missed assertions, limit and fuzzy values or any missed instruction from the user.
3. Identify and note the external resources required for those tests: fixtures, mocks, fakes, stubs, dummies and spies.
4. For each external resource needed, identify if there is already a fixture, fake or stub that accomplishes the goal. If there is not, create one. Avoid using mocks, dummies or spies.
5. Identify the best place for placing the tests according to the current software architecture and write them in that place.

# Writing tests

## Prioritize fixtures: how to create them

1. Keep them small and focused. A fixture should set up one thing (a user, a DB connection, a config object): not a giant "everything the whole suite might need" blob.
2. Prefer explicit over implicit. If a test's behavior depends on fixture data, that data should be easy to find. Avoid deeply nested or chained fixtures that hide the actual "Arrange" step several files away.
3. Make them composable. Small fixtures that combine (e.g. db + user + authenticated_client) are more flexible than one large fixture that does it all and can't be reused partially.
4. Use factories for variation, fixtures for setup. If a test needs slightly different data each time (different emails, statuses, edge-case values), use a factory/builder inside or alongside the fixture rather than creating dozens of near-duplicate fixtures.
5. Scope them correctly. Match the fixture's lifetime to what it represents: per-test for mutable state, per-module/session for expensive, read-only setup (e.g. spinning up a test container). Don't share mutable state across tests by mistake.
6. Always clean up. Any fixture that creates external state (files, DB rows, network connections) must tear it down after the test, even if the test fails. Prefer framework teardown hooks (yield in pytest, afterEach in Jest) over manual cleanup calls scattered in test bodies.
7. Avoid fixtures with hidden magic. A fixture shouldn't silently mock things, patch globals, or change behavior in ways a reader can't infer from its name. If it does something non-obvious, name it accordingly (e.g. frozen_time, mocked_payment_gateway).
8. Don't let fixtures encode assertions. Fixtures build state: they shouldn't contain assert statements or business logic that decides pass/fail. That belongs in the test itself.
9. Name fixtures for what they provide, not how. valid_user is better than user_from_db_query_v2: the test shouldn't need to know the mechanism, just what it gets.
10. Watch for fixture bloat. If a fixture file keeps growing and few tests use most of what's in it, split it up. Overly shared fixtures become a maintenance burden and a source of unrelated test breakage.

## Test doubles: what to use when

| I want to verify: | Use |
|---|---|
| The result/output of my function | Stub or Fake |
| That an important side effect happened (sending an email, writing a log) | Spy (use sparingly) |
| Complex, realistic behavior of a dependency | Fake |
| A parameter that doesn't matter for the test | Dummy |
| Exactly how a dependency was called, with which arguments | Mock (avoid if you can achieve the same another way) |

## Golden rule

**Mock at the edges** (I/O, external APIs, time, randomness), not at the core of your business logic. If you find yourself mocking 5 internal dependencies to test one function, that's a sign the design is too coupled: not that you need more mocks.

## Guidelines

- **Arrange-Act-Assert**: setup, call, assert. Keep tests short and readable.
- **Isolation**: unit tests must not hit real databases, networks, or filesystems unless explicitly integration tests (put those in `tests/integration/`).
- **Fixtures**: shared setup goes in `conftest.py`; scope fixtures narrowly (`function` by default).
- **Parametrize** repeated cases.
- **What to test**: do not test API endpoint functions directly. Instead, test all the functions that each endpoint calls internally to do its job. The endpoint itself should stay thin (routing, request/response handling) and is better covered by integration tests, not unit tests.

```python
@pytest.mark.parametrize("a,b,expected", [(0, 0, 0), (1, -1, 0), (-3, 3, 0)])
def test_add_handles_zeros_and_negatives(a, b, expected):
    assert add(a, b) == expected
```

- **Mocking**: use `unittest.mock` or `pytest-mock` only for external I/O, and only when a fixture, fake or stub isn't a good fit. Mock at boundaries, not internals.

```python
@pytest.fixture
def todo_client():
    # Fake in-memory client instead of hitting the real API
    return FakeTodoClient(todos=[{"id": 1, "title": "Buy milk", "done": False}])

def test_fetch_todos_returns_pending_items(todo_client):
    result = fetch_todos(client=todo_client)
    assert result == [{"id": 1, "title": "Buy milk", "done": False}]
```

## Running tests

```bash
# all tests
python -m pytest

# one file
python -m pytest tests/test_example.py

# one test by name
python -m pytest -k "test_add_returns_sum"

# verbose with traceback
python -m pytest -v --tb=short

# stop on first failure
python -m pytest -x
```

## Checklist before finishing

- [ ] New/changed behavior has at least one happy-path and one edge/error test
- [ ] Tests are deterministic (no time/random without fixing seeds or mocking)
- [ ] No test depends on execution order
- [ ] `python -m pytest` passes

## Additional resources

- For more patterns and anti-patterns, see [examples.md](examples.md)
