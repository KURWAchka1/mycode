using System.Net.Http.Json;
using System.Text;
using System.Text.Json;

namespace PlayerokMonitor.Core;

public sealed class PlayerokClient : IDisposable
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true
    };

    private readonly HttpClient _http;
    public string PairingUrl { get; }

    public PlayerokClient(string pairingUrl, HttpMessageHandler? handler = null)
    {
        var error = ValidatePairingUrl(pairingUrl);
        if (error is not null) throw new ArgumentException(error, nameof(pairingUrl));
        PairingUrl = pairingUrl.Trim();
        _http = handler is null ? new HttpClient() : new HttpClient(handler, true);
        _http.Timeout = TimeSpan.FromSeconds(70);
        _http.DefaultRequestHeaders.UserAgent.ParseAdd("PlayerokMonitor-Desktop/1.1.4 Windows11");
        _http.DefaultRequestHeaders.Accept.ParseAdd("application/json, text/plain, */*");
    }

    public static string? ValidatePairingUrl(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return "Вставьте Pairing URL с VPS";
        if (!Uri.TryCreate(raw.Trim(), UriKind.Absolute, out var uri)) return "Некорректный URL";
        if (!uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)) return "Разрешён только HTTPS";
        if (string.IsNullOrWhiteSpace(uri.Host)) return "В URL нет адреса VPS";
        if (!uri.AbsolutePath.Equals("/poll", StringComparison.Ordinal)) return "Pairing URL должен содержать /poll";
        var query = ParseQuery(uri.Query);
        return query.ContainsKey("token") && !string.IsNullOrWhiteSpace(query["token"]) ? null : "В URL нет API token";
    }

    public async Task<bool> CheckHealthAsync(CancellationToken cancellationToken = default)
    {
        var text = (await GetTextAsync(Build("/health"), cancellationToken)).Trim();
        if (text.Equals("OK", StringComparison.OrdinalIgnoreCase)) return true;

        try
        {
            using var doc = JsonDocument.Parse(text);
            var root = doc.RootElement;
            if (root.ValueKind == JsonValueKind.True) return true;
            if (root.ValueKind == JsonValueKind.String) return root.GetString()?.Equals("OK", StringComparison.OrdinalIgnoreCase) == true;
            return root.ValueKind == JsonValueKind.Object
                && root.TryGetProperty("ok", out var ok)
                && ok.ValueKind is JsonValueKind.True;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    public async Task<long> GetLatestEventIdAsync(CancellationToken cancellationToken = default)
    {
        using var doc = await GetJsonAsync(Build("/cursor"), cancellationToken);
        return doc.RootElement.TryGetProperty("latest_event_id", out var value) ? Math.Max(0, value.GetInt64()) : 0;
    }

    public async Task<EventRecord?> PollEventAsync(long after, CancellationToken cancellationToken = default)
    {
        var raw = await GetTextAsync(Build("/poll", ("after", Math.Max(0, after).ToString()), ("mode", "eventsv2")), cancellationToken);
        return EventRecord.Parse(raw.Trim());
    }

    public async Task<OrdersEnvelope> GetOrdersAsync(long afterRevision, CancellationToken cancellationToken = default)
    {
        var uri = Build("/poll", ("mode", "orders"), ("after_rev", Math.Max(0, afterRevision).ToString()), ("limit", "200"));
        return await GetAsync<OrdersEnvelope>(uri, cancellationToken) ?? new OrdersEnvelope();
    }

    public Task<AutoReplySettings> GetAutoRepliesAsync(CancellationToken cancellationToken = default) =>
        GetRequiredAsync<AutoReplySettings>(Build("/poll", ("mode", "auto_replies")), cancellationToken);

    public async Task<AutoReplySettings> SaveAutoRepliesAsync(AutoReplyRequest request, CancellationToken cancellationToken = default)
    {
        var uri = Build("/poll", ("mode", "auto_replies"));
        using var response = await _http.PostAsJsonAsync(uri, request, Json, cancellationToken);
        return await ReadRequiredAsync<AutoReplySettings>(response, cancellationToken);
    }

    public async Task<ApiResult> WakeAsync(string dealId, CancellationToken cancellationToken = default)
    {
        using var response = await _http.PostAsync(Build("/wake", ("deal_id", dealId)), new ByteArrayContent([]), cancellationToken);
        return await ReadRequiredAsync<ApiResult>(response, cancellationToken);
    }

    public Task<RelistOffer> GetRelistSetupAsync(string dealId, CancellationToken cancellationToken = default) =>
        GetRequiredAsync<RelistOffer>(Build("/relist", ("deal_id", dealId), ("setup", "1")), cancellationToken);

    public Task<RelistOffer> PreviewRelistAsync(string dealId, int listingPrice, bool premium, CancellationToken cancellationToken = default) =>
        GetRequiredAsync<RelistOffer>(Build("/relist", ("deal_id", dealId), ("listing_price", listingPrice.ToString()), ("priority_type", premium ? "PREMIUM" : "DEFAULT")), cancellationToken);

    public async Task<RelistOffer> ExecuteRelistAsync(string dealId, RelistOffer offer, CancellationToken cancellationToken = default)
    {
        var uri = Build("/relist", ("deal_id", dealId), ("priority_id", offer.PriorityId), ("priority_price", offer.PriorityPrice.ToString()), ("listing_price", offer.ItemPrice.ToString()), ("priority_type", offer.PriorityType));
        using var response = await _http.PostAsync(uri, new ByteArrayContent([]), cancellationToken);
        return await ReadRequiredAsync<RelistOffer>(response, cancellationToken);
    }

    public async Task TriggerTestNotificationAsync(CancellationToken cancellationToken = default) =>
        _ = await GetTextAsync(Build("/test"), cancellationToken);

    private Uri Build(string path, params (string Key, string Value)[] parameters)
    {
        var source = new Uri(PairingUrl);
        var query = ParseQuery(source.Query);
        foreach (var key in new[] { "after", "mode", "after_rev", "limit", "deal_id", "priority_id", "priority_price", "listing_price", "priority_type", "setup" }) query.Remove(key);
        foreach (var (key, value) in parameters) query[key] = value;
        var builder = new UriBuilder(source) { Path = path, Query = string.Join("&", query.Select(pair => $"{Uri.EscapeDataString(pair.Key)}={Uri.EscapeDataString(pair.Value)}")) };
        return builder.Uri;
    }

    private static Dictionary<string, string> ParseQuery(string query)
    {
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var part in query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var split = part.Split('=', 2);
            result[Uri.UnescapeDataString(split[0])] = split.Length > 1 ? Uri.UnescapeDataString(split[1]) : "";
        }
        return result;
    }

    private async Task<string> GetTextAsync(Uri uri, CancellationToken cancellationToken)
    {
        using var response = await _http.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        var text = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode) throw ApiException(response.StatusCode, text);
        return text;
    }

    private async Task<JsonDocument> GetJsonAsync(Uri uri, CancellationToken cancellationToken) => JsonDocument.Parse(await GetTextAsync(uri, cancellationToken));

    private async Task<T?> GetAsync<T>(Uri uri, CancellationToken cancellationToken) => JsonSerializer.Deserialize<T>(await GetTextAsync(uri, cancellationToken), Json);

    private async Task<T> GetRequiredAsync<T>(Uri uri, CancellationToken cancellationToken) =>
        await GetAsync<T>(uri, cancellationToken) ?? throw new InvalidOperationException("VPS вернул пустой ответ");

    private static async Task<T> ReadRequiredAsync<T>(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        var text = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode) throw ApiException(response.StatusCode, text);
        return JsonSerializer.Deserialize<T>(text, Json) ?? throw new InvalidOperationException("VPS вернул пустой ответ");
    }

    private static Exception ApiException(System.Net.HttpStatusCode code, string text)
    {
        try
        {
            using var document = JsonDocument.Parse(text);
            if (document.RootElement.TryGetProperty("message", out var message)) return new InvalidOperationException(message.GetString() ?? $"HTTP {(int)code}");
        }
        catch (JsonException) { }
        return new InvalidOperationException($"HTTP {(int)code}: {text.Trim()}");
    }

    public void Dispose() => _http.Dispose();
}
