package com.revayato.app;

/** Centralized backend endpoints so every Activity references the same base. */
final class Config {
  static final String API_BASE = "https://revayato.com/api/";
  static final String WS_BASE = "wss://revayato.com/ws/";
  static final String REFERER = "https://revayato.com/";

  private Config() {}
}
