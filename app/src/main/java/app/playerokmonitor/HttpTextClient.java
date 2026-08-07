package app.playerokmonitor;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

final class HttpTextClient {
    private HttpTextClient() {}

    static String get(String url, int readTimeoutMs) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setRequestMethod("GET");
        connection.setConnectTimeout(10_000);
        connection.setReadTimeout(readTimeoutMs);
        connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "text/plain");
        connection.setRequestProperty("User-Agent", "PlayerokMonitor-Android/1.0");
        try {
            int code = connection.getResponseCode();
            InputStream stream = code >= 200 && code < 300
                    ? connection.getInputStream()
                    : connection.getErrorStream();
            String body = readFirstLine(stream);
            if (code < 200 || code >= 300) {
                throw new IllegalStateException("HTTP " + code + ": " + body);
            }
            return body;
        } finally {
            connection.disconnect();
        }
    }

    private static String readFirstLine(InputStream stream) throws Exception {
        if (stream == null) return "";
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line = reader.readLine();
            return line == null ? "" : line;
        }
    }
}
