# Python Unit Testing: Examples

## Fixture in conftest.py

```python
# tests/conftest.py
import pytest


@pytest.fixture
def sample_todos():
    return [
        {"id": 1, "title": "Buy milk", "done": False},
        {"id": 2, "title": "Walk dog", "done": True},
    ]
```

```python
# tests/test_todos.py
def test_active_todos_excludes_done(sample_todos):
    from todoapp.todos import active_todos
    result = active_todos(sample_todos)
    assert len(result) == 1
    assert result[0]["title"] == "Buy milk"
```

## Fake instead of mock

Prefer a small fake implementation over mocking a dependency's internals. The fake behaves like the real thing, so the test stays valid even if the implementation details of `fetch_todos` change.

```python
# tests/fakes.py
class FakeTodoClient:
    def __init__(self, todos):
        self._todos = todos

    def list_todos(self):
        return self._todos
```

```python
# tests/test_client.py
from tests.fakes import FakeTodoClient


def test_fetch_todos_returns_pending_items():
    from todoapp.client import fetch_todos
    client = FakeTodoClient(todos=[{"id": 1, "title": "Buy milk", "done": False}])
    result = fetch_todos(client=client)
    assert result == [{"id": 1, "title": "Buy milk", "done": False}]
```

## Testing exceptions with message

```python
import pytest


def test_parse_id_rejects_empty_string():
    from todoapp.parser import parse_id
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_id("")
```

## Temporary files

`tmp_path` is a built-in pytest fixture: it keeps the test isolated from the real filesystem without needing a mock.

```python
from pathlib import Path


def test_save_writes_json(tmp_path: Path):
    from todoapp.storage import save_todos
    target = tmp_path / "todos.json"
    save_todos([{"id": 1}], target)
    assert target.read_text().startswith("[")
```

## Anti-patterns to avoid

| Avoid | Prefer |
|-------|--------|
| Testing an API endpoint function directly | Test the functions the endpoint calls internally |
| Testing private `_method` directly | Test public API behavior |
| One giant test for many scenarios | Separate tests or `@pytest.mark.parametrize` |
| Mocking an internal dependency's behavior | Fake or stub the dependency instead |
| Sleep/retry for async or time-based logic | Fake clock (e.g. `freezegun`) or `pytest-asyncio` |
| Asserting full object dumps | Assert only relevant fields |
| Copy-paste setup in every test | Fixtures in `conftest.py` |
