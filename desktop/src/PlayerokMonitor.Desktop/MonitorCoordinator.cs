using PlayerokMonitor.Core;

namespace PlayerokMonitor.Desktop;

public sealed class MonitorCoordinator : IAsyncDisposable
{
    private readonly DesktopState _state;
    private readonly DesktopStateStore _store;
    private readonly SemaphoreSlim _syncGate = new(1, 1);
    private CancellationTokenSource? _cts;
    private Task? _loop;
    private PlayerokClient? _client;

    public event Action<IReadOnlyList<Order>>? OrdersChanged;
    public event Action<EventRecord>? EventReceived;
    public event Action<string, bool>? StatusChanged;
    public PlayerokClient? Client => _client;

    public MonitorCoordinator(DesktopState state, DesktopStateStore store)
    {
        _state = state;
        _store = store;
    }

    public async Task RestartAsync()
    {
        await StopAsync();
        if (!_state.MonitoringEnabled)
        {
            StatusChanged?.Invoke("Мониторинг выключен", false);
            return;
        }
        var validation = PlayerokClient.ValidatePairingUrl(_state.PairingUrl);
        if (validation is not null)
        {
            StatusChanged?.Invoke("Нужно подключить VPS", false);
            return;
        }
        _client = new PlayerokClient(_state.PairingUrl);
        _cts = new CancellationTokenSource();
        _loop = RunAsync(_cts.Token);
        await Task.Yield();
    }

    public async Task RefreshAsync(CancellationToken cancellationToken = default) => await SyncOrdersAsync(cancellationToken);

    private async Task RunAsync(CancellationToken cancellationToken)
    {
        var failures = 0;
        try
        {
            if (_client is null) return;
            var fingerprint = DesktopStateStore.Fingerprint(_state.PairingUrl);
            if (!_state.EventSourceFingerprint.Equals(fingerprint, StringComparison.Ordinal))
            {
                StatusChanged?.Invoke("Тихая первичная синхронизация…", true);
                _state.EventCursor = await _client.GetLatestEventIdAsync(cancellationToken);
                _state.EventSourceFingerprint = fingerprint;
                _state.OrdersRevision = 0;
                _state.Orders = [];
                await _store.SaveAsync(_state);
            }
            await SyncOrdersAsync(cancellationToken);
            StatusChanged?.Invoke("Подключено к VPS", true);
            while (!cancellationToken.IsCancellationRequested)
            {
                try
                {
                    var record = await _client.PollEventAsync(_state.EventCursor, cancellationToken);
                    failures = 0;
                    StatusChanged?.Invoke("Подключено к VPS", true);
                    if (record is null || record.Id <= _state.EventCursor) continue;
                    _state.EventCursor = record.Id;
                    await _store.SaveAsync(_state);
                    EventReceived?.Invoke(record);
                    await SyncOrdersAsync(cancellationToken);
                }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { break; }
                catch (Exception)
                {
                    failures++;
                    StatusChanged?.Invoke("Переподключение к VPS…", false);
                    await Task.Delay(TimeSpan.FromSeconds(Math.Min(15, Math.Max(1, failures))), cancellationToken);
                }
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { }
        catch (Exception error)
        {
            StatusChanged?.Invoke($"Нет связи: {error.Message}", false);
        }
    }

    private async Task SyncOrdersAsync(CancellationToken cancellationToken)
    {
        if (_client is null) return;
        if (!await _syncGate.WaitAsync(0, cancellationToken)) return;
        try
        {
            var response = await _client.GetOrdersAsync(_state.OrdersRevision, cancellationToken);
            if (!response.Unchanged)
            {
                _state.OrdersRevision = response.Revision;
                _state.Orders = response.Orders;
                await _store.SaveAsync(_state);
            }
            OrdersChanged?.Invoke(_state.Orders);
        }
        finally { _syncGate.Release(); }
    }

    private async Task StopAsync()
    {
        var cts = _cts;
        var loop = _loop;
        _cts = null;
        _loop = null;
        if (cts is not null) await cts.CancelAsync();
        if (loop is not null)
        {
            try { await loop; } catch (OperationCanceledException) { }
        }
        cts?.Dispose();
        _client?.Dispose();
        _client = null;
    }

    public async ValueTask DisposeAsync()
    {
        await StopAsync();
        _syncGate.Dispose();
    }
}
