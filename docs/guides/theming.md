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

The switcher offers **Light** and **Dark** only. "Follow the device" is not a
third option — it is the absence of a stored choice, which is the state every
new install starts in. So a user who never touches the control keeps tracking
their OS, and one who picks a side stays pinned to it until they pick the other.
There is no way back to following the device short of clearing app storage; that
is the deliberate cost of keeping the control to two buttons.

Because the two states are indistinguishable in the UI, the switcher marks
whichever option matches **what is currently on screen**. Before any choice that
is the device's scheme, so the control always describes the visible theme rather
than showing nothing selected.

The choice persists under `taskify.colorScheme` in AsyncStorage.

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
