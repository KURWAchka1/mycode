package app.playerokmonitor;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.widget.TextView;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

final class Ui {
    static final int BG = Color.rgb(246, 247, 249);
    static final int CARD = Color.WHITE;
    static final int TEXT = Color.rgb(31, 35, 41);
    static final int MUTED = Color.rgb(111, 118, 129);
    static final int ACCENT = Color.rgb(82, 66, 214);
    static final int GREEN = Color.rgb(31, 145, 84);
    static final int GREEN_BG = Color.rgb(232, 247, 238);
    static final int RED = Color.rgb(196, 54, 54);
    static final int RED_BG = Color.rgb(255, 235, 235);
    static final int AMBER = Color.rgb(166, 103, 0);
    static final int AMBER_BG = Color.rgb(255, 246, 222);
    static final int BORDER = Color.rgb(229, 232, 237);

    private Ui() {}

    static int dp(Context c, int value) {
        return Math.round(value * c.getResources().getDisplayMetrics().density);
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

    static TextView text(Context c, String value, float sp, int color, boolean bold) {
        TextView v = new TextView(c);
        v.setText(value);
        v.setTextSize(sp);
        v.setTextColor(color);
        v.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        if (bold) v.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return v;
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
