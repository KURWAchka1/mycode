using System.Globalization;
using System.Text.Json.Serialization;

namespace PlayerokMonitor.Core;

public sealed class BuyerField
{
    [JsonPropertyName("label")] public string Label { get; init; } = "";
    [JsonPropertyName("value")] public string Value { get; init; } = "";
    [JsonPropertyName("copyable")] public bool Copyable { get; init; }
}

public sealed class Order
{
    [JsonPropertyName("deal_id")] public string DealId { get; init; } = "";
    [JsonPropertyName("chat_id")] public string ChatId { get; init; } = "";
    [JsonPropertyName("direction")] public string Direction { get; init; } = "";
    [JsonPropertyName("item_name")] public string ItemName { get; init; } = "";
    [JsonPropertyName("price")] public string Price { get; init; } = "";
    [JsonPropertyName("seller_net_amount")] public string SellerNetAmount { get; init; } = "";
    [JsonPropertyName("seller_net_status")] public string SellerNetStatus { get; init; } = "";
    [JsonPropertyName("seller_net_available_at")] public string SellerNetAvailableAt { get; init; } = "";
    [JsonPropertyName("counterparty")] public string Counterparty { get; init; } = "";
    [JsonPropertyName("buyer")] public string Buyer { get; init; } = "";
    [JsonPropertyName("buyer_comment")] public string BuyerComment { get; init; } = "";
    [JsonPropertyName("buyer_fields")] public List<BuyerField> BuyerFields { get; init; } = [];
    [JsonPropertyName("paid_at")] public string PaidAt { get; init; } = "";
    [JsonPropertyName("problem_active")] public bool ProblemActive { get; init; }
    [JsonPropertyName("problem_reported_at")] public string ProblemReportedAt { get; init; } = "";
    [JsonPropertyName("problem_reported_by_name")] public string ProblemReportedByName { get; init; } = "";
    [JsonPropertyName("problem_reported_by_role")] public string ProblemReportedByRole { get; init; } = "";
    [JsonPropertyName("problem_reported_by_relation")] public string ProblemReportedByRelation { get; init; } = "";
    [JsonPropertyName("problem_resolved_at")] public string ProblemResolvedAt { get; init; } = "";
    [JsonPropertyName("problem_resolved_by_name")] public string ProblemResolvedByName { get; init; } = "";
    [JsonPropertyName("problem_resolved_by_role")] public string ProblemResolvedByRole { get; init; } = "";
    [JsonPropertyName("problem_resolved_by_relation")] public string ProblemResolvedByRelation { get; init; } = "";
    [JsonPropertyName("rolled_back")] public bool RolledBack { get; init; }
    [JsonPropertyName("rolled_back_at")] public string RolledBackAt { get; init; } = "";
    [JsonPropertyName("rolled_back_by_name")] public string RolledBackByName { get; init; } = "";
    [JsonPropertyName("rolled_back_by_role")] public string RolledBackByRole { get; init; } = "";
    [JsonPropertyName("rolled_back_by_relation")] public string RolledBackByRelation { get; init; } = "";
    [JsonPropertyName("deal_status")] public string DealStatus { get; init; } = "";
    [JsonPropertyName("seller_fulfilled")] public bool SellerFulfilled { get; init; }
    [JsonPropertyName("seller_fulfilled_at")] public string SellerFulfilledAt { get; init; } = "";
    [JsonPropertyName("seller_fulfilled_by_name")] public string SellerFulfilledByName { get; init; } = "";
    [JsonPropertyName("seller_fulfilled_by_role")] public string SellerFulfilledByRole { get; init; } = "";
    [JsonPropertyName("seller_fulfilled_by_relation")] public string SellerFulfilledByRelation { get; init; } = "";
    [JsonPropertyName("recipient_confirmed")] public bool RecipientConfirmed { get; init; }
    [JsonPropertyName("recipient_confirmed_at")] public string RecipientConfirmedAt { get; init; } = "";
    [JsonPropertyName("recipient_confirmation_automatic")] public bool RecipientConfirmationAutomatic { get; init; }
    [JsonPropertyName("recipient_confirmed_by_name")] public string RecipientConfirmedByName { get; init; } = "";
    [JsonPropertyName("recipient_confirmed_by_role")] public string RecipientConfirmedByRole { get; init; } = "";
    [JsonPropertyName("recipient_confirmed_by_relation")] public string RecipientConfirmedByRelation { get; init; } = "";
    [JsonPropertyName("review_rating")] public int ReviewRating { get; init; }
    [JsonPropertyName("review_text")] public string ReviewText { get; init; } = "";
    [JsonPropertyName("review_created_at")] public string ReviewCreatedAt { get; init; } = "";
    [JsonPropertyName("review_author")] public string ReviewAuthor { get; init; } = "";
    [JsonPropertyName("relist_eligible")] public bool RelistEligible { get; init; }
    [JsonPropertyName("relist_state")] public string RelistState { get; init; } = "";
    [JsonPropertyName("relisted_item_id")] public string RelistedItemId { get; init; } = "";
    [JsonPropertyName("relisted_item_url")] public string RelistedItemUrl { get; init; } = "";
    [JsonPropertyName("relist_priority_price")] public int RelistPriorityPrice { get; init; }
    [JsonPropertyName("relist_priority_type")] public string RelistPriorityType { get; init; } = "";
    [JsonPropertyName("relist_listing_price")] public int RelistListingPrice { get; init; }
    [JsonPropertyName("relisted_at")] public string RelistedAt { get; init; } = "";
    [JsonPropertyName("relist_error")] public string RelistError { get; init; } = "";
    [JsonPropertyName("reply_sent")] public bool ReplySent { get; init; }
    [JsonPropertyName("reply_mode")] public string ReplyMode { get; init; } = "";
    [JsonPropertyName("sleep_reply_sent")] public bool SleepReplySent { get; init; }
    [JsonPropertyName("wake_reply_requested")] public bool WakeReplyRequested { get; init; }
    [JsonPropertyName("wake_reply_available")] public bool WakeReplyAvailable { get; init; }
    [JsonPropertyName("wake_reply_sent")] public bool WakeReplySent { get; init; }
    [JsonPropertyName("revision")] public long Revision { get; init; }
    [JsonPropertyName("deal_url")] public string DealUrl { get; init; } = "";

