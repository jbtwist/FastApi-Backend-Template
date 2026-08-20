---
name: frontend
description: >-
  Expo + React Native + react-native-web coding conventions for this project.
  Load when writing or reviewing any code in frontend/.
  For framework-specific tasks, delegate to the official Expo skills listed below.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Frontend — Expo + React Native

Project-specific conventions. For framework internals, load the official Expo skill for the task.

## Skill routing — load the right skill first

| Task | Load |
|---|---|
| Navigation, tabs, modals, deep links, URL params | `expo:expo-router` |
| API calls, React Query, caching, offline sync | `expo:expo-data-fetching` |
| Animations, gestures, haptics | `expo:expo-animation` |
| Native UI components (sheets, pickers, menus) | `expo:expo-native-ui` |
| Design tokens, themes, dark mode | `expo:expo-design-system` |
| Tailwind / NativeWind setup | `expo:expo-tailwind-setup` |
| Shipping to App Store / Play Store | `expo:eas-app-stores` |
| CI/CD pipelines | `expo:eas-workflows` |
| Creating native modules | `expo:expo-module` |
| SDK version upgrade | `expo:expo-upgrade` |

---

## Project structure

```
frontend/
└── src/
    ├── app/              # Expo Router routes ONLY — every file is a route
    │   ├── _layout.tsx
    │   ├── _layout.web.tsx
    │   └── (tabs)/
    ├── components/       # reusable UI — kebab-case filenames
    ├── screens/          # screen bodies rendered by routes
    ├── hooks/            # custom hooks — use-*.ts naming
    ├── utils/            # pure helpers + colocated tests
    └── constants.ts
```

Routes delegate to screens. Screens own layout. Components are reusable.

```tsx
// src/app/index.tsx — route only
import { TaskList } from "@/screens/task-list";
export default function HomeRoute() {
  return <TaskList />;
}
```

---

## File naming

- Components: **kebab-case** (`task-card.tsx`, `add-task-button.tsx`)
- Hooks: `use-*.ts` (`use-tasks.ts`, `use-sync-status.ts`)
- Utils: camelCase (`formatDate.ts`)
- Routes: kebab-case or index (`task-detail.tsx`)
- Platform variants: `component.tsx` + `component.web.tsx` (default file always required)

---

## TypeScript

- Strict mode. No `any`.
- Named exports. No default exports except route files (Expo Router requires it).
- Explicit interfaces for all props.

```tsx
// good
interface TaskCardProps {
  title: string;
  is_done: boolean;
  onToggle: () => void;
}

export function TaskCard({ title, is_done, onToggle }: TaskCardProps) { ... }

// bad
export default function TaskCard(props: any) { ... }
```

---

## Platform-specific code

Small differences: `Platform.select` / `Platform.OS`.  
Larger differences: split into platform files.

```
task-list.tsx       # default (required)
task-list.web.tsx   # web variant
```

Props must be identical across variants.

---

## Styles

Colocate `StyleSheet.create` at the bottom of the component file. No separate `.styles` files.

```tsx
export function TaskCard() {
  return <View style={styles.container} />;
}

const styles = StyleSheet.create({
  container: { padding: 12 },
});
```

If using NativeWind: Tailwind classes instead of `StyleSheet`. Never mix both in the same component.

---

## Offline-first

Local DB (SQLite on mobile, IndexedDB on web) is source of truth. Sync against backend is async.

- Read always from local DB first.
- Writes go to local DB immediately, then queue for sync.
- Do not implement conflict resolution logic that assumes last-write-wins without flagging it — strategy is not yet designed.

For data fetching patterns, load `expo:expo-data-fetching`.

---

## Comments

No inline comments. Docstrings (TSDoc) acceptable on exported functions and hooks.

```tsx
// bad
const count = tasks.filter(t => !t.is_done).length; // count pending tasks

// good
const count = tasks.filter(t => !t.is_done).length;

// good — TSDoc on export
/** Returns all tasks that have not been completed. */
export function usePendingTasks() { ... }
```

---

## Naming

Before naming any variable, prop, hook, or component, check [`../tdd/GLOSSARY.md`](../tdd/GLOSSARY.md). Use the canonical name exactly. Add missing concepts to the glossary before writing code.

---

## Tests

Colocate tests next to the file they test.

```
use-tasks.ts
use-tasks.test.ts
```

For test patterns, load the `tdd` skill.

---

## react-native-web compatibility

Same codebase targets mobile and browser. Before using any library:
- Verify it supports `react-native-web` or has a `.web.tsx` variant strategy
- Avoid libraries that depend on native-only APIs with no web fallback
