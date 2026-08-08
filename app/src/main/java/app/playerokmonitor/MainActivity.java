package app.playerokmonitor;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Insets;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int REQ_NOTIFICATIONS = 5001;
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private OrderListAdapter adapter;
    private TextView statusChip;
    private TextView emptyText;
    private Button refreshButton;
    private long lastSyncStartedMs = 0L;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        NotificationHelper.ensureChannels(this);
        setContentView(buildUi());
        requestNotificationPermissionIfNeeded();
        showOrders(OrdersRepository.loadCached(this));
        refreshMonitorStatus();
        syncOrders(false);
    }

    private View buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Ui.BG);
        int side = Ui.dp(this, 16);
        root.setPadding(side, Ui.dp(this, 10), side, Ui.dp(this, 10));
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int left = side, top = Ui.dp(this, 10), right = side, bottom = Ui.dp(this, 10);
            if (Build.VERSION.SDK_INT >= 30) {
                Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
                left += bars.left; top += bars.top; right += bars.right; bottom += bars.bottom;
            } else {
                left += insets.getSystemWindowInsetLeft(); top += insets.getSystemWindowInsetTop();
                right += insets.getSystemWindowInsetRight(); bottom += insets.getSystemWindowInsetBottom();
            }
            v.setPadding(left, top, right, bottom);
            return insets;
        });

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(0, Ui.dp(this, 6), 0, Ui.dp(this, 10));
        root.addView(header, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT));

        LinearLayout titleBlock = new LinearLayout(this);
        titleBlock.setOrientation(LinearLayout.VERTICAL);
        header.addView(titleBlock, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        titleBlock.addView(Ui.text(this, "Playerok Monitor", 27, Ui.TEXT, true));
        TextView subtitle = Ui.text(this, "Оплаченные заказы и проблемы", 14, Ui.MUTED, false);
        LinearLayout.LayoutParams subParams = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        subParams.topMargin = Ui.dp(this, 2);
        titleBlock.addView(subtitle, subParams);

        Button settings = new Button(this);
        settings.setText("Настройки"); settings.setAllCaps(false);
        settings.setOnClickListener(v -> startActivity(new Intent(this, SettingsActivity.class)));
        header.addView(settings, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, Ui.dp(this, 48)));

        LinearLayout tools = new LinearLayout(this);
        tools.setOrientation(LinearLayout.HORIZONTAL);
        tools.setGravity(Gravity.CENTER_VERTICAL);
        tools.setPadding(Ui.dp(this, 14), Ui.dp(this, 11), Ui.dp(this, 10), Ui.dp(this, 11));
        tools.setBackground(Ui.roundedStroke(this, Ui.CARD, Ui.BORDER, 14));
        root.addView(tools, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT));

        statusChip = Ui.text(this, "", 13, Ui.GREEN, true);
        statusChip.setGravity(Gravity.CENTER);
        statusChip.setPadding(Ui.dp(this, 10), Ui.dp(this, 6), Ui.dp(this, 10), Ui.dp(this, 6));
        tools.addView(statusChip);
        TextView hint = Ui.text(this, "Данные берутся из SQLite на VPS", 13, Ui.MUTED, false);
        LinearLayout.LayoutParams hintParams = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        hintParams.leftMargin = Ui.dp(this, 10);
        tools.addView(hint, hintParams);
        refreshButton = new Button(this);
        refreshButton.setText("↻"); refreshButton.setTextSize(20);
        refreshButton.setOnClickListener(v -> syncOrders(true));
        tools.addView(refreshButton, new LinearLayout.LayoutParams(Ui.dp(this, 48), Ui.dp(this, 44)));

        TextView section = Ui.text(this, "Заказы", 20, Ui.TEXT, true);
        LinearLayout.LayoutParams sec = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        sec.topMargin = Ui.dp(this, 18); sec.bottomMargin = Ui.dp(this, 4);
        root.addView(section, sec);

        emptyText = Ui.text(this, "Пока нет сохранённых заказов", 15, Ui.MUTED, false);
        emptyText.setGravity(Gravity.CENTER);
        emptyText.setPadding(Ui.dp(this, 20), Ui.dp(this, 50), Ui.dp(this, 20), Ui.dp(this, 20));
        root.addView(emptyText, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT));

        ListView list = new ListView(this);
        list.setDivider(null); list.setDividerHeight(0); list.setCacheColorHint(android.graphics.Color.TRANSPARENT); list.setBackgroundColor(Ui.BG);
        adapter = new OrderListAdapter(this); list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> {
            OrderData order = adapter.getOrder(position);
            startActivity(new Intent(this, OrderDetailActivity.class).putExtra(OrderDetailActivity.EXTRA_DEAL_ID, order.dealId));
        });
        root.addView(list, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));
        return root;
    }

    private void showOrders(List<OrderData> orders) {
        if (adapter == null) return;
        adapter.setOrders(orders);
        emptyText.setVisibility(orders == null || orders.isEmpty() ? View.VISIBLE : View.GONE);
    }

    private void syncOrders(boolean manual) {
        String url = Prefs.getUrl(this);
        if (UrlTools.validatePairingUrl(url) != null) {
            if (manual) toast("Сначала укажите Pairing URL в настройках");
            if (OrdersRepository.loadCached(this).isEmpty()) emptyText.setText("Подключите VPS в настройках — здесь появятся оплаченные заказы");
            return;
        }
        long now = android.os.SystemClock.elapsedRealtime();
        if (!manual && now - lastSyncStartedMs < 2500L) return;
        lastSyncStartedMs = now;
        refreshButton.setEnabled(false);
        network.execute(() -> {
            try {
                OrdersRepository.SyncResult result = OrdersRepository.sync(this, url);
                runOnUiThread(() -> {
                    refreshButton.setEnabled(true); emptyText.setText("Пока нет сохранённых заказов");
                    showOrders(result.orders); refreshMonitorStatus();
                    if (manual) toast(result.unchanged ? "Уже актуально" : "Заказы обновлены");
                });
            } catch (Exception e) {
                runOnUiThread(() -> { refreshButton.setEnabled(true); refreshMonitorStatus(); if (manual) toast("Не удалось обновить: " + e.getMessage()); });
            }
        });
    }

    private void refreshMonitorStatus() {
        if (statusChip == null) return;
        if (Prefs.isEnabled(this)) {
            statusChip.setText("● МОНИТОРИНГ"); statusChip.setTextColor(Ui.GREEN); statusChip.setBackground(Ui.rounded(this, Ui.GREEN_BG, 10));
        } else {
            statusChip.setText("○ ВЫКЛЮЧЕН"); statusChip.setTextColor(Ui.AMBER); statusChip.setBackground(Ui.rounded(this, Ui.AMBER_BG, 10));
        }
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIFICATIONS);
        }
    }

    @Override protected void onResume() { super.onResume(); refreshMonitorStatus(); showOrders(OrdersRepository.loadCached(this)); syncOrders(false); }
    @Override protected void onDestroy() { network.shutdownNow(); super.onDestroy(); }
    private void toast(String text) { Toast.makeText(this, text, Toast.LENGTH_SHORT).show(); }
}
