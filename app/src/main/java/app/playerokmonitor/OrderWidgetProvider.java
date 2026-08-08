package app.playerokmonitor;

import android.annotation.SuppressLint;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.util.SizeF;
import android.view.View;
import android.widget.RemoteViews;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Responsive order dashboard for One UI Home, foldables, DeX and Flex Window. */
public final class OrderWidgetProvider extends AppWidgetProvider {
    private static final int WIDTH_COMPACT = 220;
    private static final int HEIGHT_STRIP = 80;
    private static final int HEIGHT_MEDIUM = 110;
    private static final int HEIGHT_LARGE = 170;

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        for (int id : ids) update(context, manager, id);
    }

    @Override
    public void onAppWidgetOptionsChanged(
            Context context,
            AppWidgetManager manager,
            int appWidgetId,
            Bundle newOptions
    ) {
        update(context, manager, appWidgetId);
    }

    static void updateAll(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        ComponentName provider = new ComponentName(context, OrderWidgetProvider.class);
        for (int id : manager.getAppWidgetIds(provider)) update(context, manager, id);
    }

    private static void update(Context context, AppWidgetManager manager, int id) {
        WidgetData data = WidgetData.load(context);
        RemoteViews views;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            views = buildResponsive(context, data);
        } else {
            views = buildForOptions(context, data, manager.getAppWidgetOptions(id));
        }
        manager.updateAppWidget(id, views);
    }

    @SuppressLint("NewApi")
    private static RemoteViews buildResponsive(Context context, WidgetData data) {
        Map<SizeF, RemoteViews> layouts = new LinkedHashMap<>();
        layouts.put(new SizeF(110f, 40f), buildStrip(context, data));
        layouts.put(new SizeF(180f, 72f), buildCompact(context, data));
        layouts.put(new SizeF(250f, 110f), buildMedium(context, data));
        layouts.put(new SizeF(280f, 170f), buildLarge(context, data));
        return new RemoteViews(layouts);
    }

    private static RemoteViews buildForOptions(Context context, WidgetData data, Bundle options) {
        int width = options == null
                ? 250
                : options.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH, 250);
        int height = options == null
                ? HEIGHT_MEDIUM
                : options.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT, HEIGHT_MEDIUM);
        if (height <= HEIGHT_STRIP) return buildStrip(context, data);
        if (width < WIDTH_COMPACT || height < HEIGHT_MEDIUM) return buildCompact(context, data);
        if (height >= HEIGHT_LARGE) return buildLarge(context, data);
        return buildMedium(context, data);
    }

    private static RemoteViews buildStrip(Context context, WidgetData data) {
        RemoteViews views = base(context, R.layout.order_widget_strip, data);
        views.setTextViewText(R.id.widget_strip_summary, "↑" + data.sales + "  ↓" + data.purchases);
        views.setContentDescription(
                R.id.widget_strip_summary,
                "Продаж: " + data.sales + ", покупок: " + data.purchases
        );
        int risks = data.problems + data.refunds;
        views.setViewVisibility(R.id.widget_alert_chip, risks > 0 ? View.VISIBLE : View.GONE);
        views.setTextViewText(R.id.widget_alert_summary, riskText(risks));
        return views;
    }

    private static RemoteViews buildCompact(Context context, WidgetData data) {
        RemoteViews views = base(context, R.layout.order_widget_compact, data);
        bindCounts(views, data);
        bindCountClicks(context, views);
        int risks = data.problems + data.refunds;
        views.setViewVisibility(R.id.widget_alert_chip, risks > 0 ? View.VISIBLE : View.GONE);
        views.setTextViewText(R.id.widget_alert_summary, eventText(risks));
        return views;
    }

    private static RemoteViews buildMedium(Context context, WidgetData data) {
        RemoteViews views = base(context, R.layout.order_widget, data);
        bindCounts(views, data);
        bindCountClicks(context, views);
        return views;
    }

    private static RemoteViews buildLarge(Context context, WidgetData data) {
        RemoteViews views = base(context, R.layout.order_widget_large, data);
        bindCounts(views, data);
        bindCountClicks(context, views);

        if (data.latest == null) {
            views.setTextViewText(R.id.widget_latest_name, "Ждём первую сделку");
            views.setTextViewText(R.id.widget_latest_meta, "Появится после синхронизации с VPS");
        } else {
            String name = clean(data.latest.itemName, "Сделка #" + data.latest.dealId);
            String direction = data.latest.isSale() ? "Продажа" : "Покупка";
            String price = clean(data.latest.price, "без цены");
            views.setTextViewText(R.id.widget_latest_name, name);
            views.setTextViewText(R.id.widget_latest_meta, direction + "  •  " + price);
            views.setOnClickPendingIntent(
                    R.id.widget_latest_card,
                    detailIntent(context, data.latest)
            );
        }
        return views;
    }

    private static RemoteViews base(Context context, int layout, WidgetData data) {
        RemoteViews views = new RemoteViews(context.getPackageName(), layout);
        boolean enabled = Prefs.isEnabled(context);
        views.setTextViewText(R.id.widget_status, enabled ? "Мониторинг активен" : "Мониторинг выключен");
        views.setImageViewResource(
                R.id.widget_status_dot,
                enabled ? R.drawable.widget_dot_active : R.drawable.widget_dot_inactive
        );
        views.setContentDescription(
                R.id.widget_root,
                "Playerok Monitor. Продаж: " + data.sales
                        + ", покупок: " + data.purchases
                        + ", проблем: " + data.problems
                        + ", возвратов: " + data.refunds
        );
        views.setOnClickPendingIntent(R.id.widget_root, mainIntent(context, null, 810));
        return views;
    }

    private static void bindCounts(RemoteViews views, WidgetData data) {
        views.setTextViewText(R.id.widget_sales, Integer.toString(data.sales));
        views.setTextViewText(R.id.widget_purchases, Integer.toString(data.purchases));
        views.setTextViewText(R.id.widget_problems, Integer.toString(data.problems));
        views.setTextViewText(R.id.widget_refunds, Integer.toString(data.refunds));
    }

    private static void bindCountClicks(Context context, RemoteViews views) {
        views.setOnClickPendingIntent(
                R.id.widget_sales_card,
                mainIntent(context, OrderData.DIRECTION_SALE, 811)
        );
        views.setOnClickPendingIntent(
                R.id.widget_purchases_card,
                mainIntent(context, OrderData.DIRECTION_PURCHASE, 812)
        );
    }

    private static PendingIntent mainIntent(Context context, String direction, int requestCode) {
        Intent open = new Intent(context, MainActivity.class)
                .setAction("app.playerokmonitor.WIDGET_OPEN_" + requestCode)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        if (direction != null) open.putExtra(MainActivity.EXTRA_DIRECTION, direction);
        return PendingIntent.getActivity(
                context,
                requestCode,
                open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
    }

    private static PendingIntent detailIntent(Context context, OrderData order) {
        Intent detail = new Intent(context, OrderDetailActivity.class)
                .setAction("app.playerokmonitor.WIDGET_DEAL_" + order.dealId)
                .putExtra(OrderDetailActivity.EXTRA_DEAL_ID, order.dealId);
        int requestCode = 900 + (order.dealId.hashCode() & 0x7fff);
        return PendingIntent.getActivity(
                context,
                requestCode,
                detail,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
    }

    private static String clean(String value, String fallback) {
        if (value == null || value.trim().isEmpty()) return fallback;
        return value.trim();
    }

    private static String riskText(int count) {
        return count + " " + plural(count, "риск", "риска", "рисков");
    }

    private static String eventText(int count) {
        return count + " " + plural(count, "событие", "события", "событий");
    }

    private static String plural(int count, String one, String few, String many) {
        int mod100 = Math.abs(count) % 100;
        int mod10 = mod100 % 10;
        if (mod100 >= 11 && mod100 <= 14) return many;
        if (mod10 == 1) return one;
        if (mod10 >= 2 && mod10 <= 4) return few;
        return many;
    }

    private static final class WidgetData {
        final int sales;
        final int purchases;
        final int problems;
        final int refunds;
        final OrderData latest;

        WidgetData(int sales, int purchases, int problems, int refunds, OrderData latest) {
            this.sales = sales;
            this.purchases = purchases;
            this.problems = problems;
            this.refunds = refunds;
            this.latest = latest;
        }

        static WidgetData load(Context context) {
            List<OrderData> orders = OrdersRepository.loadCached(context);
            int sales = 0;
            int purchases = 0;
            int problems = 0;
            int refunds = 0;
            for (OrderData order : orders) {
                if (order.isSale()) sales++;
                if (order.isPurchase()) purchases++;
                if (order.problemActive) problems++;
                if (order.rolledBack) refunds++;
            }
            return new WidgetData(
                    sales,
                    purchases,
                    problems,
                    refunds,
                    orders.isEmpty() ? null : orders.get(0)
            );
        }
    }
}
