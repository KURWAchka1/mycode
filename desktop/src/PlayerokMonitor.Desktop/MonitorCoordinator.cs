using PlayerokMonitor.Core;

namespace PlayerokMonitor.Desktop;

public sealed class MonitorCoordinator : IAsyncDisposable
{
    private readonly DesktopState _state;
    private readonly DesktopStateStore _store;
    private readonly Func<string, PlayerokClient> _clientFactory;
    private readonly SemaphoreSlim _syncGate = new(1, 1);
    private CancellationTokenSource? _cts;
    private Task? _loop;
    private PlayerokClient? _client;
    private int _disposeStarted;

    public event Action<IReadOnlyList<Order>>? OrdersChanged;
    public event Action<EventRecord>? EventReceived;
    public event Action<string, bool>? StatusChanged;
    public PlayerokClient? Client => _client;

    public MonitorCoordinator(DesktopState state, DesktopStateStore store, Func<string, PlayerokClient>? clientFactory = null)
    {
        _state = state;
        _store = store;
        _clientFactory = clientFactory ?? (pairingUrl => new PlayerokClient(pairingUrl));
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
        _client = _clientFactory(_state.PairingUrl);
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
            var client = _client;
            if (client is null) return;
            await MoveToLiveEventHeadAsync(client, cancellationToken);
            await SyncOrdersAsync(cancellationToken);
            StatusChanged?.Invoke("Подключено к VPS", true);
            var reconnecting = false;
            while (!cancellationToken.IsCancellationRequested)
            {
                try
                {
                    if (reconnecting)
                    {
                        await MoveToLiveEventHeadAsync(client, cancellationToken);
                        await SyncOrdersAsync(cancellationToken);
                        reconnecting = false;
                    }
                    var record = await client.PollEventAsync(_state.EventCursor, cancellationToken);
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
                    reconnecting = true;
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

    private async Task MoveToLiveEventHeadAsync(PlayerokClient client, CancellationToken cancellationToken)
    {
        var fingerprint = DesktopStateStore.Fingerprint(_state.PairingUrl);
        var sourceChanged = !_state.EventSourceFingerprint.Equals(fingerprint, StringComparison.Ordinal);
        var latestEventId = await client.GetLatestEventIdAsync(cancellationToken);
        if (!sourceChanged && _state.EventCursor == latestEventId) return;

        StatusChanged?.Invoke("Тихая синхронизация без старых уведомлений…", true);
        _state.EventCursor = latestEventId;
        _state.EventSourceFingerprint = fingerprint;
        if (sourceChanged)
        {
            _state.OrdersRevision = 0;
            _state.Orders = [];
        }
        await _store.SaveAsync(_state);
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
        var client = _client;
        _cts = null;
        _loop = null;
        _client = null;
        cts?.Cancel();
        client?.Dispose();
        if (loop is not null)
        {
            try { await loop.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false); }
            catch (OperationCanceledException) when (cts?.IsCancellationRequested == true) { }
            catch (ObjectDisposedException) when (cts?.IsCancellationRequested == true) { }
            catch (TimeoutException) { }
        }
        cts?.Dispose();
    }

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref _disposeStarted, 1) != 0) return;
        await StopAsync().ConfigureAwait(false);
        _syncGate.Dispose();
    }
}
