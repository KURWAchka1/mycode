package app.playerokmonitor;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

import java.util.List;

/** Compact order dashboard for One UI Home and Good Lock/Flex Window. */
public final class OrderWidgetProvider extends AppWidgetProvider {
    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        for (int id : ids) manager.updateAppWidget(id, build(context));
    }

    static void updateAll(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        ComponentName provider = new ComponentName(context, OrderWidgetProvider.class);
        int[] ids = manager.getAppWidgetIds(provider);
        for (int id : ids) manager.updateAppWidget(id, build(context));
    }

    private static RemoteViews build(Context context) {
        List<OrderData> orders = OrdersRepository.loadCached(context);
        int sales = 0, purchases = 0, problems = 0, refunds = 0;
        for (OrderData order : orders) {
            if (order.isSale()) sales++;
            if (order.isPurchase()) purchases++;
            if (order.problemActive) problems++;
            if (order.rolledBack) refunds++;
        }

        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.order_widget);
        views.setTextViewText(R.id.widget_status,
                Prefs.isEnabled(context) ? "Мониторинг включён" : "Мониторинг выключен");
        views.setTextViewText(R.id.widget_sales, Integer.toString(sales));
        views.setTextViewText(R.id.widget_purchases, Integer.toString(purchases));
        views.setTextViewText(R.id.widget_problems, Integer.toString(problems));
        views.setTextViewText(R.id.widget_refunds, Integer.toString(refunds));

        Intent open = new Intent(context, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(context, 81, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        views.setOnClickPendingIntent(R.id.widget_root, pi);
        return views;
    }
}
