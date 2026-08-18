import React from 'react';
import {StatusBar, StyleSheet, View} from 'react-native';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import {NavigationContainer, DefaultTheme} from '@react-navigation/native';
import {AppNavigator} from './navigation';
import {linking} from './navigation/linking';
import {colors} from './theme';

const navTheme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    background: colors.bgMain,
    card: colors.bgMain,
    text: colors.textPrimary,
    border: colors.line,
    primary: colors.brandBright,
  },
};

/**
 * Root provider stack. Keeping the theme single-source (theme/index) and the
 * navigation single-file means phone/TV share the same shell.
 */
export default function App() {
  return (
    <SafeAreaProvider>
      <View style={styles.root}>
        <StatusBar
          barStyle="light-content"
          backgroundColor={colors.bgMain}
          translucent={false}
        />
        <NavigationContainer theme={navTheme} linking={linking} fallback={null}>
          <AppNavigator />
        </NavigationContainer>
      </View>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgMain,
  },
});
