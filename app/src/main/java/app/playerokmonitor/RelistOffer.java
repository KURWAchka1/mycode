package app.playerokmonitor;

import org.json.JSONObject;

final class RelistOffer {
    final String state;
    final String itemName;
    final String priorityId;
    final String priorityName;
    final int priorityPrice;
    final String priorityType;
    final int priorityPeriodDays;
    final String itemUrl;
    final String publishedAt;
    final boolean hasCover;

    private RelistOffer(
            String state,
            String itemName,
            String priorityId,
            String priorityName,
            int priorityPrice,
            String priorityType,
            int priorityPeriodDays,
            String itemUrl,
            String publishedAt,
            boolean hasCover
    ) {
        this.state = state;
        this.itemName = itemName;
        this.priorityId = priorityId;
        this.priorityName = priorityName;
        this.priorityPrice = priorityPrice;
        this.priorityType = priorityType;
        this.priorityPeriodDays = priorityPeriodDays;
        this.itemUrl = itemUrl;
        this.publishedAt = publishedAt;
        this.hasCover = hasCover;
    }

    static RelistOffer fromJson(String raw) throws Exception {
        JSONObject json = new JSONObject(raw);
        if (!json.optBoolean("ok", false)) {
            throw new IllegalStateException(json.optString("message", "VPS отклонил запрос"));
        }
        return new RelistOffer(
                json.optString("state", ""),
                json.optString("item_name", ""),
                json.optString("priority_id", ""),
                json.optString("priority_name", ""),
                json.optInt("priority_price", 0),
                json.optString("priority_type", ""),
                json.optInt("priority_period_days", 0),
                json.optString("item_url", json.optString("source_item_url", "")),
                json.optString("published_at", ""),
                json.optBoolean("has_cover", json.optBoolean("cover_preserved", false))
        );
    }

    boolean isPublished() { return "PUBLISHED".equalsIgnoreCase(state); }
    String feeLabel() { return priorityPrice <= 0 ? "Бесплатно" : priorityPrice + " ₽"; }
}
