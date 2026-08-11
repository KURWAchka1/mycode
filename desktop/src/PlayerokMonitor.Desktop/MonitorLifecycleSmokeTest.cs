using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using PlayerokMonitor.Core;

namespace PlayerokMonitor.Desktop;

internal static class MonitorLifecycleSmokeTest
{
    public static async Task RunAsync()
    {
        var testDirectory = Path.Combine(Path.GetTempPath(), $"PlayerokMonitorLifecycle-{Guid.NewGuid():N}");
        Directory.CreateDirectory(testDirectory);
        try
        {
            const string pairingUrl = "https://example.com/poll?token=lifecycle-test";
            var state = new DesktopState
            {
                PairingUrl = pairingUrl,
                MonitoringEnabled = true,
                EventCursor = 1,
                EventSourceFingerprint = DesktopStateStore.Fingerprint(pairingUrl)
            };
            var handler = new LifecycleHandler();
            var coordinator = new MonitorCoordinator(
                state,
                new DesktopStateStore(testDirectory),
                url => new PlayerokClient(url, handler));
            var receivedEvents = 0;
            coordinator.EventReceived += _ => receivedEvents++;

            await coordinator.RestartAsync();
            await handler.PollStarted.Task.WaitAsync(TimeSpan.FromSeconds(3));
            if (state.EventCursor != 5) throw new InvalidDataException("Offline event cursor was not moved to the live head");
            if (handler.PollAfter != 5) throw new InvalidDataException("Polling restarted before the current live head");
            if (receivedEvents != 0) throw new InvalidDataException("Offline events were replayed as notifications");

            var stopwatch = Stopwatch.StartNew();
            await coordinator.DisposeAsync();
            stopwatch.Stop();
            if (stopwatch.Elapsed > TimeSpan.FromSeconds(2)) throw new InvalidDataException("Monitor shutdown blocked on long-poll");
        }
        finally
        {
            if (Directory.Exists(testDirectory)) Directory.Delete(testDirectory, true);
        }
    }

    private sealed class LifecycleHandler : HttpMessageHandler
    {
        public TaskCompletionSource PollStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public long PollAfter { get; private set; } = -1;

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var uri = request.RequestUri ?? throw new InvalidDataException("Request URI is missing");
            if (uri.AbsolutePath == "/cursor") return Json("{\"latest_event_id\":5}");

            var query = ParseQuery(uri.Query);
            if (uri.AbsolutePath == "/poll" && query.GetValueOrDefault("mode") == "orders")
                return Json("{\"revision\":2,\"unchanged\":false,\"orders\":[]}");

            if (uri.AbsolutePath == "/poll" && query.GetValueOrDefault("mode") == "eventsv2")
            {
                PollAfter = long.TryParse(query.GetValueOrDefault("after"), out var after) ? after : -1;
                PollStarted.TrySetResult();
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            }

            return new HttpResponseMessage(HttpStatusCode.NotFound);
        }

        private static HttpResponseMessage Json(string content) => new(HttpStatusCode.OK)
        {
            Content = new StringContent(content, Encoding.UTF8, "application/json")
        };

        private static Dictionary<string, string> ParseQuery(string query) => query
            .TrimStart('?')
            .Split('&', StringSplitOptions.RemoveEmptyEntries)
            .Select(part => part.Split('=', 2))
            .ToDictionary(
                part => Uri.UnescapeDataString(part[0]),
                part => part.Length > 1 ? Uri.UnescapeDataString(part[1]) : "",
                StringComparer.Ordinal);
    }
}
