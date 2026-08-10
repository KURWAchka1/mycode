package app.playerokmonitor;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONException;
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

    static List<OrderData> filterByDirection(List<OrderData> values, String direction) {
        ArrayList<OrderData> result = new ArrayList<>();
        if (values == null) return result;
        for (OrderData order : values) {
            if (direction.equals(order.direction)) result.add(order);
        }
        return result;
    }

    static List<OrderData> filterNewOrders(List<OrderData> values) {
        ArrayList<OrderData> result = new ArrayList<>();
        if (values == null) return result;
        for (OrderData order : values) {
            // "New" means a paid sale still awaiting this account's own
            // fulfillment action. Refunded deals are no longer actionable.
            if (order.isSale() && !order.sellerFulfilled && !order.rolledBack) {
                result.add(order);
            }
        }
        return result;
    }

    static int countUnclassified(List<OrderData> values) {
        int count = 0;
        if (values == null) return 0;
        for (OrderData order : values) {
            if (!order.isSale() && !order.isPurchase()) count++;
        }
        return count;
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
            String response = HttpTextClient.get(
                    UrlTools.ordersUrl(pairingUrl, currentRevision, 200),
                    15_000
            );
            String trimmed = response == null ? "" : response.trim();
            if (!trimmed.startsWith("{")) {
                if (trimmed.startsWith("EVENT") || "NONE".equals(trimmed)) {
                    throw new IllegalStateException("VPS не поддерживает новый список сделок — установите сервер v11");
                }
                throw new IllegalStateException("VPS вернул неизвестный формат ответа");
            }

            final JSONObject root;
            try {
                root = new JSONObject(trimmed);
            } catch (JSONException e) {
                throw new IllegalStateException("VPS вернул повреждённый JSON", e);
            }

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
            GalaxyIntegration.refreshSurfaces(context);
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
