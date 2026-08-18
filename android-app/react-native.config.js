/**
 * Registers bundled assets (Vazirmatn fonts) so `npx react-native-asset`
 * copies them into the native apps. RN has no @font-face; bundling is the
 * reliable path for both phone and Android TV.
 */
module.exports = {
  assets: ['./src/assets/fonts'],
};