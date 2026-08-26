package com.revayato.app;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Handler;
import android.os.Looper;
import android.widget.ImageView;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.lang.ref.WeakReference;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Collections;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Small lifecycle-safe image pipeline with bounded memory and sampled decoding. */
final class ImageLoader {
    private static final int MAX_BYTES = (int) Math.min(48L * 1024 * 1024,
            Runtime.getRuntime().maxMemory() / 8L);
    private static final android.util.LruCache<String, Bitmap> MEMORY =
            new android.util.LruCache<String, Bitmap>(MAX_BYTES) {
                @Override protected int sizeOf(String key, Bitmap value) {
                    return value.getAllocationByteCount();
                }
            };
    private static final ExecutorService WORKERS = Executors.newFixedThreadPool(4);
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final Set<String> IN_FLIGHT = Collections.newSetFromMap(new ConcurrentHashMap<>());

    static void load(String source, ImageView target, int fallbackWidthPx) {
        if (source == null || source.trim().isEmpty()) return;
        target.setTag(source);
        Bitmap cached = MEMORY.get(source);
        if (cached != null) {
            target.setImageBitmap(cached);
            target.setAlpha(1f);
            return;
        }
        if (!IN_FLIGHT.add(source)) {
            MAIN.postDelayed(() -> load(source, target, fallbackWidthPx), 90);
            return;
        }
        WeakReference<ImageView> reference = new WeakReference<>(target);
        WORKERS.execute(() -> {
            try {
                byte[] bytes = download(source);
                Bitmap bitmap = decodeSampled(bytes, Math.max(320, fallbackWidthPx));
                if (bitmap != null) {
                    MEMORY.put(source, bitmap);
                    MAIN.post(() -> {
                        ImageView view = reference.get();
                        if (view != null && source.equals(view.getTag())) {
                            view.setImageBitmap(bitmap);
                            view.animate().alpha(1f).setDuration(180).start();
                        }
                    });
                }
            } catch (Exception ignored) {
                // Keep the neutral placeholder; catalog browsing must never fail for artwork.
            } finally {
                IN_FLIGHT.remove(source);
            }
        });
    }

    private static byte[] download(String source) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(source).openConnection();
        connection.setConnectTimeout(8_000);
        connection.setReadTimeout(12_000);
        connection.setUseCaches(true);
        connection.setRequestProperty("Accept", "image/avif,image/webp,image/*,*/*;q=0.8");
        connection.setRequestProperty("User-Agent", "RevayatoAndroid/5.0");
        connection.setRequestProperty("Referer", "https://revayato.com/");
        try (InputStream input = new BufferedInputStream(connection.getInputStream());
             ByteArrayOutputStream output = new ByteArrayOutputStream(64 * 1024)) {
            byte[] buffer = new byte[16 * 1024];
            for (int count; (count = input.read(buffer)) != -1;) output.write(buffer, 0, count);
            return output.toByteArray();
        } finally {
            connection.disconnect();
        }
    }

    private static Bitmap decodeSampled(byte[] bytes, int targetWidth) {
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
        int sample = 1;
        while (bounds.outWidth / (sample * 2) >= targetWidth) sample *= 2;
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = sample;
        options.inPreferredConfig = Bitmap.Config.RGB_565;
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
    }

    private ImageLoader() {}
}
