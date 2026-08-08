package app.playerokmonitor;

import android.content.Context;
import android.content.SharedPreferences;

final class Prefs {
    private static final String NAME = "playerok_monitor";
    private static final String KEY_URL = "pairing_url";
    private static final String KEY_ENABLED = "monitor_enabled";
    private static final String KEY_LAST_ID = "last_event_id";
    private static final String KEY_ORDERS_REVISION = "orders_revision";
    private static final String KEY_ORDERS_JSON = "orders_json";
    private static final String KEY_BOOTSTRAPPED_URL = "events_bootstrapped_url";

    private Prefs() {}
    static SharedPreferences prefs(Context context) { return context.getSharedPreferences(NAME, Context.MODE_PRIVATE); }
    static String getUrl(Context context) { return prefs(context).getString(KEY_URL, ""); }
    static void setUrl(Context context, String url) {
        String normalized = url == null ? "" : url.trim();
        SharedPreferences p = prefs(context);
        String previous = p.getString(KEY_URL, "");
        SharedPreferences.Editor edit = p.edit().putString(KEY_URL, normalized);
        if (!normalized.equals(previous)) {
            edit.putLong(KEY_LAST_ID, 0L)
                    .remove(KEY_BOOTSTRAPPED_URL)
                    .putLong(KEY_ORDERS_REVISION, 0L)
                    .putString(KEY_ORDERS_JSON, "[]");
        }
        edit.apply();
    }
    static boolean isEnabled(Context context) { return prefs(context).getBoolean(KEY_ENABLED, false); }
    static void setEnabled(Context context, boolean enabled) { prefs(context).edit().putBoolean(KEY_ENABLED, enabled).apply(); }
    static long getLastEventId(Context context) { return prefs(context).getLong(KEY_LAST_ID, 0L); }
    static void setLastEventId(Context context, long id) { prefs(context).edit().putLong(KEY_LAST_ID, id).apply(); }
    static long getOrdersRevision(Context context) { return prefs(context).getLong(KEY_ORDERS_REVISION, 0L); }
    static void setOrdersRevision(Context context, long revision) { prefs(context).edit().putLong(KEY_ORDERS_REVISION, Math.max(0L, revision)).apply(); }
    static String getOrdersJson(Context context) { return prefs(context).getString(KEY_ORDERS_JSON, "[]"); }
    static void setOrdersJson(Context context, String json) { prefs(context).edit().putString(KEY_ORDERS_JSON, json == null ? "[]" : json).apply(); }
    static boolean isEventStreamBootstrapped(Context context, String pairingUrl) {
        String normalized = pairingUrl == null ? "" : pairingUrl.trim();
        SharedPreferences p = prefs(context);
        String bootstrapped = p.getString(KEY_BOOTSTRAPPED_URL, "");
        if (normalized.equals(bootstrapped) && !normalized.isEmpty()) return true;
        // Upgrade path: earlier builds already consumed events but had no marker.
        return bootstrapped.isEmpty()
                && normalized.equals(p.getString(KEY_URL, ""))
                && p.getLong(KEY_LAST_ID, 0L) > 0L;
    }
    static void markEventStreamBootstrapped(Context context, String pairingUrl, long cursor) {
        prefs(context).edit()
                .putLong(KEY_LAST_ID, Math.max(0L, cursor))
                .putString(KEY_BOOTSTRAPPED_URL, pairingUrl == null ? "" : pairingUrl.trim())
                .apply();
    }
}
