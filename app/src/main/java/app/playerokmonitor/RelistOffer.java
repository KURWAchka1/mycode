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
    final int itemPrice;
    final int sourceItemPrice;
    final int discountedPrice;
    final int priorityCalculationPrice;
    final boolean priceCustomized;
    final boolean priceLocked;

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
            boolean hasCover,
            int itemPrice,
            int sourceItemPrice,
            int discountedPrice,
            int priorityCalculationPrice,
            boolean priceCustomized,
            boolean priceLocked
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
        this.itemPrice = itemPrice;
        this.sourceItemPrice = sourceItemPrice;
        this.discountedPrice = discountedPrice;
        this.priorityCalculationPrice = priorityCalculationPrice;
        this.priceCustomized = priceCustomized;
        this.priceLocked = priceLocked;
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
                json.optBoolean("has_cover", json.optBoolean("cover_preserved", false)),
                json.optInt("item_price", 0),
                json.optInt("source_item_price", json.optInt("item_price", 0)),
                json.optInt("discounted_price", 0),
                json.optInt("priority_calculation_price", 0),
                json.optBoolean("price_customized", false),
                json.optBoolean("price_locked", false)
        );
    }

    boolean isPublished() { return "PUBLISHED".equalsIgnoreCase(state); }
    boolean isPremium() { return "PREMIUM".equalsIgnoreCase(priorityType); }
    String feeLabel() {
        String fallback = isPremium() ? "Premium" : "Обычное размещение";
        String name = priorityName.isEmpty() ? fallback : priorityName;
        return priorityPrice <= 0 ? name + ": бесплатно" : name + ": " + priorityPrice + " ₽";
    }
}
