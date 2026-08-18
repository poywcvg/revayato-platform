import React from 'react';
import {Platform} from 'react-native';
import {PhoneNavigator} from './PhoneNavigator';
import {TvNavigator} from './TvNavigator';

/**
 * One pick at startup: Android TV uses the leanback launch intent, so
 * `Platform.isTV` is set by the react-native-tvos fork. Phones get tabs.
 */
export function AppNavigator() {
  const isTV = Boolean((Platform as {isTV?: boolean}).isTV);
  return isTV ? <TvNavigator /> : <PhoneNavigator />;
}
