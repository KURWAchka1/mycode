package app.playerokmonitor;

import android.animation.ValueAnimator;
import android.app.Activity;
import android.content.Context;
import android.content.res.ColorStateList;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.os.Build;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.View;
import android.view.Window;
import android.view.WindowInsetsController;
import android.view.animation.PathInterpolator;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.TextView;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

/** Small, dependency-free One UI presentation layer.
 *
 * Values follow Samsung's public One UI guidance: 24 dp content margins,
 * reachable controls, generous viewing space, 18 dp button radii and the
 * official One UI blue.  Keeping this native avoids a second UI framework on
 * a monitoring app that must remain tiny and dependable.
 */
final class Ui {
    static int BG;
    static int CARD;
    static int SURFACE_2;
    static int TEXT;
    static int MUTED;
    static int ACCENT;
    static int ACCENT_BG;
    static int GREEN;
    static int GREEN_BG;
    static int RED;
    static int RED_BG;
    static int AMBER;
    static int AMBER_BG;
    static int BORDER;
    static int HERO_START;
    static int HERO_END;

    private Ui() {}

    static void configure(Context context) {
        boolean dark = (context.getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        if (dark) {
            BG = Color.rgb(10, 12, 17);
            CARD = Color.rgb(20, 24, 32);
            SURFACE_2 = Color.rgb(28, 33, 43);
            TEXT = Color.rgb(247, 247, 248);
            MUTED = Color.rgb(171, 177, 190);
            ACCENT = Color.rgb(62, 145, 255);      // One UI primary, dark
            ACCENT_BG = Color.rgb(22, 48, 82);
            GREEN = Color.rgb(80, 210, 130);
            GREEN_BG = Color.rgb(20, 55, 38);
            RED = Color.rgb(255, 105, 105);
            RED_BG = Color.rgb(69, 29, 34);
            AMBER = Color.rgb(255, 190, 73);
            AMBER_BG = Color.rgb(65, 48, 22);
            BORDER = Color.rgb(45, 51, 64);
            HERO_START = Color.rgb(23, 43, 75);
            HERO_END = Color.rgb(18, 25, 39);
        } else {
            BG = Color.rgb(246, 247, 250);
            CARD = Color.WHITE;
            SURFACE_2 = Color.rgb(236, 239, 245);
            TEXT = Color.rgb(37, 37, 37);
            MUTED = Color.rgb(104, 104, 109);
            ACCENT = Color.rgb(0, 114, 222);       // One UI primary, light
            ACCENT_BG = Color.rgb(229, 242, 255);
            GREEN = Color.rgb(19, 128, 72);
            GREEN_BG = Color.rgb(231, 247, 237);
            RED = Color.rgb(199, 48, 54);
            RED_BG = Color.rgb(255, 234, 235);
            AMBER = Color.rgb(156, 94, 0);
            AMBER_BG = Color.rgb(255, 245, 218);
            BORDER = Color.rgb(222, 226, 234);
            HERO_START = Color.rgb(220, 237, 255);
            HERO_END = Color.rgb(241, 246, 255);
        }
    }

    static void prepareWindow(Activity activity) {
        configure(activity);
        Window window = activity.getWindow();
        window.setStatusBarColor(BG);
        window.setNavigationBarColor(BG);
        boolean dark = (activity.getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        if (Build.VERSION.SDK_INT >= 30) {
            // PhoneWindow has no DecorView yet when this is called before
            // setContentView(). Asking the decor directly is null-safe during
            // Activity creation and still supplies the correct controller.
            View decor = window.getDecorView();
            WindowInsetsController controller = decor.getWindowInsetsController();
            if (controller != null) {
                int flags = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                        | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                controller.setSystemBarsAppearance(dark ? 0 : flags, flags);
            }
        } else {
            window.getDecorView().setSystemUiVisibility(dark ? 0
                    : View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        }
    }

    static int dp(Context c, int value) {
        return Math.round(value * c.getResources().getDisplayMetrics().density);
    }

    static boolean isWide(Context c) {
        return c.getResources().getConfiguration().smallestScreenWidthDp >= 600;
    }

    static GradientDrawable rounded(Context c, int fill, int radiusDp) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(fill);
        d.setCornerRadius(dp(c, radiusDp));
        return d;
    }

    static GradientDrawable roundedStroke(Context c, int fill, int stroke, int radiusDp) {
        GradientDrawable d = rounded(c, fill, radiusDp);
        d.setStroke(dp(c, 1), stroke);
        return d;
    }

    static RippleDrawable ripple(Context c, int fill, int stroke, int radiusDp) {
        GradientDrawable content = roundedStroke(c, fill, stroke, radiusDp);
        GradientDrawable mask = rounded(c, Color.WHITE, radiusDp);
        return new RippleDrawable(ColorStateList.valueOf(withAlpha(ACCENT, 36)), content, mask);
    }

    static GradientDrawable hero(Context c) {
        GradientDrawable drawable = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{HERO_START, HERO_END}
        );
        drawable.setCornerRadius(dp(c, 28));
        drawable.setStroke(dp(c, 1), withAlpha(ACCENT, 56));
        return drawable;
    }

    static int withAlpha(int color, int alpha) {
        return Color.argb(alpha, Color.red(color), Color.green(color), Color.blue(color));
    }

    static TextView text(Context c, String value, float sp, int color, boolean bold) {
        TextView v = new TextView(c);
        v.setText(value);
        v.setTextSize(sp);
        v.setTextColor(color);
        v.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        if (bold) v.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return v;
    }

    static ImageButton iconButton(Context c, int drawableRes, String description) {
        ImageButton button = new ImageButton(c);
        button.setImageResource(drawableRes);
        button.setContentDescription(description);
        button.setTooltipText(description);
        button.setBackgroundTintList(null);
        button.setBackground(ripple(c, Color.TRANSPARENT, Color.TRANSPARENT, 22));
        button.setImageTintList(ColorStateList.valueOf(TEXT));
        int p = dp(c, 13);
        button.setPadding(p, p, p, p);
        button.setScaleType(ImageButton.ScaleType.CENTER_INSIDE);
        return button;
    }

    static Button button(Context c, String label, boolean primary) {
        Button button = new Button(c);
        button.setText(label);
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setTextColor(primary ? ACCENT : TEXT);
        button.setCompoundDrawableTintList(ColorStateList.valueOf(primary ? ACCENT : TEXT));
        button.setBackgroundTintList(null);
        button.setStateListAnimator(null);
        button.setBackground(ripple(c,
                primary ? withAlpha(ACCENT, 22) : Color.TRANSPARENT,
                primary ? withAlpha(ACCENT, 105) : Color.TRANSPARENT,
                18));
        button.setMinHeight(dp(c, 52));
        button.setPadding(dp(c, 18), dp(c, 8), dp(c, 18), dp(c, 8));
        return button;
    }

    static void styleTab(Context c, TextView tab, boolean selected) {
        tab.setTextColor(selected ? ACCENT : MUTED);
        tab.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        tab.setBackground(ripple(c, Color.TRANSPARENT, Color.TRANSPARENT, 18));
        GradientDrawable indicator = rounded(c, selected ? ACCENT : Color.TRANSPARENT, 2);
        indicator.setSize(dp(c, 24), dp(c, 3));
        tab.setCompoundDrawablesWithIntrinsicBounds(null, null, null, indicator);
        tab.setCompoundDrawablePadding(dp(c, 7));
    }

    static void styleInput(Context c, EditText input) {
        input.setTextColor(TEXT);
        input.setHintTextColor(MUTED);
        input.setBackgroundTintList(null);
        input.setBackground(ripple(c, Color.TRANSPARENT, BORDER, 18));
        input.setPadding(dp(c, 16), dp(c, 12), dp(c, 16), dp(c, 12));
        input.setOnFocusChangeListener((view, focused) -> {
            if (!focused) return;
            view.postDelayed(() -> view.requestRectangleOnScreen(
                    new Rect(0, 0, view.getWidth(), view.getHeight()), true), 180L);
        });
    }

    static void elevate(View view, int dp) {
        if (Build.VERSION.SDK_INT >= 21) view.setElevation(Ui.dp(view.getContext(), dp));
    }

    static void haptic(View view) {
        view.performHapticFeedback(Build.VERSION.SDK_INT >= 30
                ? HapticFeedbackConstants.CONFIRM : HapticFeedbackConstants.VIRTUAL_KEY);
    }

    static void reveal(View view) {
        if (!ValueAnimator.areAnimatorsEnabled()) return;
        view.setAlpha(0f);
        view.setTranslationY(dp(view.getContext(), 10));
        view.animate()
                .alpha(1f)
                .translationY(0f)
                .setDuration(260L)
                .setInterpolator(new PathInterpolator(0.22f, 0.25f, 0f, 1f))
                .start();
    }

    static String formatDate(String raw) {
        if (raw == null || raw.trim().isEmpty()) return "—";
        try {
            Instant instant = OffsetDateTime.parse(raw).toInstant();
            DateTimeFormatter f = DateTimeFormatter.ofPattern("d MMM, HH:mm", new Locale("ru"))
                    .withZone(ZoneId.systemDefault());
            return f.format(instant);
        } catch (Exception ignored) {
            try {
                Instant instant = Instant.parse(raw);
                DateTimeFormatter f = DateTimeFormatter.ofPattern("d MMM, HH:mm", new Locale("ru"))
                        .withZone(ZoneId.systemDefault());
                return f.format(instant);
            } catch (Exception ignored2) {
                return raw;
            }
        }
    }
}
