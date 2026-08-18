/**
 * روایتو — dark-only design tokens mirroring the web app.
 * (Frontend uses a forced dark theme; the same palette is reproduced here.)
 */
export const colors = {
  bgMain: '#1d1c21',
  bgSoft: '#19181d',
  bgSurface: '#26252b',
  bgElevated: '#2f2e36',
  line: '#38373f',
  textPrimary: '#f4f1ea',
  textSecondary: '#b9b4a8',
  textMuted: '#8a8579',
  brand: '#408a71',
  brandBright: '#b0e4cc',
  accentCrimson: '#c94f3d',
  success: '#3fae6e',
  error: '#e05b4e',
  warning: '#e0a13c',
  overlay: 'rgba(0,0,0,0.72)',
} as const;

export type ThemeColor = keyof typeof colors;
