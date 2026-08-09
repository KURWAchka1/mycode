package app.playerokmonitor;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.net.Uri;
import android.os.Build;

final class NotificationHelper {
    static final String SERVICE_CHANNEL = "monitor_service_v1";
    static final String ORDERS_CHANNEL = "playerok_orders_v3";
    static final String PROBLEMS_CHANNEL = "playerok_problems_v1";
    static final int SERVICE_NOTIFICATION_ID = 1001;

    private NotificationHelper() {}

    static void ensureChannels(Context context) {
        Ui.configure(context);
        NotificationManager manager = context.getSystemService(NotificationManager.class);

        NotificationChannel service = new NotificationChannel(
                SERVICE_CHANNEL,
                "Мониторинг Playerok",
                NotificationManager.IMPORTANCE_LOW
        );
        service.setDescription("Постоянное уведомление работающего мониторинга");
        service.setSound(null, null);
        service.enableVibration(false);
        manager.createNotificationChannel(service);

        Uri sound = Uri.parse("android.resource://" + context.getPackageName() + "/" + R.raw.order_alert);
        AudioAttributes attributes = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build();

        NotificationChannel orders = new NotificationChannel(
                ORDERS_CHANNEL,
                "Новые заказы Playerok",
                NotificationManager.IMPORTANCE_HIGH
        );
        orders.setDescription("Заметный короткий мягкий сигнал новых оплаченных заказов");
        orders.setSound(sound, attributes);
        orders.enableVibration(true);
        orders.setVibrationPattern(new long[]{0, 55, 70, 65});
        manager.createNotificationChannel(orders);

        NotificationChannel problems = new NotificationChannel(
                PROBLEMS_CHANNEL,
                "Проблемы и возвраты Playerok",
                NotificationManager.IMPORTANCE_HIGH
        );
        problems.setDescription("Срочные уведомления о проблемах и возвратах по сделкам");
        problems.setSound(sound, attributes);
        problems.enableVibration(true);
        problems.setVibrationPattern(new long[]{0, 90, 80, 90});
        manager.createNotificationChannel(problems);
    }

    static Notification serviceNotification(Context context, String text) {
        Intent open = new Intent(context, MainActivity.class);
        PendingIntent openPi = PendingIntent.getActivity(
                context, 1, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Intent stop = new Intent(context, MonitorService.class).setAction(MonitorService.ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(
                context, 2, stop,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        return new Notification.Builder(context, SERVICE_CHANNEL)
                .setSmallIcon(R.drawable.ic_stat_order)
                .setContentTitle("Playerok Monitor активен")
                .setContentText(text)
                .setContentIntent(openPi)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setColor(Ui.ACCENT)
                .setCategory(Notification.CATEGORY_SERVICE)
                .addAction(new Notification.Action.Builder(null, "Остановить", stopPi).build())
                .build();
    }

    static void showEvent(
            Context context,
            long eventId,
            String kind,
            String dealId,
            String title,
            String body
    ) {
        ensureChannels(context);
        // Resolution updates the order card silently; creating a problem or a
        // refund is urgent and gets an alert.
        if ("PROBLEM_RESOLVED".equals(kind)) return;

        boolean urgent = "PROBLEM_CREATED".equals(kind) || "DEAL_ROLLED_BACK".equals(kind);
        String channel = urgent ? PROBLEMS_CHANNEL : ORDERS_CHANNEL;
        Intent open;
        if (dealId != null && !dealId.isEmpty()) {
            open = new Intent(context, OrderDetailActivity.class)
                    .putExtra(OrderDetailActivity.EXTRA_DEAL_ID, dealId);
        } else {
            open = new Intent(context, MainActivity.class);
        }
        open.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent openPi = PendingIntent.getActivity(
                context,
                (int) (10000 + eventId % 100000),
                open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Notification.Builder builder = new Notification.Builder(context, channel)
                .setSmallIcon(R.drawable.ic_stat_order)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setContentIntent(openPi)
                .setAutoCancel(true)
                .setCategory(Notification.CATEGORY_MESSAGE)
                .setVisibility(Notification.VISIBILITY_PUBLIC);
        builder.setGroup("playerok_monitor_events");
        if (urgent) builder.setColor(Ui.RED);

        NotificationManager manager = context.getSystemService(NotificationManager.class);
        manager.notify((int) (2000 + eventId % 1_000_000_000L), builder.build());
    }

    static void updateService(Context context, String text) {
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        manager.notify(SERVICE_NOTIFICATION_ID, serviceNotification(context, text));
    }
}
