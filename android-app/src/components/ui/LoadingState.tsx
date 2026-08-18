import React from 'react';
import {ActivityIndicator, StyleSheet, View} from 'react-native';
import {colors, radius, spacing} from '../../theme';
import {AppText} from './AppText';

/** Neutral full-area or inline loading placeholder. */
export function LoadingState({label}: {label?: string}) {
  return (
    <View style={styles.wrap}>
      <ActivityIndicator color={colors.brand} size="large" />
      {label ? (
        <AppText size="sm" color={colors.textMuted} style={{marginTop: spacing.md}}>
          {label}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    minHeight: 120,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
  },
});
