package app.playerokmonitor;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationManager;
import android.app.TimePickerDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Insets;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.format.DateFormat;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.time.ZoneId;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class SettingsActivity extends Activity {
    private static final int REQ_NOTIFICATIONS = 5002;

    private EditText urlInput;
    private TextView statusText;
    private Switch replyDisabledToggle;
    private LinearLayout replyList;
    private TextView replyStatus;
    private Button addReplyButton;
    private EditText fulfillmentReplyInput;
    private Switch sleepReplyToggle;
    private Button sleepStartButton;
    private Button sleepEndButton;
    private TextView sleepTimezoneText;
    private EditText sleepReplyInput;
    private String sleepStart = "00:00";
    private String sleepEnd = "08:00";
    private String sleepTimezone = "Europe/Moscow";
    private final ArrayList<EditText> replyInputs = new ArrayList<>();
    private String replyDefaultMessage = AutoReplyConfig.DEFAULT_MESSAGE;
    private int maxReplyMessages = AutoReplyConfig.DEFAULT_MAX_MESSAGES;
    private boolean loadingReplySettings;
    private int replyRequestGeneration;
    private final ExecutorService network = Executors.newSingleThreadExecutor();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Ui.prepareWindow(this);
        NotificationHelper.ensureChannels(this);
        setContentView(buildUi());
        requestNotificationPermissionIfNeeded();
        refreshStatus();
        loadAutoReplySettings();
    }

    private View buildUi() {
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Ui.BG);
        scroll.setFillViewport(true);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int p = Ui.dp(this, Ui.isWide(this) ? 48 : 24);
        root.setPadding(p, p, p, p);
        scroll.addView(root, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT));

        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int left = p, top = p, right = p, bottom = p;
            if (Build.VERSION.SDK_INT >= 30) {
                Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
                Insets ime = insets.getInsets(WindowInsets.Type.ime());
                left += bars.left;
                top += bars.top;
                right += bars.right;
                bottom += Math.max(bars.bottom, ime.bottom);
            } else {
                left += insets.getSystemWindowInsetLeft();
                top += insets.getSystemWindowInsetTop();
                right += insets.getSystemWindowInsetRight();
                bottom += insets.getSystemWindowInsetBottom();
            }
            v.setPadding(left, top, right, bottom);
            return insets;
        });

        LinearLayout head = new LinearLayout(this);
        head.setOrientation(LinearLayout.HORIZONTAL);
        head.setGravity(Gravity.CENTER_VERTICAL);
        root.addView(head, matchWrap());

        ImageButton back = Ui.iconButton(this, R.drawable.ic_nav_back, "Назад");
        back.setOnClickListener(v -> { Ui.haptic(v); finish(); });
        head.addView(back, new LinearLayout.LayoutParams(Ui.dp(this, 52), Ui.dp(this, 52)));

        TextView title = Ui.text(this, "Настройки", 30, Ui.TEXT, true);
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        titleParams.leftMargin = Ui.dp(this, 10);
        head.addView(title, titleParams);

        TextView subtitle = Ui.text(this,
                "Подключение, уведомления и сообщения покупателю — в одном месте.",
                14, Ui.MUTED, false);
        LinearLayout.LayoutParams sub = matchWrap();
        sub.topMargin = Ui.dp(this, 14);
        root.addView(subtitle, sub);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(Ui.dp(this, 20), Ui.dp(this, 19), Ui.dp(this, 20), Ui.dp(this, 18));
        card.setBackground(Ui.hero(this));
        Ui.elevate(card, 2);
        LinearLayout.LayoutParams cardParams = matchWrap();
        cardParams.topMargin = Ui.dp(this, 16);
        root.addView(card, cardParams);

        TextView connectionTitle = Ui.text(this, "Подключение к VPS", 20, Ui.TEXT, true);
        card.addView(connectionTitle);
        TextView connectionHint = Ui.text(this,
                "Pairing URL не меняется при обновлении приложения.", 13, Ui.MUTED, false);
        card.addView(connectionHint, marginTop(4));

        TextView label = new TextView(this);
        label.setText("Pairing URL");
        label.setTextColor(Ui.TEXT);
        label.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        card.addView(label, marginTop(16));

        urlInput = new EditText(this);
        urlInput.setSingleLine(false);
        urlInput.setMinLines(2);
        urlInput.setHint("https://example.com/poll?token=...&after=");
        urlInput.setText(Prefs.getUrl(this));
        urlInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT |
                android.text.InputType.TYPE_TEXT_VARIATION_URI |
                android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        Ui.styleInput(this, urlInput);
        card.addView(urlInput, marginTop(8));

        Button saveStart = Ui.button(this, "Сохранить и запустить мониторинг", true);
        saveStart.setOnClickListener(v -> { Ui.haptic(v); saveAndStart(); });
        card.addView(saveStart, marginTop(14));

        Button health = button("Проверить соединение с VPS");
        health.setOnClickListener(v -> { Ui.haptic(v); checkServer(false); });
        card.addView(health, marginTop(8));

        Button test = button("Тестовое уведомление");
        test.setOnClickListener(v -> { Ui.haptic(v); checkServer(true); });
        card.addView(test, marginTop(8));

        Button stop = button("Остановить мониторинг");
        stop.setOnClickListener(v -> { Ui.haptic(v); stopMonitoring(); });
        card.addView(stop, marginTop(8));

        Button notificationSettings = button("Настройки звука уведомлений");
        notificationSettings.setOnClickListener(v -> { Ui.haptic(v); openNotificationSettings(); });
        card.addView(notificationSettings, marginTop(8));

        statusText = Ui.text(this, "", 14, Ui.MUTED, false);
        statusText.setPadding(0, Ui.dp(this, 18), 0, 0);
        card.addView(statusText);

        buildAutoReplyCard(root);

        TextView note = Ui.text(this,
                "Переключение вкладок Продажи/Покупки читает локальный кэш Android. Список синхронизируется с SQLite на VPS и не делает запрос к Playerok при каждом переключении.",
                13, Ui.MUTED, false);
        LinearLayout.LayoutParams noteParams = matchWrap();
        noteParams.topMargin = Ui.dp(this, 16);
        root.addView(note, noteParams);

        Ui.reveal(root);

        return scroll;
    }

    private void buildAutoReplyCard(LinearLayout root) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(Ui.dp(this, 18), Ui.dp(this, 18), Ui.dp(this, 18), Ui.dp(this, 18));
        card.setBackground(Ui.roundedStroke(this, Ui.CARD, Ui.BORDER, 26));
        Ui.elevate(card, 1);
        LinearLayout.LayoutParams cardParams = matchWrap();
        cardParams.topMargin = Ui.dp(this, 16);
        root.addView(card, cardParams);

        TextView title = Ui.text(this, "Сообщения покупателю", 20, Ui.TEXT, true);
        card.addView(title, matchWrap());

        TextView description = Ui.text(this,
                "Настройте оплату, возможный сон и завершение заказа. Пустое поле не отключает сообщение: серый фоновый текст становится действующим значением по умолчанию.",
                13, Ui.MUTED, false);
        card.addView(description, marginTop(5));

        replyDisabledToggle = new Switch(this);
        replyDisabledToggle.setText("Отключить сообщения");
        replyDisabledToggle.setTextColor(Ui.TEXT);
        replyDisabledToggle.setTextSize(16);
        replyDisabledToggle.setPadding(0, Ui.dp(this, 8), 0, Ui.dp(this, 8));
        card.addView(replyDisabledToggle, marginTop(10));

        TextView paidTitle = Ui.text(this, "После оплаты", 16, Ui.TEXT, true);
        card.addView(paidTitle, marginTop(10));

        TextView paidDescription = Ui.text(this,
                "Эти сообщения идут по порядку только покупателю вашего товара.",
                13, Ui.MUTED, false);
        card.addView(paidDescription, marginTop(3));

        replyList = new LinearLayout(this);
        replyList.setOrientation(LinearLayout.VERTICAL);
        card.addView(replyList, marginTop(8));
        addReplyInput("");

        TextView fulfilledTitle = Ui.text(
                this, "После подтверждения выполнения вами", 16, Ui.TEXT, true);
        card.addView(fulfilledTitle, marginTop(18));

        TextView fulfilledDescription = Ui.text(this,
                "Одно сообщение после того, как именно вы подтвердили выполнение своей продажи. Подтверждение чужого продавца в ваших покупках его не запускает.",
                13, Ui.MUTED, false);
        card.addView(fulfilledDescription, marginTop(3));

        fulfillmentReplyInput = new EditText(this);
        fulfillmentReplyInput.setText("");
        fulfillmentReplyInput.setHint(AutoReplyConfig.DEFAULT_FULFILLMENT_MESSAGE);
        fulfillmentReplyInput.setTextColor(Ui.TEXT);
        fulfillmentReplyInput.setHintTextColor(Ui.MUTED);
        fulfillmentReplyInput.setTextSize(15);
        fulfillmentReplyInput.setMinLines(3);
        fulfillmentReplyInput.setMaxLines(6);
        fulfillmentReplyInput.setGravity(Gravity.TOP | Gravity.START);
        fulfillmentReplyInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT |
                android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES |
                android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        Ui.styleInput(this, fulfillmentReplyInput);
        card.addView(fulfillmentReplyInput, marginTop(8));

        TextView sleepTitle = Ui.text(this, "Когда я могу спать", 16, Ui.TEXT, true);
        card.addView(sleepTitle, marginTop(18));

        TextView sleepDescription = Ui.text(this,
                "Если новый заказ оплачен в этот промежуток, покупатель получит только предупреждение о возможном сне. Обычные сообщения после оплаты уйдут, когда вы нажмёте «Я проснулся» в заказе.",
                13, Ui.MUTED, false);
        card.addView(sleepDescription, marginTop(3));

        sleepReplyToggle = new Switch(this);
        sleepReplyToggle.setText("Предупреждать покупателя");
        sleepReplyToggle.setTextColor(Ui.TEXT);
        sleepReplyToggle.setTextSize(16);
        sleepReplyToggle.setPadding(0, Ui.dp(this, 8), 0, Ui.dp(this, 8));
        card.addView(sleepReplyToggle, marginTop(8));

        LinearLayout timeRow = new LinearLayout(this);
        timeRow.setOrientation(LinearLayout.HORIZONTAL);
        timeRow.setGravity(Gravity.CENTER_VERTICAL);
        card.addView(timeRow, marginTop(4));

        sleepStartButton = Ui.button(this, "С 00:00", false);
        sleepStartButton.setOnClickListener(v -> {
            Ui.haptic(v);
            showSleepTimePicker(true);
        });
        timeRow.addView(sleepStartButton, new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        sleepEndButton = Ui.button(this, "До 08:00", false);
        sleepEndButton.setOnClickListener(v -> {
            Ui.haptic(v);
            showSleepTimePicker(false);
        });
        LinearLayout.LayoutParams endTimeParams = new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        endTimeParams.leftMargin = Ui.dp(this, 8);
        timeRow.addView(sleepEndButton, endTimeParams);

        LinearLayout timezoneRow = new LinearLayout(this);
        timezoneRow.setOrientation(LinearLayout.HORIZONTAL);
        timezoneRow.setGravity(Gravity.CENTER_VERTICAL);
        card.addView(timezoneRow, marginTop(8));
        sleepTimezoneText = Ui.text(this, "Часовой пояс: " + sleepTimezone, 13, Ui.MUTED, false);
        timezoneRow.addView(sleepTimezoneText, new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        Button deviceTimezone = Ui.button(this, "С телефона", false);
        deviceTimezone.setOnClickListener(v -> {
            Ui.haptic(v);
            sleepTimezone = ZoneId.systemDefault().getId();
            sleepTimezoneText.setText("Часовой пояс: " + sleepTimezone);
            replyStatus.setText("Часовой пояс изменён · нажмите «Сохранить»");
        });
        timezoneRow.addView(deviceTimezone, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));

        sleepReplyInput = new EditText(this);
        sleepReplyInput.setText("");
        sleepReplyInput.setHint(AutoReplyConfig.DEFAULT_SLEEP_MESSAGE);
        sleepReplyInput.setTextColor(Ui.TEXT);
        sleepReplyInput.setHintTextColor(Ui.MUTED);
        sleepReplyInput.setTextSize(15);
        sleepReplyInput.setMinLines(3);
        sleepReplyInput.setMaxLines(6);
        sleepReplyInput.setGravity(Gravity.TOP | Gravity.START);
        sleepReplyInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT |
                android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES |
                android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        Ui.styleInput(this, sleepReplyInput);
        card.addView(sleepReplyInput, marginTop(8));

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.VERTICAL);
        card.addView(actions, marginTop(12));

        addReplyButton = Ui.button(this, "+ Сообщение после оплаты", false);
        addReplyButton.setOnClickListener(v -> {
            Ui.haptic(v);
            if (replyInputs.size() >= maxReplyMessages) {
                toast("Можно добавить не больше " + maxReplyMessages + " сообщений");
                return;
            }
            addReplyInput("");
            replyInputs.get(replyInputs.size() - 1).requestFocus();
        });
        actions.addView(addReplyButton, matchWrap());

        Button save = Ui.button(this, "Сохранить", true);
        save.setOnClickListener(v -> { Ui.haptic(v); saveAutoReplySettings(); });
        LinearLayout.LayoutParams saveParams = matchWrap();
        saveParams.topMargin = Ui.dp(this, 4);
        actions.addView(save, saveParams);

        replyStatus = Ui.text(this, "Загружаю настройки с VPS…", 13, Ui.MUTED, false);
        card.addView(replyStatus, marginTop(12));

        replyDisabledToggle.setOnCheckedChangeListener((button, disabled) -> {
            if (loadingReplySettings) return;
            replyStatus.setText(disabled
                    ? "Отключаю отправку. Тексты останутся сохранены…"
                    : "Включаю отправку для новых заказов…");
            saveAutoReplySettings();
        });
        sleepReplyToggle.setOnCheckedChangeListener((button, enabled) -> {
            updateSleepControls();
            if (!loadingReplySettings) {
                replyStatus.setText("Режим сна изменён · нажмите «Сохранить»");
            }
        });
        updateSleepControls();
    }

    private void showSleepTimePicker(boolean start) {
        String value = start ? sleepStart : sleepEnd;
        String[] parts = value.split(":", 2);
        int hour = 0;
        int minute = 0;
        try {
            hour = Integer.parseInt(parts[0]);
            minute = Integer.parseInt(parts[1]);
        } catch (Exception ignored) {
            // The server already validates values; this is only a safe UI fallback.
        }
        new TimePickerDialog(
                this,
                (picker, selectedHour, selectedMinute) -> {
                    String formatted = String.format(
                            Locale.ROOT, "%02d:%02d", selectedHour, selectedMinute);
                    if (start) sleepStart = formatted; else sleepEnd = formatted;
                    refreshSleepTimeButtons();
                    replyStatus.setText("Время сна изменено · нажмите «Сохранить»");
                },
                hour,
                minute,
                DateFormat.is24HourFormat(this)
        ).show();
    }

    private void refreshSleepTimeButtons() {
        if (sleepStartButton != null) sleepStartButton.setText("С " + sleepStart);
        if (sleepEndButton != null) sleepEndButton.setText("До " + sleepEnd);
    }

    private void updateSleepControls() {
        if (sleepReplyToggle == null) return;
        boolean enabled = sleepReplyToggle.isChecked();
        View[] controls = {sleepStartButton, sleepEndButton, sleepTimezoneText, sleepReplyInput};
        for (View control : controls) {
            if (control == null) continue;
            control.setEnabled(enabled);
            control.setAlpha(enabled ? 1f : 0.5f);
        }
    }

    private void addReplyInput(String value) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.VERTICAL);

        EditText input = new EditText(this);
        input.setText(value == null ? "" : value);
        input.setTextColor(Ui.TEXT);
        input.setHintTextColor(Ui.MUTED);
        input.setTextSize(15);
        input.setMinLines(2);
        input.setMaxLines(5);
        input.setGravity(Gravity.TOP | Gravity.START);
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT |
                android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES |
                android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        Ui.styleInput(this, input);
        LinearLayout.LayoutParams inputParams = matchWrap();
        row.addView(input, inputParams);

        Button remove = Ui.button(this, "Удалить", false);
        LinearLayout.LayoutParams removeParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        removeParams.gravity = Gravity.END;
        removeParams.topMargin = Ui.dp(this, 2);
        row.addView(remove, removeParams);
        remove.setOnClickListener(v -> {
            Ui.haptic(v);
            replyInputs.remove(input);
            replyList.removeView(row);
            if (replyInputs.isEmpty()) addReplyInput("");
            refreshReplyHints();
            updateAddReplyButton();
        });

        replyInputs.add(input);
        LinearLayout.LayoutParams rowParams = matchWrap();
        if (replyList.getChildCount() > 0) rowParams.topMargin = Ui.dp(this, 8);
        replyList.addView(row, rowParams);
        refreshReplyHints();
        updateAddReplyButton();
    }

    private void refreshReplyHints() {
        for (int index = 0; index < replyInputs.size(); index++) {
            replyInputs.get(index).setHint(index == 0
                    ? replyDefaultMessage
                    : "Дополнительное сообщение после оплаты");
        }
    }

    private void showReplyMessages(List<String> messages) {
        replyList.removeAllViews();
        replyInputs.clear();
        if (messages == null || messages.isEmpty()) {
            addReplyInput("");
        } else {
            for (String message : messages) addReplyInput(message);
        }
        updateAddReplyButton();
    }

    private void updateAddReplyButton() {
        if (addReplyButton != null) addReplyButton.setEnabled(replyInputs.size() < maxReplyMessages);
    }

    private ArrayList<String> collectReplyMessages() {
        ArrayList<String> messages = new ArrayList<>();
        for (EditText input : replyInputs) messages.add(input.getText().toString());
        return messages;
    }

    private void loadAutoReplySettings() {
        String url = urlInput.getText().toString().trim();
        String validation = UrlTools.validatePairingUrl(url);
        if (validation != null) {
            replyStatus.setText("Сначала сохраните корректный Pairing URL");
            return;
        }
        final int generation = ++replyRequestGeneration;
        network.execute(() -> {
            try {
                AutoReplyConfig config = AutoReplyConfig.fromJson(
                        HttpTextClient.get(UrlTools.autoRepliesUrl(url), 15_000));
                runOnUiThread(() -> {
                    if (generation != replyRequestGeneration) return;
                    applyAutoReplyConfig(config, "Настройки загружены с VPS");
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    if (generation == replyRequestGeneration)
                        replyStatus.setText("Не удалось загрузить: " + e.getMessage());
                });
            }
        });
    }

    private void saveAutoReplySettings() {
        String url = urlInput.getText().toString().trim();
        String validation = UrlTools.validatePairingUrl(url);
        if (validation != null) {
            replyStatus.setText(validation);
            return;
        }
        final boolean enabled = !replyDisabledToggle.isChecked();
        final ArrayList<String> messages = collectReplyMessages();
        final String fulfillmentMessage = fulfillmentReplyInput.getText().toString();
        final boolean sleepEnabled = sleepReplyToggle.isChecked();
        if (sleepEnabled && sleepStart.equals(sleepEnd)) {
            replyStatus.setText("Начало и конец периода сна должны отличаться");
            toast("Укажите промежуток сна, а не одну точку");
            return;
        }
        final String sleepMessage = sleepReplyInput.getText().toString();
        final int generation = ++replyRequestGeneration;
        replyStatus.setText(enabled ? "Сохраняю сообщения…" : "Отключаю сообщения…");
        network.execute(() -> {
            try {
                String request = AutoReplyConfig.requestJson(
                        enabled,
                        messages,
                        fulfillmentMessage,
                        sleepEnabled,
                        sleepStart,
                        sleepEnd,
                        sleepTimezone,
                        sleepMessage);
                AutoReplyConfig config = AutoReplyConfig.fromJson(HttpTextClient.postJson(
                        UrlTools.autoRepliesUrl(url), request, 15_000));
                runOnUiThread(() -> {
                    if (generation != replyRequestGeneration) return;
                    applyAutoReplyConfig(config, config.enabled
                            ? "Сообщения включены · настройки сохранены"
                            : "Сообщения отключены · тексты сохранены");
                    toast(config.enabled ? "Сообщения сохранены" : "Отправка сообщений отключена");
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    if (generation == replyRequestGeneration)
                        replyStatus.setText("Не удалось сохранить: " + e.getMessage());
                });
            }
        });
    }

    private void applyAutoReplyConfig(AutoReplyConfig config, String status) {
        loadingReplySettings = true;
        maxReplyMessages = config.maxMessages;
        replyDefaultMessage = config.defaultMessage;
        replyDisabledToggle.setChecked(!config.enabled);
        showReplyMessages(config.messages);
        fulfillmentReplyInput.setText(config.fulfillmentMessage);
        fulfillmentReplyInput.setHint(config.defaultFulfillmentMessage);
        sleepStart = config.sleepStart;
        sleepEnd = config.sleepEnd;
        sleepTimezone = config.sleepTimezone;
        sleepReplyToggle.setChecked(config.sleepEnabled);
        sleepReplyInput.setText(config.sleepMessage);
        sleepReplyInput.setHint(config.defaultSleepMessage);
        sleepTimezoneText.setText("Часовой пояс: " + sleepTimezone);
        refreshSleepTimeButtons();
        updateSleepControls();
        replyStatus.setText(status);
        loadingReplySettings = false;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams marginTop(int dp) {
        LinearLayout.LayoutParams params = matchWrap();
        params.topMargin = Ui.dp(this, dp);
        return params;
    }

    private Button button(String text) {
        return Ui.button(this, text, false);
    }

    private void saveAndStart() {
        String url = urlInput.getText().toString().trim();
        String validation = UrlTools.validatePairingUrl(url);
        if (validation != null) { toast(validation); return; }
        if (!notificationsAllowed()) {
            requestNotificationPermissionIfNeeded();
            toast("Разрешите уведомления и нажмите запуск ещё раз");
            return;
        }
        Prefs.setUrl(this, url);
        Prefs.setEnabled(this, true);
        GalaxyIntegration.refreshSurfaces(this);
        Intent service = new Intent(this, MonitorService.class).setAction(MonitorService.ACTION_START);
        startForegroundService(service);
        refreshStatus();
        loadAutoReplySettings();
        toast("Мониторинг запущен");
    }

    private void stopMonitoring() {
        Prefs.setEnabled(this, false);
        GalaxyIntegration.refreshSurfaces(this);
        Intent service = new Intent(this, MonitorService.class).setAction(MonitorService.ACTION_STOP);
        startService(service);
        refreshStatus();
        toast("Мониторинг остановлен");
    }

    private void checkServer(boolean createTest) {
        String url = urlInput.getText().toString().trim();
        String validation = UrlTools.validatePairingUrl(url);
        if (validation != null) { toast(validation); return; }
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
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return false;
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
        statusText.setText(Prefs.isEnabled(this)
                ? "Статус: мониторинг включён"
                : "Статус: мониторинг выключен");
    }

    @Override protected void onResume() { super.onResume(); refreshStatus(); }
    @Override protected void onDestroy() { network.shutdownNow(); super.onDestroy(); }
    private void toast(String text) { Toast.makeText(this, text, Toast.LENGTH_SHORT).show(); }
}
