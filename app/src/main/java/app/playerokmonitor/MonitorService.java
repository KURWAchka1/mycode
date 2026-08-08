package app.playerokmonitor;

import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

import org.json.JSONObject;

import java.util.concurrent.atomic.AtomicBoolean;

public final class MonitorService extends Service {
    public static final String ACTION_START = "app.playerokmonitor.action.START";
    public static final String ACTION_STOP = "app.playerokmonitor.action.STOP";

    private final AtomicBoolean workerRunning = new AtomicBoolean(false);
    private volatile Thread worker;

    @Override
    public void onCreate() {
        super.onCreate();
        Ui.configure(this);
        NotificationHelper.ensureChannels(this);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? ACTION_START : intent.getAction();
        if (ACTION_STOP.equals(action)) {
            Prefs.setEnabled(this, false);
            GalaxyIntegration.refreshSurfaces(this);
            stopWorker();
            stopForeground(STOP_FOREGROUND_REMOVE);
            stopSelf();
            return START_NOT_STICKY;
        }

        String pairingUrl = Prefs.getUrl(this);
        if (UrlTools.validatePairingUrl(pairingUrl) != null) {
            Prefs.setEnabled(this, false);
            GalaxyIntegration.refreshSurfaces(this);
            stopSelf();
            return START_NOT_STICKY;
        }

        Prefs.setEnabled(this, true);
        GalaxyIntegration.refreshSurfaces(this);
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
                    sleepQuietly(5_000L);
                    continue;
                }

                try {
                    if (!Prefs.isEventStreamBootstrapped(this, pairingUrl)) {
                        bootstrapEventStream(pairingUrl);
                        failures = 0;
                        continue;
                    }

                    long after = Prefs.getLastEventId(this);
                    String response = HttpTextClient.get(
                            UrlTools.eventsV2Url(pairingUrl, after),
                            60_000
                    );
                    failures = 0;
                    NotificationHelper.updateService(this, "Соединение с VPS активно");
                    handlePollResponse(pairingUrl, response);
                } catch (Exception e) {
                    failures++;
                    String status = Prefs.isEventStreamBootstrapped(this, pairingUrl)
                            ? "Нет связи с VPS — переподключение…"
                            : "Первичная синхронизация — повтор подключения…";
                    NotificationHelper.updateService(this, status);
                    sleepQuietly(Math.min(15_000L, 1_000L * Math.max(1, failures)));
                }
            }
        } finally {
            workerRunning.set(false);
        }
    }

    private void bootstrapEventStream(String pairingUrl) throws Exception {
        NotificationHelper.updateService(this, "Тихая первичная синхронизация…");
        String response = HttpTextClient.get(UrlTools.cursorUrl(pairingUrl), 15_000).trim();
        JSONObject root = new JSONObject(response);
        if (!root.has("latest_event_id")) {
            throw new IllegalStateException("VPS не вернул курсор событий");
        }
        long latest = Math.max(0L, root.getLong("latest_event_id"));
        // Commit the baseline before loading cards. Events created after this
        // exact point remain newer than the cursor and will notify normally.
        Prefs.markEventStreamBootstrapped(this, pairingUrl, latest);
        syncOrdersQuietly(pairingUrl);
        NotificationHelper.updateService(this, "История синхронизирована — мониторинг активен");
    }

    private void handlePollResponse(String pairingUrl, String response) {
        if (response == null || response.isEmpty() || "NONE".equals(response)) return;
        if (response.startsWith("EVENT2\t")) {
            String[] parts = response.split("\t", 6);
            if (parts.length < 6) return;
            try {
                long eventId = Long.parseLong(parts[1]);
                long current = Prefs.getLastEventId(this);
                if (eventId <= current) return;
                Prefs.setLastEventId(this, eventId);
                NotificationHelper.showEvent(
                        this,
                        eventId,
                        parts[2],
                        parts[3],
                        parts[4],
                        parts[5]
                );
                syncOrdersQuietly(pairingUrl);
            } catch (NumberFormatException ignored) {
            }
            return;
        }

        if (response.startsWith("EVENT\t")) {
            String[] parts = response.split("\t", 4);
            if (parts.length < 4) return;
            try {
                long eventId = Long.parseLong(parts[1]);
                long current = Prefs.getLastEventId(this);
                if (eventId <= current) return;
                Prefs.setLastEventId(this, eventId);
                NotificationHelper.showEvent(
                        this,
                        eventId,
                        "ORDER_PAID",
                        "",
                        parts[2],
                        parts[3]
                );
            } catch (NumberFormatException ignored) {
            }
        }
    }

    private void syncOrdersQuietly(String pairingUrl) {
        try {
            OrdersRepository.sync(this, pairingUrl);
        } catch (Exception ignored) {
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
