/**
 * Platform helpers around the react-native-tvos fork contract.
 *
 * `Platform.isTV` is the official hook — never sniff `Platform.OS` for
 * TV-vs-phone branching.
 */
import {Platform} from 'react-native';

/** Whether this build is running on Android TV (leanback launcher). */
export const IS_TV = Boolean((Platform as unknown as {isTV?: boolean}).isTV);

export function isTV(platform: {isTV?: boolean}): boolean {
  return Boolean(platform.isTV);
}
