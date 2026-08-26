package com.revayato.app;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.LayerDrawable;
import android.graphics.drawable.RippleDrawable;
import android.graphics.Typeface;
import android.view.Gravity;
import android.widget.Button;

import androidx.appcompat.widget.AppCompatButton;

/** Shared raised-button treatment for native Android screens. */
final class AppButtonFactory {
    static final int PRIMARY = 0xffd8ff3e;
    static final int INFO = 0xff3b82f6;
    static final int SUCCESS = 0xff22c55e;
    static final int WARNING = 0xfff97316;
    static final int ERROR = 0xffef4444;

    private AppButtonFactory() {}

    static Button create(Context context, String title, int fill, int textColor, int borderColor, float textScale) {
        AppCompatButton button = new AppCompatButton(context);
        button.setText(title);
        button.setTextColor(disabledText(textColor));
        button.setTextSize(14f * textScale);
        button.setAllCaps(false);
        button.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
        button.setGravity(Gravity.CENTER);
        button.setMaxLines(3);
        button.setMinHeight(dp(context, 48));
        button.setMinWidth(dp(context, 48));
        button.setPadding(dp(context, 12), dp(context, 7), dp(context, 12), dp(context, 7));
        button.setStateListAnimator(null);
        button.setElevation(fill == Color.TRANSPARENT ? 0 : dp(context, 4));
        button.setBackground(background(context, fill, borderColor));
        return button;
    }

    static void restyle(Button button, int fill, int textColor, int borderColor) {
        button.setTextColor(disabledText(textColor));
        button.setElevation(fill == Color.TRANSPARENT ? 0 : dp(button.getContext(), 4));
        button.setBackground(background(button.getContext(), fill, borderColor));
    }

    static int borderFor(int fill) {
        if (fill == PRIMARY) return 0xffb6da25;
        if (fill == INFO) return 0xff2563eb;
        if (fill == SUCCESS) return 0xff16a34a;
        if (fill == WARNING) return 0xffea580c;
        if (fill == ERROR) return 0xffdc2626;
        if (fill == Color.TRANSPARENT) return 0x334c5f53;
        return 0xff35463c;
    }

    private static RippleDrawable background(Context context, int fill, int border) {
        int radius = dp(context, 12);
        GradientDrawable base;
        if (fill == Color.TRANSPARENT) {
            base = new GradientDrawable();
            base.setColor(Color.TRANSPARENT);
        } else {
            base = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{mix(fill, Color.WHITE, .12f), fill, mix(fill, Color.BLACK, .18f)}
            );
        }
        base.setCornerRadius(radius);
        base.setStroke(dp(context, 1), border);

        GradientDrawable sheen = new GradientDrawable(
            GradientDrawable.Orientation.TOP_BOTTOM,
            new int[]{0x38ffffff, 0x08ffffff, 0x26000000}
        );
        sheen.setCornerRadius(radius);
        sheen.setStroke(dp(context, 1), fill == Color.TRANSPARENT ? 0x18ffffff : 0x30ffffff);

        LayerDrawable layers = new LayerDrawable(new android.graphics.drawable.Drawable[]{base, sheen});
        GradientDrawable mask = new GradientDrawable();
        mask.setColor(Color.WHITE);
        mask.setCornerRadius(radius);
        int ripple = fill == PRIMARY ? 0x33000000 : 0x33ffffff;
        return new RippleDrawable(ColorStateList.valueOf(ripple), layers, mask);
    }

    private static ColorStateList disabledText(int enabled) {
        return new ColorStateList(
            new int[][]{new int[]{-android.R.attr.state_enabled}, new int[]{}},
            new int[]{mix(enabled, Color.TRANSPARENT, .48f), enabled}
        );
    }

    private static int mix(int first, int second, float amount) {
        float keep = 1f - amount;
        return Color.argb(
            Math.round(Color.alpha(first) * keep + Color.alpha(second) * amount),
            Math.round(Color.red(first) * keep + Color.red(second) * amount),
            Math.round(Color.green(first) * keep + Color.green(second) * amount),
            Math.round(Color.blue(first) * keep + Color.blue(second) * amount)
        );
    }

    private static int dp(Context context, int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }
}
