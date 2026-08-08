package app.playerokmonitor;

import org.json.JSONObject;

final class OrderData {
    static final String DIRECTION_SALE = "OUT";
    static final String DIRECTION_PURCHASE = "IN";

    final String dealId;
    final String chatId;
    final String direction;
    final String itemName;
    final String price;
    final String counterparty;
    final String buyerComment;
    final String paidAt;
    final boolean problemActive;
    final String problemReportedAt;
    final String problemResolvedAt;
    final boolean replySent;
    final long revision;
    final String dealUrl;

    private OrderData(
            String dealId,
            String chatId,
            String direction,
            String itemName,
            String price,
            String counterparty,
            String buyerComment,
            String paidAt,
            boolean problemActive,
            String problemReportedAt,
            String problemResolvedAt,
            boolean replySent,
            long revision,
            String dealUrl
    ) {
        this.dealId = dealId;
        this.chatId = chatId;
        this.direction = normalizeDirection(direction);
        this.itemName = itemName;
        this.price = price;
        this.counterparty = counterparty;
        this.buyerComment = buyerComment;
        this.paidAt = paidAt;
        this.problemActive = problemActive;
        this.problemReportedAt = problemReportedAt;
        this.problemResolvedAt = problemResolvedAt;
        this.replySent = replySent;
        this.revision = revision;
        this.dealUrl = dealUrl;
    }

    static OrderData fromJson(JSONObject o) {
        String dealId = o.optString("deal_id", "");
        String dealUrl = o.optString("deal_url", "");
        if (dealUrl.isEmpty() && !dealId.isEmpty()) {
            dealUrl = "https://playerok.com/deal/" + dealId;
        }
        String counterparty = o.optString("counterparty", "");
        if (counterparty.isEmpty()) counterparty = o.optString("buyer", "");
        return new OrderData(
                dealId,
                o.optString("chat_id", ""),
                o.optString("direction", ""),
                o.optString("item_name", ""),
                o.optString("price", ""),
                counterparty,
                o.optString("buyer_comment", ""),
                o.optString("paid_at", ""),
                o.optBoolean("problem_active", false),
                o.optString("problem_reported_at", ""),
                o.optString("problem_resolved_at", ""),
                o.optBoolean("reply_sent", false),
                o.optLong("revision", 0L),
                dealUrl
        );
    }

    private static String normalizeDirection(String raw) {
        String value = raw == null ? "" : raw.trim().toUpperCase();
        if (value.endsWith(".OUT")) value = "OUT";
        if (value.endsWith(".IN")) value = "IN";
        return DIRECTION_SALE.equals(value) || DIRECTION_PURCHASE.equals(value) ? value : "";
    }

    boolean isSale() {
        return DIRECTION_SALE.equals(direction);
    }

    boolean isPurchase() {
        return DIRECTION_PURCHASE.equals(direction);
    }

    String counterpartyLabel() {
        return isSale() ? "Покупатель" : "Продавец";
    }

    String displayName() {
        return itemName.isEmpty() ? "Сделка Playerok" : itemName;
    }
}
