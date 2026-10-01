# Switch and extend the theme

The app ships a light and a dark palette in `frontend/src/constants/theme.ts`.
Components read the active one through `useTheme()`, never by importing `Colors`
directly:

```tsx
const theme = useTheme();
<View style={{ backgroundColor: theme.background }} />;
```

## How the active scheme is decided

`ColorSchemeProvider` holds the answer, and there are only two inputs:

1. the user's stored choice, if they have made one;
2. the device's setting otherwise.

The switcher is a single icon button that flips between the two. There is no
"system" option: following the device is the absence of a stored choice, which is
the state every new install starts in. So a user who never touches the control
keeps tracking their OS, and one who presses it stays pinned until they press it
again. There is no way back to following the device short of clearing app
storage; that is the deliberate cost of keeping this to one button.

The icon shows the scheme **currently on screen** — a sun under the light
palette, a moon under the dark one — so before any choice it reflects the
device. Because an icon can't express what pressing will do, the accessibility
label names the action instead ("Switch to dark theme") rather than the state.

The choice persists under `backend-template.colorScheme` in AsyncStorage.

## Reading the scheme

| Need | Use |
| --- | --- |
| Colours to paint with | `useTheme()` |
| The scheme name (`'light' \| 'dark'`) | `useActiveColorScheme()` |
| To change it — a switcher | `useColorSchemeChoice()` |

`useActiveColorScheme` falls back to the device setting outside a provider
rather than throwing, so a component rendered without one loses the override,
not its colours. `useColorSchemeChoice` does throw: a switcher with nowhere to
write would render as a control that silently does nothing.

Never call React Native's `useColorScheme` directly in a component — it reports
the OS setting and ignores the user's choice.

## Adding a colour

Add the key to **both** palettes in `constants/theme.ts`. `ThemeColor` is
derived from the intersection of the two, so a key added to only one is a
compile error rather than a crash in one theme.