    [JsonIgnore] public bool IsSale => Direction.EndsWith("OUT", StringComparison.OrdinalIgnoreCase);
    [JsonIgnore] public bool IsPurchase => Direction.EndsWith("IN", StringComparison.OrdinalIgnoreCase);
    [JsonIgnore] public bool IsNew => IsSale && !SellerFulfilled && !RolledBack;
    [JsonIgnore] public bool IsRelisted => RelistState.Equals("PUBLISHED", StringComparison.OrdinalIgnoreCase);
    [JsonIgnore] public string DisplayName => string.IsNullOrWhiteSpace(ItemName) ? "Сделка Playerok" : ItemName;
    [JsonIgnore] public string CounterpartyDisplay => string.IsNullOrWhiteSpace(Counterparty) ? Buyer : Counterparty;
    [JsonIgnore] public string DirectionLabel => IsSale ? "Продажа" : IsPurchase ? "Покупка" : "Сделка";
    [JsonIgnore] public string PriceDisplay => FormatMoney(Price);
    [JsonIgnore] public string NetDisplay => string.IsNullOrWhiteSpace(SellerNetAmount) ? "—" : FormatMoney(SellerNetAmount);
    [JsonIgnore] public DateTimeOffset? PaidAtValue => ParseDate(PaidAt);
    [JsonIgnore] public string PaidAtDisplay => PaidAtValue?.ToLocalTime().ToString("d MMM, HH:mm", new CultureInfo("ru-RU")) ?? "Время неизвестно";
    [JsonIgnore] public string StateLabel => RolledBack ? "Возврат" : ProblemActive ? "Есть проблема" : IsNew ? "Нужно выполнить" : RecipientConfirmed ? "Завершён" : SellerFulfilled ? "Ждём получение" : DealStatus;
    [JsonIgnore] public string LifecycleLabel => $"{(SellerFulfilled ? "Выполнено" : "Не выполнено")}  •  {(RecipientConfirmed ? "Получено" : "Не получено")}";

