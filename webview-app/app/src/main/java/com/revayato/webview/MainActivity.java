package com.revayato.webview;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.res.Configuration;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Minimal WebView wrapper that presents the live روایتو web app as a native
 * Android app. The entire site is loaded at https://revayato.com — same-origin
 * `/api`, `/ws` (watch-party), `/media` and `/downloads` all work unchanged.
 *
 * Behavior:
 *  - Fullscreen video uses WebView's custom-view API (onShowCustomView /
 *    onHideCustomView) — the site's player calls requestFullscreen normally.
 *  - Downloads are intercepted (onDownloadStart) and take place inside the app
 *    via DownloadManager, with a progress notification.
 *  - Links to other hosts open in the system browser; the app itself never
 *    leaves revayato.com.
 *  - Auth depends on persistent cookies (JWT in cookies). We never clear app
 *    data, so login survives relaunch.
 */
public final class MainActivity extends Activity {

    private static final String APP_URL = "https://revayato.com/";
    private static final String APP_HOST = "revayato.com";

    private WebView webView;
    private FrameLayout fullscreenContainer;
    private View customView;
    private WebChromeClient.CustomViewCallback customViewCallback;
    private boolean customViewVisible = false;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        getWindow().addFlags(WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED);
        getWindow().setStatusBarColor(Color.parseColor("#050807"));
        getWindow().setNavigationBarColor(Color.parseColor("#050807"));

        fullscreenContainer = new FrameLayout(this);
        webView = new WebView(this);

        configureWebView();

        // ---- Layout -------------------------------------------------------
        FrameLayout content = new FrameLayout(this);
        content.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(content);

        webView.setWebChromeClient(buildChromeClient());
        webView.setWebViewClient(buildWebViewClient());
        webView.setDownloadListener(buildDownloadListener());

