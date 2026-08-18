/**
 * Metro configuration
 * https://reactnative.dev/docs/metro
 *
 * @type {import('metro-config').MetroConfig}
 */
const {getDefaultConfig, mergeConfig} = require('@react-native/metro-config');

const config = {
  resolver: {
    // Fonts are bundled natively via react-native-asset (react-native.config.js);
    // no extra assetExts required.
  },
};

module.exports = mergeConfig(getDefaultConfig(__dirname), config);