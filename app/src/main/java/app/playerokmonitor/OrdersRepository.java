package app.playerokmonitor;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

final class OrdersRepository {
    private static final Object LOCK = new Object();

    static final class SyncResult {
        final List<OrderData> orders;
        final long revision;
        final boolean unchanged;

        SyncResult(List<OrderData> orders, long revision, boolean unchanged) {
            this.orders = orders;
            this.revision = revision;
            this.unchanged = unchanged;
        }
    }

    private OrdersRepository() {}

    static List<OrderData> loadCached(Context context) {
        synchronized (LOCK) {
            return parseArray(Prefs.getOrdersJson(context));
        }
    }

    static OrderData findCached(Context context, String dealId) {
        if (dealId == null || dealId.isEmpty()) return null;
        for (OrderData order : loadCached(context)) {
            if (dealId.equals(order.dealId)) return order;
        }
        return null;
    }

    static SyncResult sync(Context context, String pairingUrl) throws Exception {
        synchronized (LOCK) {
            long currentRevision = Prefs.getOrdersRevision(context);
            String response = HttpTextClient.get(UrlTools.ordersUrl(pairingUrl, currentRevision, 100), 15_000);
            JSONObject root = new JSONObject(response);
            long revision = root.optLong("revision", currentRevision);
            boolean unchanged = root.optBoolean("unchanged", false);
            List<OrderData> orders;
            if (unchanged) {
                orders = parseArray(Prefs.getOrdersJson(context));
            } else {
                JSONArray array = root.optJSONArray("orders");
                if (array == null) array = new JSONArray();
                Prefs.setOrdersJson(context, array.toString());
                Prefs.setOrdersRevision(context, revision);
                orders = parseArray(array.toString());
            }
            return new SyncResult(Collections.unmodifiableList(orders), revision, unchanged);
        }
    }

    private static List<OrderData> parseArray(String json) {
        ArrayList<OrderData> result = new ArrayList<>();
        try {
            JSONArray array = new JSONArray(json == null ? "[]" : json);
            for (int i = 0; i < array.length(); i++) {
                JSONObject o = array.optJSONObject(i);
                if (o == null) continue;
                OrderData item = OrderData.fromJson(o);
                if (!item.dealId.isEmpty()) result.add(item);
            }
        } catch (Exception ignored) {
        }
        return result;
    }
}
