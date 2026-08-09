package app.playerokmonitor;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

final class HttpTextClient {
    private HttpTextClient() {}

    static String get(String url, int readTimeoutMs) throws Exception {
        return request("GET", url, readTimeoutMs, null, null);
    }

    static String post(String url, int readTimeoutMs) throws Exception {
        return request("POST", url, readTimeoutMs, new byte[0], null);
    }

    static String postJson(String url, String json, int readTimeoutMs) throws Exception {
        byte[] body = (json == null ? "{}" : json).getBytes(StandardCharsets.UTF_8);
        return request("POST", url, readTimeoutMs, body, "application/json; charset=utf-8");
    }

    private static String request(
            String method,
            String url,
            int readTimeoutMs,
            byte[] body,
            String contentType
    ) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(10_000);
        connection.setReadTimeout(readTimeoutMs);
        connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "application/json, text/plain, */*");
        connection.setRequestProperty("User-Agent", "PlayerokMonitor-Android/2.3 OneUI");
        if ("POST".equals(method)) {
            connection.setDoOutput(true);
            byte[] payload = body == null ? new byte[0] : body;
            connection.setFixedLengthStreamingMode(payload.length);
            if (contentType != null) connection.setRequestProperty("Content-Type", contentType);
        }
        try {
            if ("POST".equals(method)) {
                byte[] payload = body == null ? new byte[0] : body;
                try (OutputStream output = connection.getOutputStream()) {
                    output.write(payload);
                }
            }
            int code = connection.getResponseCode();
            InputStream stream = code >= 200 && code < 300 ? connection.getInputStream() : connection.getErrorStream();
            String responseBody = readFirstLine(stream);
            if (code < 200 || code >= 300)
                throw new IllegalStateException("HTTP " + code + ": " + responseBody);
            return responseBody;
        } finally { connection.disconnect(); }
    }

    private static String readFirstLine(InputStream stream) throws Exception {
        if (stream == null) return "";
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line = reader.readLine();
            return line == null ? "" : line;
        }
    }
}
