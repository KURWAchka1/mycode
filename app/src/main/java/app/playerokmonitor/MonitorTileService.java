package app.playerokmonitor;

import android.annotation.SuppressLint;
import android.app.PendingIntent;
import android.content.Intent;
import android.graphics.drawable.Icon;
import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

/** One UI Quick panel tile for starting/stopping the VPS monitor. */
public final class MonitorTileService extends TileService {
    @Override
    public void onStartListening() {
        super.onStartListening();
        updateTile();
    }

    @Override
    public void onClick() {
        super.onClick();
        String url = Prefs.getUrl(this);
        if (UrlTools.validatePairingUrl(url) != null) {
            Intent settings = new Intent(this, SettingsActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            if (Build.VERSION.SDK_INT >= 34) {
                PendingIntent pi = PendingIntent.getActivity(
                        this, 71, settings,
                        PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
                startActivityAndCollapse(pi);
            } else {
                startLegacySettings(settings);
            }
            return;
        }

        boolean enable = !Prefs.isEnabled(this);
        Prefs.setEnabled(this, enable);
        Intent service = new Intent(this, MonitorService.class)
                .setAction(enable ? MonitorService.ACTION_START : MonitorService.ACTION_STOP);
        if (enable) startForegroundService(service); else startService(service);
        updateTile();
        GalaxyIntegration.refreshSurfaces(this);
    }

    @SuppressLint("StartActivityAndCollapseDeprecated")
    @SuppressWarnings("deprecation")
    private void startLegacySettings(Intent intent) {
        startActivityAndCollapse(intent);
    }

    private void updateTile() {
        Tile tile = getQsTile();
        if (tile == null) return;
        boolean configured = UrlTools.validatePairingUrl(Prefs.getUrl(this)) == null;
        boolean enabled = configured && Prefs.isEnabled(this);
        tile.setState(!configured ? Tile.STATE_UNAVAILABLE
                : enabled ? Tile.STATE_ACTIVE : Tile.STATE_INACTIVE);
        tile.setLabel("Playerok Monitor");
        if (Build.VERSION.SDK_INT >= 29) {
            tile.setSubtitle(!configured ? "Нужна настройка" : enabled ? "Включён" : "Выключен");
        }
        tile.setIcon(Icon.createWithResource(this, R.drawable.ic_stat_order));
        tile.updateTile();
    }
}
