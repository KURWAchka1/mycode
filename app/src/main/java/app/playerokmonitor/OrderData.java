package app.playerokmonitor;

import org.json.JSONObject;

final class OrderData {
    final String dealId;
    final String chatId;
    final String itemName;
    final String price;
    final String buyer;
    final String buyerComment;
    final String paidAt;
    final boolean problemActive;
    final String problemReportedAt;
    final String problemResolvedAt;
    final boolean replySent;
    final long revision;
    final String dealUrl;

    private OrderData(String dealId, String chatId, String itemName, String price, String buyer,
                      String buyerComment, String paidAt, boolean problemActive,
                      String problemReportedAt, String problemResolvedAt, boolean replySent,
                      long revision, String dealUrl) {
        this.dealId = dealId;
        this.chatId = chatId;
        this.itemName = itemName;
        this.price = price;
        this.buyer = buyer;
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
        if (dealUrl.isEmpty() && !dealId.isEmpty()) dealUrl = "https://playerok.com/deal/" + dealId;
        return new OrderData(
                dealId,
                o.optString("chat_id", ""),
                o.optString("item_name", ""),
                o.optString("price", ""),
                o.optString("buyer", ""),
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

    String displayName() {
        return itemName.isEmpty() ? "Заказ Playerok" : itemName;
    }
}
