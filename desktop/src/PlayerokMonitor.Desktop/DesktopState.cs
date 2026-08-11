using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.IO;
using PlayerokMonitor.Core;

namespace PlayerokMonitor.Desktop;

public sealed class DesktopState
{
    [JsonIgnore] public string PairingUrl { get; set; } = "";
    [JsonPropertyName("pairing_url_protected")] public string PairingUrlProtected { get; set; } = "";
    [JsonPropertyName("monitoring_enabled")] public bool MonitoringEnabled { get; set; } = true;
    [JsonPropertyName("notifications_enabled")] public bool NotificationsEnabled { get; set; } = true;
    [JsonPropertyName("start_with_windows")] public bool StartWithWindows { get; set; }
    [JsonPropertyName("close_to_tray")] public bool CloseToTray { get; set; } = true;
    [JsonPropertyName("orders_revision")] public long OrdersRevision { get; set; }
    [JsonPropertyName("event_cursor")] public long EventCursor { get; set; }
    [JsonPropertyName("event_source_fingerprint")] public string EventSourceFingerprint { get; set; } = "";
    [JsonPropertyName("orders")] public List<Order> Orders { get; set; } = [];
}

public sealed class DesktopStateStore
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { WriteIndented = true };
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly string _directory;
    private string FilePath => Path.Combine(_directory, "state.json");

    public DesktopStateStore(string? directory = null)
    {
        _directory = string.IsNullOrWhiteSpace(directory)
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PlayerokMonitor")
            : Path.GetFullPath(directory);
    }

    public async Task<DesktopState> LoadAsync()
    {
        await _gate.WaitAsync();
        try
        {
            if (!File.Exists(FilePath)) return new DesktopState();
            var state = JsonSerializer.Deserialize<DesktopState>(await File.ReadAllTextAsync(FilePath), Json) ?? new DesktopState();
            state.PairingUrl = Unprotect(state.PairingUrlProtected);
            return state;
        }
        catch (Exception)
        {
            return new DesktopState();
        }
        finally { _gate.Release(); }
    }

    public async Task SaveAsync(DesktopState state)
    {
        await _gate.WaitAsync();
        try
        {
            Directory.CreateDirectory(_directory);
            state.PairingUrlProtected = Protect(state.PairingUrl);
            var temporary = FilePath + ".tmp";
            await File.WriteAllTextAsync(temporary, JsonSerializer.Serialize(state, Json), new UTF8Encoding(false));
            File.Move(temporary, FilePath, true);
        }
        finally { _gate.Release(); }
    }

    public static string Fingerprint(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value.Trim())));

    private static string Protect(string value) => string.IsNullOrWhiteSpace(value)
        ? ""
        : Convert.ToBase64String(ProtectedData.Protect(Encoding.UTF8.GetBytes(value), null, DataProtectionScope.CurrentUser));

    private static string Unprotect(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "";
        try { return Encoding.UTF8.GetString(ProtectedData.Unprotect(Convert.FromBase64String(value), null, DataProtectionScope.CurrentUser)); }
        catch (CryptographicException) { return ""; }
    }
}
