/**
 * Unit-test config for the pure data layer (adapter, url, format, resume).
 * These modules deliberately avoid importing react-native (config is RN-free),
 * so we run them under plain babel-jest with no RN preset — faster and immune
 * to the tvos fork's Flow-typed jest setup.
 *
 * UI/component tests (if added) can extend this with the RN preset per-file.
 */
module.exports = {
  testMatch: ['<rootDir>/__tests__/**/*.test.ts'],
  testEnvironment: 'node',
  transform: {
    '^.+\\.(ts|tsx|js)$': 'babel-jest',
  },
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react|@react-native(-community)?|react-native-tvos)/)',
  ],
};