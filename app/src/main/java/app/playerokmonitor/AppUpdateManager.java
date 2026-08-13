package app.playerokmonitor;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.widget.TextView;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** A small self-updater for the personal GitHub-distributed Android build. */
final class AppUpdateManager {
    private static final String RELEASES_API =
            "https://api.github.com/repos/KURWAchka1/mycode/releases?per_page=20";
    private static final String DOWNLOAD_PREFIX =
            "https://github.com/KURWAchka1/mycode/releases/download/";
    private static final Pattern ANDROID_TAG = Pattern.compile(
            "^v(\\d+)\\.(\\d+)\\.(\\d+)-oneui85$");
    private static final Pattern SHA256 = Pattern.compile("(?i)^([0-9a-f]{64})(?:\\s+.*)?$");
    private static final long AUTO_CHECK_INTERVAL_MS = 12L * 60L * 60L * 1000L;
    private static final long MAX_RELEASES_BYTES = 2L * 1024L * 1024L;
    private static final long MAX_CHECKSUM_BYTES = 8L * 1024L;
    private static final long MAX_APK_BYTES = 120L * 1024L * 1024L;
    private static final String PREFS = "app_updates";
    private static final String KEY_LAST_CHECK = "last_check";
    private static final String KEY_LAST_PROMPTED = "last_prompted";
    private static final String KEY_PENDING_APK = "pending_apk";
    private static final String KEY_AWAITING_PERMISSION = "awaiting_permission";
    private static final AtomicBoolean BUSY = new AtomicBoolean(false);

    private AppUpdateManager() {}

    static String currentVersion(Context context) {
        try {
            return context.getPackageManager()
                    .getPackageInfo(context.getPackageName(), 0).versionName;
        } catch (Exception ignored) {
            return "неизвестна";
        }
    }

    static void checkAndOffer(
            Activity activity,
            ExecutorService executor,
            boolean manual,
            TextView status
    ) {
        SharedPreferences prefs = prefs(activity);
        long now = System.currentTimeMillis();
        if (!manual && now - prefs.getLong(KEY_LAST_CHECK, 0L) < AUTO_CHECK_INTERVAL_MS) return;
        if (!BUSY.compareAndSet(false, true)) {
            if (manual) setStatus(activity, status, "Проверка обновления уже выполняется…");
            return;
        }
        setStatus(activity, status, "Проверяю обновления…");
        executor.execute(() -> {
            try {
                Release release = findNewestRelease();
                prefs.edit().putLong(KEY_LAST_CHECK, System.currentTimeMillis()).apply();
                if (release == null || compareVersions(release.versionName, currentVersion(activity)) <= 0) {
                    if (manual) setStatus(activity, status,
                            "Установлена актуальная версия " + currentVersion(activity));
                    return;
                }
                if (!manual && release.versionName.equals(prefs.getString(KEY_LAST_PROMPTED, ""))) return;
                prefs.edit().putString(KEY_LAST_PROMPTED, release.versionName).apply();
                runIfAlive(activity, () -> showOffer(activity, executor, release, status));
            } catch (Exception error) {
                if (manual) setStatus(activity, status,
                        "Не удалось проверить обновление: " + friendly(error));
            } finally {
                BUSY.set(false);
            }
        });
    }

    static void resumePendingInstall(Activity activity) {
        SharedPreferences prefs = prefs(activity);
        if (!prefs.getBoolean(KEY_AWAITING_PERMISSION, false)) return;
        if (Build.VERSION.SDK_INT >= 26 &&
                !activity.getPackageManager().canRequestPackageInstalls()) return;
        String path = prefs.getString(KEY_PENDING_APK, "");
        if (path == null || path.isEmpty()) return;
        File apk = new File(path);
        try {
            ensureInsideUpdateCache(activity, apk);
            validateApk(activity, apk);
            prefs.edit().putBoolean(KEY_AWAITING_PERMISSION, false).apply();
            launchInstaller(activity, apk);
        } catch (Exception error) {
            prefs.edit().remove(KEY_PENDING_APK).putBoolean(KEY_AWAITING_PERMISSION, false).apply();
            Toast.makeText(activity, "Файл обновления недействителен: " + friendly(error),
                    Toast.LENGTH_LONG).show();
        }
    }

