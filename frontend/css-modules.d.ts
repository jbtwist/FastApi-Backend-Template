// Ambient types for CSS imports on the web target (react-native-web / expo).
declare module '*.module.css' {
  const classes: { readonly [key: string]: string };
  export default classes;
}
declare module '*.css';
