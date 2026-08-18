import {FONT_STACK} from '../config';

/**
 * Typography — Vazirmatn is bundled with the app (see react-native.config.js
 * + `pnpm app:assets`). Latin glyphs fall back automatically inside Vazirmatn.
 */
export const typography = {
  fontFamily: FONT_STACK,
  // Android resolves fonts by file-stem: Vazirmatn-Bold.ttf → 'Vazirmatn-Bold'.
  // AppText selects these directly so every weight renders from the right file.
  fontFamilyName: {
    light: 'Vazirmatn-Light',
    regular: 'Vazirmatn-Regular',
    medium: 'Vazirmatn-Medium',
    bold: 'Vazirmatn-Bold',
  } as const,
  // Approximate the web's Vazirmatn pairing with weights (kept for any native
  // text component that only gets a numeric fontWeight).
  weights: {
    light: '300',
    regular: '400',
    medium: '500',
    bold: '700',
  },
  sizes: {
    xs: 11,
    sm: 13,
    md: 15,
    lg: 18,
    xl: 22,
    '2xl': 28,
    '3xl': 36,
  },
} as const;