    private static void showOffer(
            Activity activity,
            ExecutorService executor,
            Release release,
            TextView status
    ) {
        String message = "Установлена " + currentVersion(activity) + ".\n\n" + release.notes;
        new AlertDialog.Builder(activity)
                .setTitle("Доступно обновление " + release.versionName)
                .setMessage(message.trim())
                .setNegativeButton("Позже", null)
                .setPositiveButton("Обновить", (dialog, which) ->
                        downloadAndInstall(activity, executor, release, status))
                .show();
        setStatus(activity, status, "Доступна версия " + release.versionName);
    }

    private static void downloadAndInstall(
            Activity activity,
            ExecutorService executor,
            Release release,
            TextView status
    ) {
        if (!BUSY.compareAndSet(false, true)) return;
        setStatus(activity, status, "Скачиваю обновление " + release.versionName + "…");
        executor.execute(() -> {
            File temp = null;
            try {
                String checksumText = readText(release.checksumUrl, MAX_CHECKSUM_BYTES);
                Matcher checksumMatch = SHA256.matcher(checksumText.trim().split("\\R", 2)[0].trim());
                if (!checksumMatch.matches()) throw new IllegalStateException("неверная контрольная сумма релиза");
                String expectedSha256 = checksumMatch.group(1).toLowerCase(Locale.ROOT);

                File directory = updateDirectory(activity);
                temp = new File(directory, "playerok-monitor-" + release.versionName + ".download");
                File apk = new File(directory, "playerok-monitor-" + release.versionName + ".apk");
                download(release.apkUrl, temp, MAX_APK_BYTES);
                String actualSha256 = fileSha256(temp);
                if (!expectedSha256.equals(actualSha256))
                    throw new SecurityException("контрольная сумма APK не совпала");
                if (apk.exists() && !apk.delete()) throw new IllegalStateException("не удалось заменить старый APK");
                if (!temp.renameTo(apk)) throw new IllegalStateException("не удалось подготовить APK");
                temp = null;
                validateApk(activity, apk);
                prefs(activity).edit().putString(KEY_PENDING_APK, apk.getAbsolutePath()).apply();
                setStatus(activity, status, "Обновление скачано — подтвердите установку Android");
                runIfAlive(activity, () -> requestInstall(activity, apk));
            } catch (Exception error) {
                if (temp != null && temp.exists()) temp.delete();
                setStatus(activity, status, "Не удалось установить обновление: " + friendly(error));
            } finally {
                BUSY.set(false);
            }
        });
    }

