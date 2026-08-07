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
    // Notification channel sound settings are persistent. v3 guarantees that
    // upgrades from 1.0.1 use the new clean 16-bit chime instead of cached v2.
    static final String ORDERS_CHANNEL = "playerok_orders_v3";
    static final int SERVICE_NOTIFICATION_ID = 1001;

    private NotificationHelper() {}

    static void ensureChannels(Context context) {
        if (Build.VERSION.SDK_INT < 26) return;
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

        NotificationChannel orders = new NotificationChannel(
                ORDERS_CHANNEL,
                "Новые заказы Playerok",
                NotificationManager.IMPORTANCE_HIGH
        );
        orders.setDescription("Чистый короткий мягкий сигнал новых оплаченных заказов");
        Uri sound = Uri.parse("android.resource://" + context.getPackageName() + "/" + R.raw.order_alert);
        AudioAttributes attributes = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build();
        orders.setSound(sound, attributes);
        orders.enableVibration(true);
        orders.setVibrationPattern(new long[]{0, 55, 70, 65});
        manager.createNotificationChannel(orders);
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
                .setCategory(Notification.CATEGORY_SERVICE)
                .addAction(new Notification.Action.Builder(
                        null, "Остановить", stopPi).build())
                .build();
    }

    static void showOrder(Context context, long eventId, String title, String body) {
        ensureChannels(context);
        Intent open = new Intent(context, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent openPi = PendingIntent.getActivity(
                context, (int) (10000 + eventId % 100000), open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Notification notification = new Notification.Builder(context, ORDERS_CHANNEL)
                .setSmallIcon(R.drawable.ic_stat_order)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setContentIntent(openPi)
                .setAutoCancel(true)
                .setCategory(Notification.CATEGORY_MESSAGE)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .build();

        NotificationManager manager = context.getSystemService(NotificationManager.class);
        manager.notify((int) (2000 + eventId % 1_000_000_000L), notification);
    }

    static void updateService(Context context, String text) {
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        manager.notify(SERVICE_NOTIFICATION_ID, serviceNotification(context, text));
    }
}
