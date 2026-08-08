package app.playerokmonitor;

import android.app.PendingIntent;
import android.app.ShortcutInfo;
import android.app.ShortcutManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.graphics.drawable.Icon;
import android.service.quicksettings.TileService;

import java.util.Arrays;

/** Publishes standard Android surfaces used natively by One UI and Samsung DeX. */
final class GalaxyIntegration {
    private GalaxyIntegration() {}

    static void publishShortcuts(Context context) {
        ShortcutManager manager = context.getSystemService(ShortcutManager.class);
        if (manager == null || !manager.isRequestPinShortcutSupported() && manager.getMaxShortcutCountPerActivity() == 0) {
            return;
        }
        Intent sales = new Intent(context, MainActivity.class)
                .setAction("app.playerokmonitor.shortcut.SALES")
                .putExtra(MainActivity.EXTRA_DIRECTION, OrderData.DIRECTION_SALE);
        Intent purchases = new Intent(context, MainActivity.class)
                .setAction("app.playerokmonitor.shortcut.PURCHASES")
                .putExtra(MainActivity.EXTRA_DIRECTION, OrderData.DIRECTION_PURCHASE);
        Intent settings = new Intent(context, SettingsActivity.class)
                .setAction("app.playerokmonitor.shortcut.SETTINGS");
        manager.setDynamicShortcuts(Arrays.asList(
                new ShortcutInfo.Builder(context, "sales")
                        .setShortLabel("Продажи")
                        .setLongLabel("Мои продажи Playerok")
                        .setIcon(Icon.createWithResource(context, R.drawable.ic_stat_order))
                        .setIntent(sales)
                        .build(),
                new ShortcutInfo.Builder(context, "purchases")
                        .setShortLabel("Покупки")
                        .setLongLabel("Мои покупки Playerok")
                        .setIcon(Icon.createWithResource(context, R.drawable.ic_nav_open))
                        .setIntent(purchases)
                        .build(),
                new ShortcutInfo.Builder(context, "settings")
                        .setShortLabel("Настройки")
                        .setLongLabel("Настройки мониторинга")
                        .setIcon(Icon.createWithResource(context, R.drawable.ic_nav_settings))
                        .setIntent(settings)
                        .build()
        ));
    }

    static void refreshSurfaces(Context context) {
        OrderWidgetProvider.updateAll(context);
        TileService.requestListeningState(
                context,
                new ComponentName(context, MonitorTileService.class)
        );
    }
}
