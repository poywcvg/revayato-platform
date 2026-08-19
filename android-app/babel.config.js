/**
 * Release builds inline the production API base URL at bundle time so the
 * shipped APK always talks to revayato.com — never a stale emulator address.
 * The plugin is applied ONLY when the CI build step exports the env vars
 * (API_BASE_URL / REVAYATO_DEFAULT_API_BASE), so local `pnpm android` / jest
 * keep working with the run-time default in src/config.
 */
module.exports = api => {
  // Babel needs an explicit cache mode; invalidation is keyed on whether the
  // inline-env plugin is active (release CI) or not (local dev / jest).
  api.cache(() =>
    Boolean(process.env.API_BASE_URL || process.env.REVAYATO_DEFAULT_API_BASE),
  );
  const hasInlineVars = Boolean(
    process.env.API_BASE_URL || process.env.REVAYATO_DEFAULT_API_BASE,
  );
  return {
    presets: ['module:@react-native/babel-preset'],
    plugins: hasInlineVars
      ? [
          [
            'babel-plugin-transform-inline-environment-variables',
            {include: ['API_BASE_URL', 'REVAYATO_DEFAULT_API_BASE']},
          ],
        ]
      : [],
  };
};