    [JsonIgnore] public bool HasReview => ReviewRating > 0;
    [JsonIgnore] public string ReviewStars
    {
        get
        {
            var rating = Math.Clamp(ReviewRating, 0, 5);
            return rating == 0 ? "" : new string('★', rating) + new string('☆', 5 - rating);
        }
    }

    public string Actor(string name, string role, string relation)
    {
        if (relation.Equals("SELF", StringComparison.OrdinalIgnoreCase)) return "Вы";
        if (relation.Equals("PLAYEROK", StringComparison.OrdinalIgnoreCase)) return string.IsNullOrWhiteSpace(name) ? "Playerok" : $"Playerok · @{name}";
        if (!string.IsNullOrWhiteSpace(name)) return $"@{name}";
        if (relation.Equals("COUNTERPARTY", StringComparison.OrdinalIgnoreCase)) return IsSale ? "Покупатель" : "Продавец";
        return string.IsNullOrWhiteSpace(role) ? "Не определено" : role;
    }

    public static decimal? ParseMoney(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        var normalized = raw.Replace("₽", "", StringComparison.Ordinal).Replace("руб.", "", StringComparison.OrdinalIgnoreCase).Replace(" ", "", StringComparison.Ordinal).Replace(',', '.');
        return decimal.TryParse(normalized, NumberStyles.Number, CultureInfo.InvariantCulture, out var value) ? value : null;
    }

    public static string FormatMoney(string? raw)
    {
        var value = ParseMoney(raw);
        return value is null ? (string.IsNullOrWhiteSpace(raw) ? "—" : raw!) : $"{value.Value:N0} ₽";
    }

    public static DateTimeOffset? ParseDate(string? raw) => DateTimeOffset.TryParse(raw, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var value) ? value : null;
}

public sealed class OrdersEnvelope
{
    [JsonPropertyName("revision")] public long Revision { get; init; }
    [JsonPropertyName("unchanged")] public bool Unchanged { get; init; }
    [JsonPropertyName("orders")] public List<Order> Orders { get; init; } = [];
}

public sealed class EventRecord
{
    public long Id { get; init; }
    public string Type { get; init; } = "";
    public string DealId { get; init; } = "";
    public string Title { get; init; } = "";
    public string Body { get; init; } = "";

    public static EventRecord? Parse(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw) || raw == "NONE") return null;
        if (raw.StartsWith("EVENT2\t", StringComparison.Ordinal))
        {
            var parts = raw.Split('\t', 6);
            return parts.Length == 6 && long.TryParse(parts[1], out var id)
                ? new EventRecord { Id = id, Type = parts[2], DealId = parts[3], Title = parts[4], Body = parts[5] }
                : null;
        }
        if (raw.StartsWith("EVENT\t", StringComparison.Ordinal))
        {
            var parts = raw.Split('\t', 4);
            return parts.Length == 4 && long.TryParse(parts[1], out var id)
                ? new EventRecord { Id = id, Type = "ORDER_PAID", Title = parts[2], Body = parts[3] }
                : null;
        }
        return null;
    }
}

public sealed class AutoReplySettings
{
    [JsonPropertyName("ok")] public bool Ok { get; init; }
    [JsonPropertyName("enabled")] public bool Enabled { get; set; } = true;
    [JsonPropertyName("messages")] public List<string> Messages { get; set; } = [];
    [JsonPropertyName("effective_messages")] public List<string> EffectiveMessages { get; init; } = [];
    [JsonPropertyName("fulfillment_message")] public string FulfillmentMessage { get; set; } = "";
    [JsonPropertyName("sleep_enabled")] public bool SleepEnabled { get; set; }
    [JsonPropertyName("sleep_start")] public string SleepStart { get; set; } = "00:00";
    [JsonPropertyName("sleep_end")] public string SleepEnd { get; set; } = "08:00";
    [JsonPropertyName("sleep_timezone")] public string SleepTimezone { get; set; } = "Europe/Moscow";
    [JsonPropertyName("sleep_message")] public string SleepMessage { get; set; } = "";
    [JsonPropertyName("default_message")] public string DefaultMessage { get; init; } = "Ожидайте, пожалуйста. Продавец скоро приступит к выполнению Вашего заказа.";
    [JsonPropertyName("default_fulfillment_message")] public string DefaultFulfillmentMessage { get; init; } = "Заказ выполнен. Пожалуйста, проверьте товар и подтвердите получение, если всё в порядке.";
    [JsonPropertyName("default_sleep_message")] public string DefaultSleepMessage { get; init; } = "Сейчас продавец может спать. Он увидит заказ после пробуждения и напишет вам.";
}

