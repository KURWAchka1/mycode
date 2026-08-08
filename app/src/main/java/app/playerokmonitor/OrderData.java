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
    final String problemReportedByName;
    final String problemReportedByRole;
    final String problemReportedByRelation;
    final String problemResolvedAt;
    final String problemResolvedByName;
    final String problemResolvedByRole;
    final String problemResolvedByRelation;
    final boolean rolledBack;
    final String rolledBackAt;
    final String rolledBackByName;
    final String rolledBackByRole;
    final String rolledBackByRelation;
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
            String problemReportedByName,
            String problemReportedByRole,
            String problemReportedByRelation,
            String problemResolvedAt,
            String problemResolvedByName,
            String problemResolvedByRole,
            String problemResolvedByRelation,
            boolean rolledBack,
            String rolledBackAt,
            String rolledBackByName,
            String rolledBackByRole,
            String rolledBackByRelation,
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
        this.problemReportedByName = problemReportedByName;
        this.problemReportedByRole = problemReportedByRole;
        this.problemReportedByRelation = problemReportedByRelation;
        this.problemResolvedAt = problemResolvedAt;
        this.problemResolvedByName = problemResolvedByName;
        this.problemResolvedByRole = problemResolvedByRole;
        this.problemResolvedByRelation = problemResolvedByRelation;
        this.rolledBack = rolledBack;
        this.rolledBackAt = rolledBackAt;
        this.rolledBackByName = rolledBackByName;
        this.rolledBackByRole = rolledBackByRole;
        this.rolledBackByRelation = rolledBackByRelation;
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
                o.optString("problem_reported_by_name", ""),
                o.optString("problem_reported_by_role", ""),
                o.optString("problem_reported_by_relation", ""),
                o.optString("problem_resolved_at", ""),
                o.optString("problem_resolved_by_name", ""),
                o.optString("problem_resolved_by_role", ""),
                o.optString("problem_resolved_by_relation", ""),
                o.optBoolean("rolled_back", false),
                o.optString("rolled_back_at", ""),
                o.optString("rolled_back_by_name", ""),
                o.optString("rolled_back_by_role", ""),
                o.optString("rolled_back_by_relation", ""),
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

    private String actorLabel(String name, String role, String relation) {
        String rel = relation == null ? "" : relation.trim().toUpperCase();
        String cleanName = name == null ? "" : name.trim();
        String cleanRole = role == null ? "" : role.trim();
        if ("SELF".equals(rel)) return "Вы";
        if ("PLAYEROK".equals(rel)) {
            if (!cleanName.isEmpty()) return "Playerok · @" + cleanName;
            if (!cleanRole.isEmpty()) return "Playerok · " + cleanRole;
            return "Playerok";
        }
        if (!cleanName.isEmpty()) return "@" + cleanName;
        if ("COUNTERPARTY".equals(rel)) return isSale() ? "Покупатель" : "Продавец";
        return "Не удалось определить";
    }

    boolean isSale() { return DIRECTION_SALE.equals(direction); }
    boolean isPurchase() { return DIRECTION_PURCHASE.equals(direction); }

    String counterpartyLabel() { return isSale() ? "Покупатель" : "Продавец"; }
    String problemReporterLabel() { return actorLabel(problemReportedByName, problemReportedByRole, problemReportedByRelation); }
    String problemResolverLabel() { return actorLabel(problemResolvedByName, problemResolvedByRole, problemResolvedByRelation); }
    String refundActorLabel() { return actorLabel(rolledBackByName, rolledBackByRole, rolledBackByRelation); }

    String displayName() { return itemName.isEmpty() ? "Сделка Playerok" : itemName; }
}
