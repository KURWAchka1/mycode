package app.playerokmonitor;

import android.net.Uri;

import java.util.Set;

final class UrlTools {
    private UrlTools() {}

    static String validatePairingUrl(String raw) {
        String value = raw == null ? "" : raw.trim();
        if (value.isEmpty()) return "Вставьте Pairing URL с VPS";
        Uri uri;
        try {
            uri = Uri.parse(value);
        } catch (Exception e) {
            return "Некорректный URL";
        }
        if (!"https".equalsIgnoreCase(uri.getScheme())) return "Разрешён только HTTPS";
        if (uri.getHost() == null || uri.getHost().isEmpty()) return "В URL нет адреса VPS";
        if (!"/poll".equals(uri.getPath())) return "Pairing URL должен содержать /poll";
        String token = uri.getQueryParameter("token");
        if (token == null || token.isEmpty()) return "В URL нет API token";
        return null;
    }

    static String pollUrl(String pairingUrl, long after) {
        return rebuild(pairingUrl, "/poll", after, true);
    }

    static String healthUrl(String pairingUrl) {
        return rebuild(pairingUrl, "/health", 0L, false);
    }

    static String testUrl(String pairingUrl) {
        return rebuild(pairingUrl, "/test", 0L, false);
    }

    private static String rebuild(String raw, String path, long after, boolean includeAfter) {
        Uri source = Uri.parse(raw.trim());
        Uri.Builder builder = new Uri.Builder()
                .scheme(source.getScheme())
                .encodedAuthority(source.getEncodedAuthority())
                .path(path);

        Set<String> names = source.getQueryParameterNames();
        for (String name : names) {
            if ("after".equals(name)) continue;
            for (String value : source.getQueryParameters(name)) {
                builder.appendQueryParameter(name, value);
            }
        }
        if (includeAfter) builder.appendQueryParameter("after", Long.toString(Math.max(0L, after)));
        return builder.build().toString();
    }
}
