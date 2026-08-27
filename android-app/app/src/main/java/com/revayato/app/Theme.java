package com.revayato.app;

/**
 * Centralized design tokens for the Revayato Android client.
 *
 * All colors and motion durations live here so the four Activities
 * (MainActivity, AuthActivity, PlayerActivity, WatchPartyActivity) stay visually
 * coherent and never drift from duplicated hardcoded hex literals.
 *
 * Durations mirror the web app's CSS motion tokens (--motion-fast / --motion-base
 * / --motion-slow) so cross-platform motion feels identical.
 */
public final class Theme {
  private Theme() {}

  // Surfaces (Obsidian + Burnt Copper palette, dark-only).
  public static final int BG = 0xff050807;
  public static final int SURFACE = 0xe6111713;
  public static final int CARD = 0xd919211c;
  public static final int LIME = 0xffd8ff3e;
  public static final int MUTED = 0xffaab5ae;
  public static final int WHITE = 0xfff4f7f5;

  // Derived/utility tints used across activities.
  public static final int OUTLINE = 0xff2b3730;
  public static final int RIPPLE = 0x22d8ff3e;

  /** Motion durations (ms) — mirror web --motion-* tokens. */
  public static final int DUR_FAST = 120;
  public static final int DUR_BASE = 160;
  public static final int DUR_SLOW = 280;

  /** Spring-like overshoot duration for tab/selection pops. */
  public static final int DUR_SPRING = 360;

  /** Stagger step (ms) between sequential reveal items. */
  public static final int STAGGER = 40;
}