public sealed class AutoReplyRequest
{
    [JsonPropertyName("enabled")] public bool Enabled { get; init; }
    [JsonPropertyName("messages")] public List<string> Messages { get; init; } = [];
    [JsonPropertyName("fulfillment_message")] public string FulfillmentMessage { get; init; } = "";
    [JsonPropertyName("sleep_enabled")] public bool SleepEnabled { get; init; }
    [JsonPropertyName("sleep_start")] public string SleepStart { get; init; } = "00:00";
    [JsonPropertyName("sleep_end")] public string SleepEnd { get; init; } = "08:00";
    [JsonPropertyName("sleep_timezone")] public string SleepTimezone { get; init; } = "Europe/Moscow";
    [JsonPropertyName("sleep_message")] public string SleepMessage { get; init; } = "";
}

public sealed class RelistOffer
{
    [JsonPropertyName("ok")] public bool Ok { get; init; }
    [JsonPropertyName("message")] public string Message { get; init; } = "";
    [JsonPropertyName("state")] public string State { get; init; } = "";
    [JsonPropertyName("item_name")] public string ItemName { get; init; } = "";
    [JsonPropertyName("priority_id")] public string PriorityId { get; init; } = "";
    [JsonPropertyName("priority_name")] public string PriorityName { get; init; } = "";
    [JsonPropertyName("priority_price")] public int PriorityPrice { get; init; }
    [JsonPropertyName("priority_type")] public string PriorityType { get; init; } = "";
    [JsonPropertyName("priority_period_days")] public int PriorityPeriodDays { get; init; }
    [JsonPropertyName("item_url")] public string ItemUrl { get; init; } = "";
    [JsonPropertyName("source_item_url")] public string SourceItemUrl { get; init; } = "";
    [JsonPropertyName("published_at")] public string PublishedAt { get; init; } = "";
    [JsonPropertyName("has_cover")] public bool HasCover { get; init; }
    [JsonPropertyName("cover_preserved")] public bool CoverPreserved { get; init; }
    [JsonPropertyName("item_price")] public int ItemPrice { get; init; }
    [JsonPropertyName("source_item_price")] public int SourceItemPrice { get; init; }
    [JsonPropertyName("discounted_price")] public int DiscountedPrice { get; init; }
    [JsonPropertyName("priority_calculation_price")] public int PriorityCalculationPrice { get; init; }
    [JsonPropertyName("price_customized")] public bool PriceCustomized { get; init; }
    [JsonPropertyName("price_locked")] public bool PriceLocked { get; init; }
    [JsonIgnore] public bool IsPublished => State.Equals("PUBLISHED", StringComparison.OrdinalIgnoreCase);
    [JsonIgnore] public bool IsPremium => PriorityType.Equals("PREMIUM", StringComparison.OrdinalIgnoreCase);
    [JsonIgnore] public string EffectiveItemUrl => string.IsNullOrWhiteSpace(ItemUrl) ? SourceItemUrl : ItemUrl;
    [JsonIgnore] public string FeeLabel => $"{(string.IsNullOrWhiteSpace(PriorityName) ? IsPremium ? "Premium" : "Обычное размещение" : PriorityName)}: {(PriorityPrice <= 0 ? "бесплатно" : $"{PriorityPrice:N0} ₽")}";
}

public sealed class ApiResult
{
    [JsonPropertyName("ok")] public bool Ok { get; init; }
    [JsonPropertyName("code")] public string Code { get; init; } = "";
    [JsonPropertyName("message")] public string Message { get; init; } = "";
}
