/**
 * `authConfig` is built once at module load from `process.env`, so every case
 * here sets the environment and then re-imports the module.
 */
import type { AuthConfig } from '../config';

const ENV_KEYS = [
  'EXPO_PUBLIC_API_URL',
  'EXPO_PUBLIC_PASSWORD_MIN_LENGTH',
  'EXPO_PUBLIC_PASSWORD_MAX_LENGTH',
] as const;

function loadConfig(env: Partial<Record<(typeof ENV_KEYS)[number], string>>): AuthConfig {
  for (const key of ENV_KEYS) delete process.env[key];
  Object.assign(process.env, env);

  jest.resetModules();
  // `require` rather than `import()`: the module has to be re-evaluated after
  // the environment changes, and jest's ESM loader is not enabled here.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  return (require('../config') as typeof import('../config')).authConfig;
}

beforeEach(() => {
  for (const key of ENV_KEYS) delete process.env[key];
});

describe('authConfig', () => {
  it('falls back to the bundled defaults when nothing is set', () => {
    const config = loadConfig({});

    expect(config.apiBaseUrl).toBe('http://localhost:8000');
    expect(config.passwordMinLength).toBe(12);
    expect(config.passwordMaxLength).toBe(128);
  });

  it('reads the password bounds from the environment', () => {
    const config = loadConfig({
      EXPO_PUBLIC_PASSWORD_MIN_LENGTH: '15',
      EXPO_PUBLIC_PASSWORD_MAX_LENGTH: '64',
    });

    expect(config.passwordMinLength).toBe(15);
    expect(config.passwordMaxLength).toBe(64);
  });

  it.each(['', 'twelve', '0', '-3', '12.5'])(
    'ignores %p and keeps the default, so a bad value never disables the check',
    (raw) => {
      const config = loadConfig({ EXPO_PUBLIC_PASSWORD_MIN_LENGTH: raw });

      expect(config.passwordMinLength).toBe(12);
    },
  );
});
