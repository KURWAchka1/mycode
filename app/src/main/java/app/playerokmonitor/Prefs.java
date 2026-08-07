package app.playerokmonitor;

import android.content.Context;
import android.content.SharedPreferences;

final class Prefs {
    private static final String NAME = "playerok_monitor";
    private static final String KEY_URL = "pairing_url";
    private static final String KEY_ENABLED = "monitor_enabled";
    private static final String KEY_LAST_ID = "last_event_id";

    private Prefs() {}

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(NAME, Context.MODE_PRIVATE);
    }

    static String getUrl(Context context) {
        return prefs(context).getString(KEY_URL, "");
    }

    static void setUrl(Context context, String url) {
        prefs(context).edit().putString(KEY_URL, url).apply();
    }

    static boolean isEnabled(Context context) {
        return prefs(context).getBoolean(KEY_ENABLED, false);
    }

    static void setEnabled(Context context, boolean enabled) {
        prefs(context).edit().putBoolean(KEY_ENABLED, enabled).apply();
    }

    static long getLastEventId(Context context) {
        return prefs(context).getLong(KEY_LAST_ID, 0L);
    }

    static void setLastEventId(Context context, long id) {
        prefs(context).edit().putLong(KEY_LAST_ID, id).apply();
    }
}