        // Do not clear cookies/app data: login (JWT cookies) must survive relaunch.
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);

        webView.loadUrl(APP_URL);
    }

    // ---------------------------------------------------------------------
    // WebView configuration
    // ---------------------------------------------------------------------

    @SuppressLint("SetJavaScriptEnabled")
    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setGeolocationEnabled(false);
        // The site mixes https with some http CDN streams; allow it.
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        // A Chrome-like UA so the download picker prefers MP4/HLS over MKV/AVI
        // and the site treats us as a modern mobile browser. Strip the WebView
        // signature tokens (Version/4.0, wv) that mark us as a non-browser UA.
        String ua = WebSettings.getDefaultUserAgent(this)
                .replace("Version/4.0", "")
                .replace("wv", " ");
        settings.setUserAgentString(ua);
    }

    private WebChromeClient buildChromeClient() {
        return new WebChromeClient() {
            @Override
            public void onShowCustomView(View view, CustomViewCallback callback) {
                if (customView != null) {
                    callback.onCustomViewHidden();
                    return;
                }
                customView = view;
                customViewCallback = callback;
                fullscreenContainer.setBackgroundColor(Color.BLACK);
                fullscreenContainer.addView(customView);
                setContentView(fullscreenContainer);
                hideSystemUi(true);
                lockOrientation(true);
                customViewVisible = true;
            }

            @Override
            public void onHideCustomView() {
                if (customView == null) {
                    return;
                }
                customView.setVisibility(View.GONE);
                fullscreenContainer.removeView(customView);
                fullscreenContainer.removeAllViews();
                customView = null;
                setContentView(webView);
                hideSystemUi(false);
                lockOrientation(false);
                customViewVisible = false;
                if (customViewCallback != null) {
                    customViewCallback.onCustomViewHidden();
                    customViewCallback = null;
                }
            }
        };
    }

    private WebViewClient buildWebViewClient() {
        return new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleUrl(view, request.getUrl());
            }

            @Override
            @SuppressWarnings("deprecation")
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleUrl(view, Uri.parse(url));
            }
        };
    }

    private boolean handleUrl(WebView view, Uri uri) {
        String scheme = uri.getScheme();
        String host = uri.getHost();
        if ("revayato".equals(scheme)) {
            // revayato:// deep link → app web root.
            view.loadUrl(APP_URL);
            return true;
        }
        if ("https".equals(scheme)
                && (APP_HOST.equals(host) || ("www." + APP_HOST).equals(host))) {
            // Same-site navigation (pages, /api, /ws, /media, /admin) stays
            // inside the WebView.
            return false;
        }
        // Everything else (t.me, TMDB, other download CDNs) → system browser.
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "مرورگر برای باز کردن پیوند در دسترس نیست", Toast.LENGTH_SHORT).show();
        }
        return true;
    }

    // ---------------------------------------------------------------------
    // Downloads — always in-app via DownloadManager (progress notification)
    // ---------------------------------------------------------------------

    private DownloadListener buildDownloadListener() {
        return (url, userAgent, contentDisposition, mimetype, contentLength) -> {
            try {
                startInAppDownload(url, contentDisposition, mimetype);
            } catch (Exception e) {
                Toast.makeText(this, "دریافت فایل انجام نشد", Toast.LENGTH_SHORT).show();
            }
        };
    }

    private void startInAppDownload(String url, String contentDisposition, String mimetype) {
        String fileName = guessFileName(url, contentDisposition);
        String ext = extensionOf(url);
        if (ext != null && !fileName.toLowerCase(Locale.ROOT).endsWith("." + ext)) {
            fileName = fileName + "." + ext;
        }
        String safeName = sanitize(fileName);
        DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
        request.setTitle(safeName);
        request.setDescription(getString(R.string.app_name));
        request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
        request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,
                "Revayato/" + safeName);
        request.setMimeType(mimetype != null ? mimetype : "application/octet-stream");
        DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
        dm.enqueue(request);
    }

    private String guessFileName(String url, String contentDisposition) {
        if (contentDisposition != null) {
            Matcher m = Pattern.compile("filename\\*?=(?:UTF-8''|\\\")?([^\\\";]+)")
                    .matcher(contentDisposition);
            if (m.find()) {
                String name = Uri.decode(m.group(1).trim());
                if (!name.isEmpty()) return sanitize(name);
            }
        }
        String path = Uri.parse(url).getLastPathSegment();
        if (path != null && !path.isEmpty()) {
            String name = Uri.decode(path);
            if (name.indexOf('/') < 0 && name.indexOf('\\') < 0) return sanitize(name);
        }
        return getString(R.string.app_name);
    }

    /** A small safe extension only; return null when none / weird. */
    private static String extensionOf(String url) {
        String path = Uri.parse(url).getPath();
        if (path == null) return null;
        int dot = path.lastIndexOf('.');
        if (dot < 0 || path.indexOf('/', dot) >= 0) return null;
        String ext = path.substring(dot + 1).toLowerCase(Locale.ROOT);
        if (ext.length() >= 1 && ext.length() <= 6 && ext.matches("[a-z0-9]+")) {
            return ext;
        }
        return null;
    }

    private static String sanitize(String s) {
        return s.replaceAll("[^\\p{Alnum}._\\-\\s]", "_").trim();
    }

    // ---------------------------------------------------------------------
    // System chrome
    // ---------------------------------------------------------------------

    /** Match a mobile browser: fullscreen playback locks landscape. */
    private void lockOrientation(boolean landscape) {
        try {
            setRequestedOrientation(landscape
                    ? ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
                    : ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
        } catch (Exception ignored) {
            // Some OEMs restrict requested orientation changes; not fatal.
        }
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        // Re-assert system chrome after a rotation (the site's UI is
        // responsive; we only need to keep the immersive flags intact).
    }

    private void hideSystemUi(boolean immersive) {
        final View decor = getWindow().getDecorView();
        if (immersive) {
            decor.setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
        } else {
            decor.postDelayed(() ->
                    decor.setSystemUiVisibility(0), 250);
        }
    }

    // ---------------------------------------------------------------------
    // Navigation + lifecycle
    // ---------------------------------------------------------------------

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (customView != null && customViewVisible) {
            webView.getWebChromeClient().onHideCustomView();
            return;
        }
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onPause() {
        super.onPause();
        // Keep audio/video running while the activity is paused (e.g. screen
        // off), matching a browser's background-play behavior. Auth cookies are
        // never cleared, so the session persists across relaunch.
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.stopLoading();
            webView.removeAllViews();
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}