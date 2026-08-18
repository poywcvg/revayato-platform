import React, {useState} from 'react';
import {
  StyleSheet,
  Pressable,
  PressableProps,
  View,
  ViewStyle,
} from 'react-native';
import {colors, radius} from '../../theme';

interface PressableFocusProps extends PressableProps {
  /** TV only: request DPAD focus on mount (set for the first rail tile). */
  tvPreferredFocus?: boolean;
  /** Visible ring when the tile is focused (TV). */
  showFocusRing?: boolean;
  focusColor?: string;
  scaleOnFocus?: boolean;
}

/**
 * Atomic pressable that behaves touch-first on phones and gains a DPAD focus
 * ring on Android TV (react-native-tvos fork). The fork focuses Pressables
 * automatically; we manage the visual + preferred-focus delta.
 */
export function PressableFocus({
  children,
  tvPreferredFocus = false,
  showFocusRing = true,
  focusColor = colors.brandBright,
  scaleOnFocus = true,
  onFocus,
  onBlur,
  style,
  ...rest
}: PressableFocusProps) {
  const [focused, setFocused] = useState(false);

  return (
    <Pressable
      {...rest}
      hasTVPreferredFocus={tvPreferredFocus}
      onFocus={e => {
        setFocused(true);
        onFocus?.(e);
      }}
      onBlur={e => {
        setFocused(false);
        onBlur?.(e);
      }}
      style={({pressed}) => [
        pressed && styles.pressed,
        focused && scaleOnFocus && styles.focusedScale,
        style as ViewStyle,
      ]}>
      {typeof children === 'function' ? children({focused, pressed: false}) : children}
      {focused && showFocusRing ? (
        <View pointerEvents="none" style={[styles.ring, {borderColor: focusColor}]} />
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pressed: {opacity: 0.85},
  focusedScale: {transform: [{scale: 1.04}]},
  ring: {
    ...StyleSheet.absoluteFillObject,
    borderWidth: 3,
    borderRadius: radius.md,
    borderColor: colors.brandBright,
  },
});
