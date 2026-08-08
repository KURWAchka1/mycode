package app.playerokmonitor;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent == null ? "" : intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action)
                && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) return;
        if (!Prefs.isEnabled(context)) return;
        if (UrlTools.validatePairingUrl(Prefs.getUrl(context)) != null) return;

        try {
            Intent service = new Intent(context, MonitorService.class)
                    .setAction(MonitorService.ACTION_START);
            context.startForegroundService(service);
        } catch (RuntimeException ignored) {
            // Android may temporarily reject a background FGS start; the user's
            // enabled preference is intentionally preserved for the next launch.
        }
    }
}