    private static void requestInstall(Activity activity, File apk) {
        if (Build.VERSION.SDK_INT >= 26 &&
                !activity.getPackageManager().canRequestPackageInstalls()) {
            prefs(activity).edit().putBoolean(KEY_AWAITING_PERMISSION, true).apply();
            new AlertDialog.Builder(activity)
                    .setTitle("Разрешите установку обновления")
                    .setMessage("Android один раз попросит разрешить установку из Playerok Monitor. " +
                            "После возврата откроется штатное системное подтверждение обновления.")
                    .setNegativeButton("Не сейчас", null)
                    .setPositiveButton("Открыть настройки", (dialog, which) -> {
                        Intent intent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                Uri.parse("package:" + activity.getPackageName()));
                        if (intent.resolveActivity(activity.getPackageManager()) != null) activity.startActivity(intent);
                        else Toast.makeText(activity, "Откройте разрешение установки приложений вручную",
                                Toast.LENGTH_LONG).show();
                    })
                    .show();
            return;
        }
        prefs(activity).edit().putBoolean(KEY_AWAITING_PERMISSION, false).apply();
        launchInstaller(activity, apk);
    }

    private static void launchInstaller(Activity activity, File apk) {
        Uri uri = FileProvider.getUriForFile(
                activity, activity.getPackageName() + ".updates", apk);
        Intent intent = new Intent(Intent.ACTION_INSTALL_PACKAGE)
                .setData(uri)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                .putExtra(Intent.EXTRA_NOT_UNKNOWN_SOURCE, true)
                .putExtra(Intent.EXTRA_RETURN_RESULT, false);
        activity.startActivity(intent);
    }

    private static Release findNewestRelease() throws Exception {
        JSONArray releases = new JSONArray(readText(RELEASES_API, MAX_RELEASES_BYTES));
        Release newest = null;
        for (int index = 0; index < releases.length(); index++) {
            JSONObject release = releases.optJSONObject(index);
            if (release == null || release.optBoolean("draft") || release.optBoolean("prerelease")) continue;
            String tag = release.optString("tag_name", "");
            Matcher tagMatch = ANDROID_TAG.matcher(tag);
            if (!tagMatch.matches()) continue;
            String version = tagMatch.group(1) + "." + tagMatch.group(2) + "." + tagMatch.group(3);
            String apkName = "PlayerokMonitor-OneUI85-v" + version + ".apk";
            String checksumName = apkName + ".sha256";
            String apkUrl = null;
            String checksumUrl = null;
            JSONArray assets = release.optJSONArray("assets");
            if (assets == null) continue;
            for (int assetIndex = 0; assetIndex < assets.length(); assetIndex++) {
                JSONObject asset = assets.optJSONObject(assetIndex);
                if (asset == null || !"uploaded".equals(asset.optString("state"))) continue;
                String name = asset.optString("name", "");
                String url = asset.optString("browser_download_url", "");
                if (apkName.equals(name)) apkUrl = url;
                if (checksumName.equals(name)) checksumUrl = url;
            }
            if (!safeDownloadUrl(apkUrl, tag, apkName) || !safeDownloadUrl(checksumUrl, tag, checksumName)) continue;
            Release candidate = new Release(version, apkUrl, checksumUrl,
                    shortNotes(release.optString("body", "")));
            if (newest == null || compareVersions(candidate.versionName, newest.versionName) > 0) newest = candidate;
        }
        return newest;
    }

    private static boolean safeDownloadUrl(String url, String tag, String fileName) {
        return url != null && url.equals(DOWNLOAD_PREFIX + tag + "/" + fileName);
    }

    static int compareVersions(String left, String right) {
        int[] a = parseVersion(left);
        int[] b = parseVersion(right);
        for (int index = 0; index < 3; index++) {
            int result = Integer.compare(a[index], b[index]);
            if (result != 0) return result;
        }
        return 0;
    }

    private static int[] parseVersion(String value) {
        Matcher matcher = Pattern.compile("^(\\d+)\\.(\\d+)\\.(\\d+).*$")
                .matcher(value == null ? "" : value.trim());
        if (!matcher.matches()) return new int[]{0, 0, 0};
        return new int[]{
                Integer.parseInt(matcher.group(1)),
                Integer.parseInt(matcher.group(2)),
                Integer.parseInt(matcher.group(3))
        };
    }

    private static String readText(String url, long maximumBytes) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (BufferedInputStream input = open(url)) {
            copyLimited(input, output, maximumBytes);
        }
        return output.toString(StandardCharsets.UTF_8.name());
    }

    private static void download(String url, File destination, long maximumBytes) throws Exception {
        try (BufferedInputStream input = open(url);
             FileOutputStream output = new FileOutputStream(destination, false)) {
            copyLimited(input, output, maximumBytes);
        }
    }

    private static BufferedInputStream open(String url) throws Exception {
        URL parsed = new URL(url);
        if (!"https".equalsIgnoreCase(parsed.getProtocol())) throw new SecurityException("разрешён только HTTPS");
        HttpURLConnection connection = (HttpURLConnection) parsed.openConnection();
        connection.setConnectTimeout(15_000);
        connection.setReadTimeout(30_000);
        connection.setInstanceFollowRedirects(true);
        connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "application/vnd.github+json, application/octet-stream, text/plain");
        connection.setRequestProperty("User-Agent", "PlayerokMonitor-Android-Updater/2.3.18");
        int code = connection.getResponseCode();
        if (code < 200 || code >= 300) {
            connection.disconnect();
            throw new IllegalStateException("GitHub ответил HTTP " + code);
        }
        long length = connection.getContentLengthLong();
        if (length > MAX_APK_BYTES) {
            connection.disconnect();
            throw new IllegalStateException("файл обновления слишком большой");
        }
        return new BufferedInputStream(connection.getInputStream()) {
            @Override public void close() throws java.io.IOException {
                try { super.close(); } finally { connection.disconnect(); }
            }
        };
    }

    private static void copyLimited(java.io.InputStream input, java.io.OutputStream output, long maximum)
            throws Exception {
        byte[] buffer = new byte[32 * 1024];
        long total = 0L;
        int read;
        while ((read = input.read(buffer)) != -1) {
            total += read;
            if (total > maximum) throw new IllegalStateException("ответ превышает безопасный размер");
            output.write(buffer, 0, read);
        }
    }

    private static String fileSha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileInputStream input = new FileInputStream(file)) {
            byte[] buffer = new byte[32 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) digest.update(buffer, 0, read);
        }
        return hex(digest.digest());
    }

    private static void validateApk(Context context, File apk) throws Exception {
        ensureInsideUpdateCache(context, apk);
        PackageManager manager = context.getPackageManager();
        int signatureFlags = Build.VERSION.SDK_INT >= 28
                ? PackageManager.GET_SIGNING_CERTIFICATES
                : PackageManager.GET_SIGNATURES;
        PackageInfo archive = manager.getPackageArchiveInfo(apk.getAbsolutePath(), signatureFlags);
        if (archive == null) throw new SecurityException("Android не распознал APK");
        if (!context.getPackageName().equals(archive.packageName))
            throw new SecurityException("другое имя пакета");
        PackageInfo installed = manager.getPackageInfo(context.getPackageName(), signatureFlags);
        if (longVersion(archive) <= longVersion(installed))
            throw new SecurityException("версия APK не новее установленной");
        String[] archiveSigners = signerDigests(archive);
        String[] installedSigners = signerDigests(installed);
        Arrays.sort(archiveSigners);
        Arrays.sort(installedSigners);
        if (!Arrays.equals(archiveSigners, installedSigners))
            throw new SecurityException("подпись APK не принадлежит установленному приложению");
    }

    private static long longVersion(PackageInfo info) {
        return Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode;
    }

    @SuppressWarnings("deprecation")
    private static String[] signerDigests(PackageInfo info) throws Exception {
        Signature[] signatures;
        if (Build.VERSION.SDK_INT >= 28) {
            if (info.signingInfo == null) throw new SecurityException("APK не подписан");
            signatures = info.signingInfo.hasMultipleSigners()
                    ? info.signingInfo.getApkContentsSigners()
                    : info.signingInfo.getSigningCertificateHistory();
        } else {
            signatures = info.signatures;
        }
        if (signatures == null || signatures.length == 0) throw new SecurityException("APK не подписан");
        String[] result = new String[signatures.length];
        for (int index = 0; index < signatures.length; index++) {
            result[index] = hex(MessageDigest.getInstance("SHA-256").digest(signatures[index].toByteArray()));
        }
        return result;
    }

    private static String hex(byte[] bytes) {
        StringBuilder output = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) output.append(String.format(Locale.ROOT, "%02x", value & 0xff));
        return output.toString();
    }

    private static File updateDirectory(Context context) throws Exception {
        File directory = new File(context.getCacheDir(), "updates");
        if (!directory.exists() && !directory.mkdirs()) throw new IllegalStateException("не удалось создать кэш обновлений");
        return directory;
    }

    private static void ensureInsideUpdateCache(Context context, File file) throws Exception {
        String root = updateDirectory(context).getCanonicalPath() + File.separator;
        if (!file.getCanonicalPath().startsWith(root)) throw new SecurityException("недопустимый путь APK");
        if (!file.isFile() || file.length() <= 0L) throw new SecurityException("APK отсутствует");
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static void setStatus(Activity activity, TextView status, String text) {
        if (status == null) return;
        runIfAlive(activity, () -> status.setText(text));
    }

    private static void runIfAlive(Activity activity, Runnable action) {
        activity.runOnUiThread(() -> {
            if (!activity.isFinishing() && !activity.isDestroyed()) action.run();
        });
    }

    private static String shortNotes(String markdown) {
        if (markdown == null || markdown.trim().isEmpty()) return "Исправления и новые возможности готовы к установке.";
        String clean = markdown.replace("\r", "")
                .replaceAll("(?m)^#{1,6}\\s*", "")
                .replaceAll("(?m)^[-*]\\s+", "• ")
                .replaceAll("`", "")
                .trim();
        return clean.length() <= 650 ? clean : clean.substring(0, 647).trim() + "…";
    }

    private static String friendly(Exception error) {
        String message = error.getMessage();
        return message == null || message.trim().isEmpty()
                ? error.getClass().getSimpleName()
                : message.trim();
    }

    private static final class Release {
        final String versionName;
        final String apkUrl;
        final String checksumUrl;
        final String notes;

        Release(String versionName, String apkUrl, String checksumUrl, String notes) {
            this.versionName = versionName;
            this.apkUrl = apkUrl;
            this.checksumUrl = checksumUrl;
            this.notes = notes;
        }
    }
}
