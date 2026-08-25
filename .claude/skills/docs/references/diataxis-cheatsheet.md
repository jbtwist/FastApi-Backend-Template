# Cheatsheet: Diataxis + Mermaid

## Where does this content go?

| Question | Type | Folder |
|---|---|---|
| Does it teach from scratch how to accomplish something, step by step? | Tutorial | `getting-started/` |
| Does it solve a specific task for someone with prior knowledge? | How-to guide | `guides/` |
| Is it the exact spec of a function/class/endpoint? | Reference | `reference/` (auto-generated) |
| Does it explain the "why" behind a decision or the overall design? | Explanation | `architecture/` |

Don't mix types in the same document: a tutorial shouldn't dive deep into theory, and a reference page shouldn't include design opinions.

## Mermaid diagram examples

### Process flow

```mermaid
flowchart LR
    A[User sends request] --> B{Authenticated?}
    B -- No --> C[401 Unauthorized]
    B -- Yes --> D[Process request]
    D --> E[Respond 200]
```

### Interaction between components

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant DB
    Client->>API: POST /orders
    API->>DB: INSERT order
    DB-->>API: order_id
    API-->>Client: 201 Created
```

### High-level architecture

```mermaid
flowchart TB
    subgraph Frontend
        UI[Web app]
    end
    subgraph Backend
        API[REST API]
        Worker[Async worker]
    end
    subgraph Data
        DB[(Database)]
        Queue[(Message queue)]
    end
    UI --> API
    API --> DB
    API --> Queue
    Queue --> Worker
    Worker --> DB
```

## Quick checklist before finishing a docs task

- [ ] The new file is in the correct folder per the table above
- [ ] It's added to the `nav` in `mkdocs.yml`
- [ ] If it touches public code, the reference (`reference/`) was updated via `::: module`, not by hand
- [ ] If it's an architecture decision, it has its ADR under `architecture/decisions/`
- [ ] `mkdocs build --strict` passes with no warnings
