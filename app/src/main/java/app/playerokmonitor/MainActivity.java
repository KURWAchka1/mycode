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
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int REQ_NOTIFICATIONS = 5001;

    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private OrderListAdapter adapter;
    private TextView statusChip;
    private TextView emptyText;
    private TextView salesTab;
    private TextView purchasesTab;
    private TextView classificationHint;
    private ImageButton refreshButton;
    private long lastSyncStartedMs = 0L;
    private String selectedDirection = OrderData.DIRECTION_SALE;
    private List<OrderData> allOrders = Collections.emptyList();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        NotificationHelper.ensureChannels(this);
        setContentView(buildUi());
        requestNotificationPermissionIfNeeded();
        allOrders = OrdersRepository.loadCached(this);
        renderSelectedTab();
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

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(0, Ui.dp(this, 6), 0, Ui.dp(this, 10));
        root.addView(header, matchWrap());

        LinearLayout titleBlock = new LinearLayout(this);
        titleBlock.setOrientation(LinearLayout.VERTICAL);
        header.addView(titleBlock, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        titleBlock.addView(Ui.text(this, "Playerok Monitor", 27, Ui.TEXT, true));
        TextView subtitle = Ui.text(this, "Продажи, покупки и проблемы", 14, Ui.MUTED, false);
        LinearLayout.LayoutParams subParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        subParams.topMargin = Ui.dp(this, 2);
        titleBlock.addView(subtitle, subParams);

        ImageButton settings = Ui.iconButton(this, R.drawable.ic_nav_settings, "Настройки");
        settings.setOnClickListener(v -> startActivity(new Intent(this, SettingsActivity.class)));
        header.addView(settings, new LinearLayout.LayoutParams(Ui.dp(this, 48), Ui.dp(this, 48)));

        LinearLayout tools = new LinearLayout(this);
        tools.setOrientation(LinearLayout.HORIZONTAL);
        tools.setGravity(Gravity.CENTER_VERTICAL);
        tools.setPadding(Ui.dp(this, 14), Ui.dp(this, 11), Ui.dp(this, 10), Ui.dp(this, 11));
        tools.setBackground(Ui.roundedStroke(this, Ui.CARD, Ui.BORDER, 14));
        root.addView(tools, matchWrap());

        statusChip = Ui.text(this, "", 13, Ui.GREEN, true);
        statusChip.setGravity(Gravity.CENTER);
        statusChip.setPadding(Ui.dp(this, 10), Ui.dp(this, 6), Ui.dp(this, 10), Ui.dp(this, 6));
        tools.addView(statusChip);

        TextView hint = Ui.text(this, "SQLite на VPS", 13, Ui.MUTED, false);
        LinearLayout.LayoutParams hintParams = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        hintParams.leftMargin = Ui.dp(this, 10);
        tools.addView(hint, hintParams);

        refreshButton = Ui.iconButton(this, R.drawable.ic_nav_refresh, "Обновить список");
        refreshButton.setOnClickListener(v -> syncOrders(true));
        tools.addView(refreshButton, new LinearLayout.LayoutParams(Ui.dp(this, 48), Ui.dp(this, 44)));

        LinearLayout tabs = new LinearLayout(this);
        tabs.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams tabsParams = matchWrap();
        tabsParams.topMargin = Ui.dp(this, 18);
        root.addView(tabs, tabsParams);

        salesTab = makeTab("Мои продажи");
        salesTab.setOnClickListener(v -> selectDirection(OrderData.DIRECTION_SALE));
        tabs.addView(salesTab, new LinearLayout.LayoutParams(0, Ui.dp(this, 46), 1f));

        purchasesTab = makeTab("Мои покупки");
        purchasesTab.setOnClickListener(v -> selectDirection(OrderData.DIRECTION_PURCHASE));
        LinearLayout.LayoutParams purchaseParams = new LinearLayout.LayoutParams(0, Ui.dp(this, 46), 1f);
        purchaseParams.leftMargin = Ui.dp(this, 8);
        tabs.addView(purchasesTab, purchaseParams);

        classificationHint = Ui.text(this, "", 12, Ui.AMBER, false);
        classificationHint.setPadding(Ui.dp(this, 2), Ui.dp(this, 8), Ui.dp(this, 2), 0);
        classificationHint.setVisibility(View.GONE);
        root.addView(classificationHint, matchWrap());

        emptyText = Ui.text(this, "", 15, Ui.MUTED, false);
        emptyText.setGravity(Gravity.CENTER);
        emptyText.setPadding(Ui.dp(this, 20), Ui.dp(this, 50), Ui.dp(this, 20), Ui.dp(this, 20));
        root.addView(emptyText, matchWrap());

        ListView list = new ListView(this);
        list.setDivider(null);
        list.setDividerHeight(0);
        list.setCacheColorHint(android.graphics.Color.TRANSPARENT);
        list.setBackgroundColor(Ui.BG);
        adapter = new OrderListAdapter(this);
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> {
            OrderData order = adapter.getOrder(position);
            Intent detail = new Intent(this, OrderDetailActivity.class)
                    .putExtra(OrderDetailActivity.EXTRA_DEAL_ID, order.dealId);
            startActivity(detail);
        });
        root.addView(list, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f));

        updateTabStyles();
        return root;
    }

    private TextView makeTab(String text) {
        TextView tab = Ui.text(this, text, 14, Ui.MUTED, true);
        tab.setGravity(Gravity.CENTER);
        tab.setPadding(Ui.dp(this, 8), 0, Ui.dp(this, 8), 0);
        return tab;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private void selectDirection(String direction) {
        if (direction.equals(selectedDirection)) return;
        selectedDirection = direction;
        updateTabStyles();
        renderSelectedTab();
    }

    private void updateTabStyles() {
        if (salesTab == null || purchasesTab == null) return;
        Ui.styleTab(this, salesTab, OrderData.DIRECTION_SALE.equals(selectedDirection));
        Ui.styleTab(this, purchasesTab, OrderData.DIRECTION_PURCHASE.equals(selectedDirection));
    }

    private void renderSelectedTab() {
        if (adapter == null) return;
        List<OrderData> visible = OrdersRepository.filterByDirection(allOrders, selectedDirection);
        adapter.setOrders(visible);
        boolean empty = visible.isEmpty();
        emptyText.setText(OrderData.DIRECTION_SALE.equals(selectedDirection)
                ? "Оплаченных продаж пока нет"
                : "Покупок пока нет");
        emptyText.setVisibility(empty ? View.VISIBLE : View.GONE);

        int unclassified = OrdersRepository.countUnclassified(allOrders);
        if (unclassified > 0) {
            classificationHint.setText("Старые сделки ещё классифицируются на VPS: " + unclassified);
            classificationHint.setVisibility(View.VISIBLE);
        } else {
            classificationHint.setVisibility(View.GONE);
        }
    }

    private void syncOrders(boolean manual) {
        String url = Prefs.getUrl(this);
        String validation = UrlTools.validatePairingUrl(url);
        if (validation != null) {
            if (manual) toast("Сначала укажите Pairing URL в настройках");
            if (allOrders.isEmpty()) {
                emptyText.setText("Подключите VPS в настройках");
                emptyText.setVisibility(View.VISIBLE);
            }
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
                    refreshButton.setEnabled(true);
                    allOrders = result.orders;
                    renderSelectedTab();
                    refreshMonitorStatus();
                    if (manual) toast(result.unchanged ? "Уже актуально" : "Список обновлён");
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    refreshButton.setEnabled(true);
                    refreshMonitorStatus();
                    if (manual) toast("Не удалось обновить: " + e.getMessage());
                });
            }
        });
    }

    private void refreshMonitorStatus() {
        if (statusChip == null) return;
        if (Prefs.isEnabled(this)) {
            statusChip.setText("МОНИТОРИНГ");
            statusChip.setTextColor(Ui.GREEN);
            statusChip.setBackground(Ui.rounded(this, Ui.GREEN_BG, 10));
        } else {
            statusChip.setText("ВЫКЛЮЧЕН");
            statusChip.setTextColor(Ui.AMBER);
            statusChip.setBackground(Ui.rounded(this, Ui.AMBER_BG, 10));
        }
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 &&
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIFICATIONS);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshMonitorStatus();
        allOrders = OrdersRepository.loadCached(this);
        renderSelectedTab();
        syncOrders(false);
    }

    @Override
    protected void onDestroy() {
        network.shutdownNow();
        super.onDestroy();
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show();
    }
}
