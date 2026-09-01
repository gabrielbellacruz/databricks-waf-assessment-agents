/**
 * ESLint configuration
 * Encodes the conventions from go/ui-best-practices that the TypeScript
 * compiler cannot enforce on its own.
 */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  plugins: ['@typescript-eslint', 'react', 'react-hooks'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react/recommended',
    'plugin:react/jsx-runtime',
    'plugin:react-hooks/recommended',
  ],
  settings: {
    react: { version: 'detect' },
  },
  ignorePatterns: ['dist', 'node_modules', '*.cjs'],
  rules: {
    // Named exports only: helps searchability and avoids import renaming
    'no-restricted-exports': ['error', { restrictDefaultExports: { direct: true } }],

    // Emotion's `css` prop is compiled away by @emotion/babel-plugin
    'react/no-unknown-property': ['error', { ignore: ['css'] }],

    // Nested components have caused production incidents; the pattern is banned
    'react/no-unstable-nested-components': ['error', { allowAsProps: false }],

    // `as` casting is unsafe and must not be used to silence type errors
    '@typescript-eslint/consistent-type-assertions': [
      'error',
      { assertionStyle: 'never' },
    ],

    // Parameter properties transpile ambiguously across Babel/SWC/TSC
    '@typescript-eslint/parameter-properties': ['error', { prefer: 'class-property' }],

    // Prefer `interface` for object shapes, especially props
    '@typescript-eslint/consistent-type-definitions': ['error', 'interface'],

    '@typescript-eslint/no-explicit-any': 'error',
    '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
  },
  overrides: [
    {
      // Vite requires the config to be a default export
      files: ['vite.config.ts'],
      rules: { 'no-restricted-exports': 'off' },
    },
  ],
};
