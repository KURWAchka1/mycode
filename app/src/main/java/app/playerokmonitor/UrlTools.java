package app.playerokmonitor;

import android.net.Uri;

import java.util.Set;

final class UrlTools {
    private UrlTools() {}

    static String validatePairingUrl(String raw) {
        String value = raw == null ? "" : raw.trim();
        if (value.isEmpty()) return "Вставьте Pairing URL с VPS";
        Uri uri;
        try { uri = Uri.parse(value); } catch (Exception e) { return "Некорректный URL"; }
        if (!"https".equalsIgnoreCase(uri.getScheme())) return "Разрешён только HTTPS";
        if (uri.getHost() == null || uri.getHost().isEmpty()) return "В URL нет адреса VPS";
        if (!"/poll".equals(uri.getPath())) return "Pairing URL должен содержать /poll";
        String token = uri.getQueryParameter("token");
        if (token == null || token.isEmpty()) return "В URL нет API token";
        return null;
    }

    static String pollUrl(String pairingUrl, long after) { return rebuild(pairingUrl, "/poll", after, true, null, null); }
    static String eventsV2Url(String pairingUrl, long after) { return rebuild(pairingUrl, "/poll", after, true, "mode", "eventsv2"); }

    static String ordersUrl(String pairingUrl, long afterRevision, int limit) {
        Uri source = Uri.parse(pairingUrl.trim());
        Uri.Builder builder = baseBuilder(source, "/poll");
        copyAuthParams(source, builder);
        builder.appendQueryParameter("mode", "orders");
        builder.appendQueryParameter("after_rev", Long.toString(Math.max(0L, afterRevision)));
        builder.appendQueryParameter("limit", Integer.toString(Math.max(1, Math.min(200, limit))));
        return builder.build().toString();
    }

    static String healthUrl(String pairingUrl) { return rebuild(pairingUrl, "/health", 0L, false, null, null); }
    static String testUrl(String pairingUrl) { return rebuild(pairingUrl, "/test", 0L, false, null, null); }
    static String cursorUrl(String pairingUrl) { return rebuild(pairingUrl, "/cursor", 0L, false, null, null); }

    private static String rebuild(String raw, String path, long after, boolean includeAfter, String extraName, String extraValue) {
        Uri source = Uri.parse(raw.trim());
        Uri.Builder builder = baseBuilder(source, path);
        copyAuthParams(source, builder);
        if (includeAfter) builder.appendQueryParameter("after", Long.toString(Math.max(0L, after)));
        if (extraName != null) builder.appendQueryParameter(extraName, extraValue == null ? "" : extraValue);
        return builder.build().toString();
    }

    private static Uri.Builder baseBuilder(Uri source, String path) {
        return new Uri.Builder().scheme(source.getScheme()).encodedAuthority(source.getEncodedAuthority()).path(path);
    }

    private static void copyAuthParams(Uri source, Uri.Builder builder) {
        Set<String> names = source.getQueryParameterNames();
        for (String name : names) {
            if ("after".equals(name) || "mode".equals(name) || "after_rev".equals(name) || "limit".equals(name)) continue;
            for (String value : source.getQueryParameters(name)) builder.appendQueryParameter(name, value);
        }
    }
}
