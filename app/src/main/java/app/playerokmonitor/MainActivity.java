package app.playerokmonitor;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Insets;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int REQ_NOTIFICATIONS = 5001;

    private EditText urlInput;
    private TextView statusText;
    private final ExecutorService network = Executors.newSingleThreadExecutor();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        NotificationHelper.ensureChannels(this);
        setContentView(buildUi());
        requestNotificationPermissionIfNeeded();
        refreshStatus();
    }

    private View buildUi() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int p = dp(22);
        root.setPadding(p, p, p, p);
        scroll.addView(root, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT));

        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int left = p, top = p, right = p, bottom = p;
            if (Build.VERSION.SDK_INT >= 30) {
                Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
                left += bars.left;
                top += bars.top;
                right += bars.right;
                bottom += bars.bottom;
            } else {
                left += insets.getSystemWindowInsetLeft();
                top += insets.getSystemWindowInsetTop();
                right += insets.getSystemWindowInsetRight();
                bottom += insets.getSystemWindowInsetBottom();
            }
            v.setPadding(left, top, right, bottom);
            return insets;
        });

        TextView title = new TextView(this);
        title.setText("Playerok Monitor");
        title.setTextSize(30);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        root.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("Мгновенные уведомления о заказах через ваш VPS");
        subtitle.setTextSize(16);
        subtitle.setPadding(0, dp(6), 0, dp(22));
        root.addView(subtitle);

        TextView label = new TextView(this);
        label.setText("Pairing URL");
        label.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        root.addView(label);

        urlInput = new EditText(this);
        urlInput.setSingleLine(false);
        urlInput.setMinLines(2);
        urlInput.setHint("https://example.com/poll?token=...&after=");
        urlInput.setText(Prefs.getUrl(this));
        urlInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT |
                android.text.InputType.TYPE_TEXT_VARIATION_URI |
                android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        root.addView(urlInput, matchWrap());

        Button saveStart = button("Сохранить и запустить мониторинг");
        saveStart.setOnClickListener(v -> saveAndStart());
        root.addView(saveStart, marginTop(16));

        Button health = button("Проверить соединение с VPS");
        health.setOnClickListener(v -> checkServer(false));
        root.addView(health, marginTop(8));

        Button test = button("Тестовое уведомление");
        test.setOnClickListener(v -> checkServer(true));
        root.addView(test, marginTop(8));

        Button stop = button("Остановить мониторинг");
        stop.setOnClickListener(v -> stopMonitoring());
        root.addView(stop, marginTop(8));

        Button notificationSettings = button("Настройки звука уведомлений");
        notificationSettings.setOnClickListener(v -> openNotificationSettings());
        root.addView(notificationSettings, marginTop(8));

        statusText = new TextView(this);
        statusText.setTextSize(15);
        statusText.setPadding(0, dp(22), 0, dp(8));
        root.addView(statusText);

        TextView note = new TextView(this);
        note.setText("Звук заказа воспроизводится только через системный канал уведомлений. " +
                "Беззвучный режим, режим вибрации, DND и отключённый звук канала соблюдаются Android.");
        note.setTextSize(13);
        root.addView(note);

        return scroll;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams marginTop(int dp) {
        LinearLayout.LayoutParams params = matchWrap();
        params.topMargin = dp(dp);
        return params;
    }

    private Button button(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setMinHeight(dp(52));
        return button;
    }

    private void saveAndStart() {
        String url = urlInput.getText().toString().trim();
        String validation = UrlTools.validatePairingUrl(url);
        if (validation != null) {
            toast(validation);
            return;
        }
        if (!notificationsAllowed()) {
            requestNotificationPermissionIfNeeded();
            toast("Разрешите уведомления и нажмите запуск ещё раз");
            return;
        }
        Prefs.setUrl(this, url);
        Prefs.setEnabled(this, true);
        Intent service = new Intent(this, MonitorService.class).setAction(MonitorService.ACTION_START);
        startForegroundService(service);
        refreshStatus();
        toast("Мониторинг запущен");
    }

    private void stopMonitoring() {
        Prefs.setEnabled(this, false);
        Intent service = new Intent(this, MonitorService.class).setAction(MonitorService.ACTION_STOP);
        startService(service);
        refreshStatus();
        toast("Мониторинг остановлен");
    }

    private void checkServer(boolean createTest) {
        String url = urlInput.getText().toString().trim();
        String validation = UrlTools.validatePairingUrl(url);
        if (validation != null) {
            toast(validation);
            return;
        }
        Prefs.setUrl(this, url);
        statusText.setText(createTest ? "Создаю тестовое событие…" : "Проверяю HTTPS…");
        network.execute(() -> {
            try {
                String target = createTest ? UrlTools.testUrl(url) : UrlTools.healthUrl(url);
                String response = HttpTextClient.get(target, 15_000);
                runOnUiThread(() -> {
                    statusText.setText("VPS ответил: " + response);
                    if (createTest && !Prefs.isEnabled(this)) {
                        toast("Тест поставлен в очередь. Запустите мониторинг, чтобы получить уведомление.");
                    }
                });
            } catch (Exception e) {
                runOnUiThread(() -> statusText.setText("Ошибка VPS: " + e.getMessage()));
            }
        });
    }

    private void openNotificationSettings() {
        Intent intent = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName());
        startActivity(intent);
    }

    private boolean notificationsAllowed() {
        if (Build.VERSION.SDK_INT >= 33 &&
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            return false;
        }
        NotificationManager manager = getSystemService(NotificationManager.class);
        return manager.areNotificationsEnabled();
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 &&
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIFICATIONS);
        }
    }

    private void refreshStatus() {
        if (statusText == null) return;
        boolean enabled = Prefs.isEnabled(this);
        statusText.setText(enabled
                ? "Статус: мониторинг включён"
                : "Статус: мониторинг выключен");
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshStatus();
    }

    @Override
    protected void onDestroy() {
        network.shutdownNow();
        super.onDestroy();
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_LONG).show();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
