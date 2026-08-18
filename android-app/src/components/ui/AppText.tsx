import React from 'react';
import {StyleSheet, Text, TextProps} from 'react-native';
import {colors, typography} from '../../theme';

interface AppTextProps extends TextProps {
  weight?: keyof typeof typography.weights;
  size?: keyof typeof typography.sizes;
  color?: string;
  align?: 'auto' | 'left' | 'right' | 'center' | 'justify';
}

/**
 * Renders with the exact bundled Vazirmatn TTF for the requested weight.
 * Android resolves font families by file-stem (Vazirmatn-Bold.ttf), so we
 * select the fontFamily here instead of relying on `fontWeight` — otherwise
 * every weight would silently render Regular.
 */
export function AppText({
  weight = 'regular',
  size = 'md',
  color = colors.textPrimary,
  align,
  style,
  children,
  ...rest
}: AppTextProps) {
  return (
    <Text
      {...rest}
      style={[
        styles.base,
        {
          fontFamily: typography.fontFamilyName[weight],
          fontSize: typography.sizes[size],
          color,
        },
        align ? {textAlign: align} : null,
        style,
      ]}>
      {children}
    </Text>
  );
}

const styles = StyleSheet.create({
  base: {},
});
