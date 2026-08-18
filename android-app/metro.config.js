/**
 * Metro configuration
 * https://reactnative.dev/docs/metro
 *
 * @type {import('metro-config').MetroConfig}
 */
const path = require('path');
const {getDefaultConfig, mergeConfig} = require('@react-native/metro-config');

// pnpm workspace root — Metro must be able to follow the symlinked
// react-native-tvos and hoisted @babel/* packages, otherwise the JS bundle
// step fails with "Unable to resolve module @babel/runtime/...".
const MONOREPO_ROOT = path.resolve(__dirname, '..');

const config = {
  watchFolders: [MONOREPO_ROOT],
  resolver: {
    // Prioritise the same node_modules order Metro defaults to: app first,
    // then the pnpm workspace root (where the real packages live).
    nodeModulesPaths: [
      path.resolve(__dirname, 'node_modules'),
      path.resolve(MONOREPO_ROOT, 'node_modules'),
    ],
    // Fonts are bundled natively via react-native-asset (react-native.config.js);
    // no extra assetExts required.
  },
};

module.exports = mergeConfig(getDefaultConfig(__dirname), config);