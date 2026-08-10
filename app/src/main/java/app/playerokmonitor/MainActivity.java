package app.playerokmonitor;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Insets;
import android.os.Build;
import android.os.Bundle;
import android.text.Spannable;
import android.text.SpannableString;
import android.text.style.ForegroundColorSpan;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int REQ_NOTIFICATIONS = 5001;
    private static final String FILTER_NEW_ORDERS = "NEW_ORDERS";
    static final String EXTRA_DIRECTION = "direction";

    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private OrderListAdapter adapter;
    private ScrollView emptyScroll;
    private LinearLayout emptyState;
    private TextView emptyTitle;
    private TextView emptyText;
    private TextView newOrdersTab;
    private TextView salesTab;
    private TextView purchasesTab;
    private TextView classificationHint;
    private ImageButton refreshButton;
    private long lastSyncStartedMs = 0L;
    private String selectedDirection = FILTER_NEW_ORDERS;
    private List<OrderData> allOrders = Collections.emptyList();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Ui.prepareWindow(this);
        NotificationHelper.ensureChannels(this);
        GalaxyIntegration.publishShortcuts(this);
        applyIntent(getIntent());
        setContentView(buildUi());
        requestNotificationPermissionIfNeeded();
        allOrders = OrdersRepository.loadCached(this);
        renderSelectedTab();
        syncOrders(false);
    }

    private View buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Ui.BG);
        boolean largeText = getResources().getConfiguration().fontScale >= 1.35f;
        int side = Ui.dp(this, Ui.isWide(this) ? 48 : 24);
        root.setPadding(side, Ui.dp(this, 4), side, Ui.dp(this, 8));
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int left = side, top = Ui.dp(this, 4), right = side, bottom = Ui.dp(this, 12);
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
        header.setMinimumHeight(Ui.dp(this, 56));
        header.setPadding(0, Ui.dp(this, 2), 0, 0);
        root.addView(header, matchWrap());

        SpannableString compactTitle = new SpannableString("Playerok Заказы");
        compactTitle.setSpan(new ForegroundColorSpan(Ui.ACCENT), 0, 8,
                Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
        TextView screenTitle = Ui.text(this, "", 22, Ui.TEXT, true);
        screenTitle.setText(compactTitle);
        screenTitle.setSingleLine(true);
        screenTitle.setAutoSizeTextTypeUniformWithConfiguration(
                13, 22, 1, TypedValue.COMPLEX_UNIT_SP);
        header.addView(screenTitle, new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        refreshButton = Ui.iconButton(this, R.drawable.ic_nav_refresh, "Обновить список");
        refreshButton.setOnClickListener(v -> {
            Ui.haptic(v);
            syncOrders(true);
        });
        header.addView(refreshButton, new LinearLayout.LayoutParams(Ui.dp(this, 48), Ui.dp(this, 48)));

        ImageButton settings = Ui.iconButton(this, R.drawable.ic_nav_settings, "Настройки");
        settings.setOnClickListener(v -> {
            Ui.haptic(v);
            startActivity(new Intent(this, SettingsActivity.class));
        });
        header.addView(settings, new LinearLayout.LayoutParams(Ui.dp(this, 48), Ui.dp(this, 48)));

        HorizontalScrollView tabScroll = new HorizontalScrollView(this);
        tabScroll.setFillViewport(!largeText);
        tabScroll.setHorizontalScrollBarEnabled(false);
        tabScroll.setOverScrollMode(View.OVER_SCROLL_NEVER);
        LinearLayout.LayoutParams tabsParams = matchWrap();
        root.addView(tabScroll, tabsParams);

        LinearLayout tabs = new LinearLayout(this);
        tabs.setOrientation(LinearLayout.HORIZONTAL);
        tabs.setBaselineAligned(false);
        tabs.setGravity(Gravity.BOTTOM);
        tabScroll.addView(tabs, new HorizontalScrollView.LayoutParams(
                largeText
                        ? HorizontalScrollView.LayoutParams.WRAP_CONTENT
                        : HorizontalScrollView.LayoutParams.MATCH_PARENT,
                HorizontalScrollView.LayoutParams.WRAP_CONTENT));

        newOrdersTab = makeTab("Новые заказы", largeText);
        newOrdersTab.setOnClickListener(v -> selectDirection(FILTER_NEW_ORDERS));
        tabs.addView(newOrdersTab, tabParams(largeText));

        salesTab = makeTab("Продажи", largeText);
        salesTab.setOnClickListener(v -> selectDirection(OrderData.DIRECTION_SALE));
        tabs.addView(salesTab, tabParams(largeText));

        purchasesTab = makeTab("Покупки", largeText);
        purchasesTab.setOnClickListener(v -> selectDirection(OrderData.DIRECTION_PURCHASE));
        tabs.addView(purchasesTab, tabParams(largeText));

        View pinnedDivider = new View(this);
        pinnedDivider.setBackgroundColor(Ui.BORDER);
        root.addView(pinnedDivider, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, Ui.dp(this, 1)));

        classificationHint = Ui.text(this, "", 12, Ui.AMBER, false);
        classificationHint.setPadding(Ui.dp(this, 2), Ui.dp(this, 8), Ui.dp(this, 2), 0);
        classificationHint.setVisibility(View.GONE);
        root.addView(classificationHint, matchWrap());

        FrameLayout contentArea = new FrameLayout(this);
        LinearLayout.LayoutParams contentParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f);
        root.addView(contentArea, contentParams);

        ListView list = new ListView(this);
        list.setDivider(null);
        list.setDividerHeight(0);
        list.setCacheColorHint(android.graphics.Color.TRANSPARENT);
        list.setBackgroundColor(Ui.BG);
        list.setOverScrollMode(View.OVER_SCROLL_NEVER);
        list.setVerticalScrollBarEnabled(false);
        list.setClipToPadding(false);
        list.setPadding(0, Ui.dp(this, 4), 0, Ui.dp(this, 20));
        adapter = new OrderListAdapter(this);
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> {
            OrderData order = adapter.getOrder(position);
            Intent detail = new Intent(this, OrderDetailActivity.class)
                    .putExtra(OrderDetailActivity.EXTRA_DEAL_ID, order.dealId);
            startActivity(detail);
        });
        contentArea.addView(list, new FrameLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.MATCH_PARENT));

        emptyScroll = new ScrollView(this);
        emptyScroll.setFillViewport(true);
        emptyScroll.setVerticalScrollBarEnabled(false);
        emptyScroll.setOverScrollMode(View.OVER_SCROLL_NEVER);

        emptyState = new LinearLayout(this);
        emptyState.setOrientation(LinearLayout.VERTICAL);
        emptyState.setGravity(Gravity.CENTER);
        emptyState.setPadding(Ui.dp(this, 20), Ui.dp(this, 36), Ui.dp(this, 20), Ui.dp(this, 24));
        emptyScroll.addView(emptyState, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT));

        ImageView emptyIcon = new ImageView(this);
        emptyIcon.setImageResource(R.drawable.ic_empty_check);
        emptyIcon.setImageTintList(android.content.res.ColorStateList.valueOf(Ui.ACCENT));
        emptyIcon.setPadding(Ui.dp(this, 18), Ui.dp(this, 18), Ui.dp(this, 18), Ui.dp(this, 18));
        emptyIcon.setBackground(Ui.rounded(this, Ui.ACCENT_BG, 32));
        emptyState.addView(emptyIcon, new LinearLayout.LayoutParams(Ui.dp(this, 64), Ui.dp(this, 64)));

        emptyTitle = Ui.text(this, "Пока всё спокойно", 20, Ui.TEXT, true);
        emptyTitle.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams emptyTitleParams = matchWrap();
        emptyTitleParams.topMargin = Ui.dp(this, 16);
        emptyState.addView(emptyTitle, emptyTitleParams);

        emptyText = Ui.text(this, "", 14, Ui.MUTED, false);
        emptyText.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams emptyBodyParams = matchWrap();
        emptyBodyParams.topMargin = Ui.dp(this, 5);
        emptyState.addView(emptyText, emptyBodyParams);

        Button emptyRefresh = Ui.button(this, "Обновить", false);
        emptyRefresh.setCompoundDrawablesWithIntrinsicBounds(R.drawable.ic_nav_refresh, 0, 0, 0);
        emptyRefresh.setCompoundDrawablePadding(Ui.dp(this, 8));
        emptyRefresh.setOnClickListener(v -> { Ui.haptic(v); syncOrders(true); });
        LinearLayout.LayoutParams emptyRefreshParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        emptyRefreshParams.topMargin = Ui.dp(this, 12);
        emptyState.addView(emptyRefresh, emptyRefreshParams);

        FrameLayout.LayoutParams emptyParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT);
        contentArea.addView(emptyScroll, emptyParams);

        updateTabStyles();
        Ui.reveal(root);
        return root;
    }

    private TextView makeTab(String text, boolean largeText) {
        TextView tab = Ui.text(this, text, 14, Ui.MUTED, true);
        tab.setGravity(Gravity.CENTER);
        tab.setMinHeight(Ui.dp(this, 50));
        if (largeText) {
            tab.setSingleLine(true);
            tab.setPadding(Ui.dp(this, 18), Ui.dp(this, 7), Ui.dp(this, 18), Ui.dp(this, 5));
        } else {
            tab.setMaxLines(2);
            tab.setHorizontallyScrolling(false);
            tab.setPadding(Ui.dp(this, 5), Ui.dp(this, 7), Ui.dp(this, 5), Ui.dp(this, 5));
        }
        return tab;
    }

    private LinearLayout.LayoutParams tabParams(boolean largeText) {
        return largeText
                ? new LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.WRAP_CONTENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT)
                : new LinearLayout.LayoutParams(
                        0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private void selectDirection(String direction) {
        if (direction.equals(selectedDirection)) return;
        View target = FILTER_NEW_ORDERS.equals(direction)
                ? newOrdersTab
                : (OrderData.DIRECTION_SALE.equals(direction) ? salesTab : purchasesTab);
        Ui.haptic(target);
        selectedDirection = direction;
        updateTabStyles();
        renderSelectedTab();
    }

    private void updateTabStyles() {
        if (newOrdersTab == null || salesTab == null || purchasesTab == null) return;
        Ui.styleTab(this, newOrdersTab, FILTER_NEW_ORDERS.equals(selectedDirection));
        Ui.styleTab(this, salesTab, OrderData.DIRECTION_SALE.equals(selectedDirection));
        Ui.styleTab(this, purchasesTab, OrderData.DIRECTION_PURCHASE.equals(selectedDirection));
    }

    private void renderSelectedTab() {
        if (adapter == null) return;
        List<OrderData> visible = FILTER_NEW_ORDERS.equals(selectedDirection)
                ? OrdersRepository.filterNewOrders(allOrders)
                : OrdersRepository.filterByDirection(allOrders, selectedDirection);
        adapter.setOrders(visible);
        boolean empty = visible.isEmpty();
        if (FILTER_NEW_ORDERS.equals(selectedDirection)) {
            emptyTitle.setText("Пока всё спокойно");
            emptyText.setText("Новых заказов нет — всё выполнено");
        } else if (OrderData.DIRECTION_SALE.equals(selectedDirection)) {
            emptyTitle.setText("Продаж пока нет");
            emptyText.setText("Новые оплаченные продажи появятся здесь");
        } else {
            emptyTitle.setText("Покупок пока нет");
            emptyText.setText("Ваши оплаченные покупки появятся здесь");
        }
        emptyScroll.setVisibility(empty ? View.VISIBLE : View.GONE);

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
                emptyTitle.setText("Нужно подключение");
                emptyText.setText("Добавьте Pairing URL в настройках");
                emptyScroll.setVisibility(View.VISIBLE);
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
                    if (manual) toast(result.unchanged ? "Уже актуально" : "Список обновлён");
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    refreshButton.setEnabled(true);
                    if (manual) toast("Не удалось обновить: " + e.getMessage());
                });
            }
        });
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
        allOrders = OrdersRepository.loadCached(this);
        renderSelectedTab();
        syncOrders(false);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        applyIntent(intent);
        updateTabStyles();
        renderSelectedTab();
    }

    private void applyIntent(Intent intent) {
        if (intent == null) return;
        String direction = intent.getStringExtra(EXTRA_DIRECTION);
        if ((direction == null || direction.isEmpty()) && intent.getData() != null) {
            direction = intent.getData().getQueryParameter(EXTRA_DIRECTION);
        }
        if (OrderData.DIRECTION_SALE.equals(direction) || OrderData.DIRECTION_PURCHASE.equals(direction)) {
            selectedDirection = direction;
        }
    }

    @Override
    public boolean onKeyShortcut(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_R) {
            syncOrders(true);
            return true;
        }
        if (keyCode == KeyEvent.KEYCODE_1) {
            selectDirection(FILTER_NEW_ORDERS);
            return true;
        }
        if (keyCode == KeyEvent.KEYCODE_2) {
            selectDirection(OrderData.DIRECTION_SALE);
            return true;
        }
        if (keyCode == KeyEvent.KEYCODE_3) {
            selectDirection(OrderData.DIRECTION_PURCHASE);
            return true;
        }
        if (keyCode == KeyEvent.KEYCODE_COMMA) {
            startActivity(new Intent(this, SettingsActivity.class));
            return true;
        }
        return super.onKeyShortcut(keyCode, event);
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
