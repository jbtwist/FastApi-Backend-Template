/// <reference types="expo/types" />
// Expo's own ambient types, which `expo start` would otherwise write into the
// gitignored `expo-env.d.ts`; without them a fresh clone fails `tsc`.
// Ambient types for CSS imports on the web target (react-native-web / expo).
declare module '*.module.css' {
  const classes: { readonly [key: string]: string };
  export default classes;
}
declare module '*.css';
