/**
 * @format
 *
 * روایتو — force RTL (Persian) BEFORE any component renders.
 * React Native does not flip layout from dir attributes; I18nManager must be
 * set here so every screen builds RTL-aware from the start.
 */

import {AppRegistry, I18nManager} from 'react-native';
import App from './src/App';
import {name as appName} from './app.json';

I18nManager.allowRTL(true);
I18nManager.forceRTL(true);

AppRegistry.registerComponent(appName, () => App);