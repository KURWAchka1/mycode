package app.playerokmonitor;

import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

import java.util.concurrent.atomic.AtomicBoolean;

public final class MonitorService extends Service {
    public static final String ACTION_START = "app.playerokmonitor.action.START";
    public static final String ACTION_STOP = "app.playerokmonitor.action.STOP";

    private final AtomicBoolean workerRunning = new AtomicBoolean(false);
    private volatile Thread worker;

    @Override
    public void onCreate() {
        super.onCreate();
        NotificationHelper.ensureChannels(this);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? ACTION_START : intent.getAction();
        if (ACTION_STOP.equals(action)) {
            Prefs.setEnabled(this, false);
            stopWorker();
            stopForeground(STOP_FOREGROUND_REMOVE);
            stopSelf();
            return START_NOT_STICKY;
        }

        String pairingUrl = Prefs.getUrl(this);
        if (UrlTools.validatePairingUrl(pairingUrl) != null) {
            Prefs.setEnabled(this, false);
            stopSelf();
            return START_NOT_STICKY;
        }

        Prefs.setEnabled(this, true);
        startAsForeground("Подключение к VPS…");
        startWorkerIfNeeded();
        return START_STICKY;
    }

    private void startAsForeground(String text) {
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(
                    NotificationHelper.SERVICE_NOTIFICATION_ID,
                    NotificationHelper.serviceNotification(this, text),
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            );
        } else {
            startForeground(
                    NotificationHelper.SERVICE_NOTIFICATION_ID,
                    NotificationHelper.serviceNotification(this, text)
            );
        }
    }

    private void startWorkerIfNeeded() {
        if (!workerRunning.compareAndSet(false, true)) return;
        worker = new Thread(this::pollLoop, "playerok-long-poll");
        worker.start();
    }

    private void pollLoop() {
        int failures = 0;
        try {
            while (Prefs.isEnabled(this) && !Thread.currentThread().isInterrupted()) {
                String pairingUrl = Prefs.getUrl(this);
                String error = UrlTools.validatePairingUrl(pairingUrl);
                if (error != null) {
                    NotificationHelper.updateService(this, error);
                    sleepQuietly(5000);
                    continue;
                }

                long after = Prefs.getLastEventId(this);
                try {
                    String response = HttpTextClient.get(UrlTools.pollUrl(pairingUrl, after), 60_000);
                    failures = 0;
                    NotificationHelper.updateService(this, "Соединение с VPS активно");
                    handlePollResponse(response);
                } catch (Exception e) {
                    failures++;
                    NotificationHelper.updateService(this, "Нет связи с VPS — переподключение…");
                    long delay = Math.min(15_000L, 1000L * Math.max(1, failures));
                    sleepQuietly(delay);
                }
            }
        } finally {
            workerRunning.set(false);
        }
    }

    private void handlePollResponse(String response) {
        if (response == null || response.isEmpty() || "NONE".equals(response)) return;
        if (!response.startsWith("EVENT\t")) return;

        String[] parts = response.split("\t", 4);
        if (parts.length < 4) return;
        try {
            long eventId = Long.parseLong(parts[1]);
            long current = Prefs.getLastEventId(this);
            if (eventId <= current) return;
            Prefs.setLastEventId(this, eventId);
            NotificationHelper.showOrder(this, eventId, parts[2], parts[3]);
        } catch (NumberFormatException ignored) {
        }
    }

    private void stopWorker() {
        Thread current = worker;
        if (current != null) current.interrupt();
        worker = null;
        workerRunning.set(false);
    }

    private static void sleepQuietly(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public void onDestroy() {
        stopWorker();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
