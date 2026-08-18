/**
 * Platform layout adapter — returns phone vs TV grid/focus dimensions.
 * TV = broadcast 16:9 metrics; phone = device window.
 */
import {useWindowDimensions} from 'react-native';
import {IS_TV} from '../utils/platform';

export interface TVLayout {
  isTV: boolean;
  width: number;
  height: number;
  /** Media grid columns (phone: 3, TV: 6–8). */
  columnCount: number;
  /** Horizontal chip/rail spacing. */
  spacing: number;
  /** Poster rail tile width. */
  tileWidth: number;
  /** Larger minimum touch/focus handle on TV. */
  hitSlopScale: number;
}

export function useTVLayout(): TVLayout {
  const {width, height} = useWindowDimensions();
  const isTV = IS_TV;

  const columnCount = isTV ? (width >= 1400 ? 8 : 6) : 3;
  const tileWidth = isTV ? Math.floor(width / 7) : Math.floor(width / 3.4);
  const spacing = isTV ? 20 : 10;
  const hitSlopScale = isTV ? 1.6 : 1;

  return {isTV, width, height, columnCount, spacing, tileWidth, hitSlopScale};
}
