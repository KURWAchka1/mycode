using PlayerokMonitor.Core;
using System.Net;

static void Assert(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

Assert(PlayerokClient.ValidatePairingUrl("https://example.com/poll?token=secret") is null, "valid pairing URL rejected");
Assert(PlayerokClient.ValidatePairingUrl("http://example.com/poll?token=secret") is not null, "http pairing URL accepted");
Assert(PlayerokClient.ValidatePairingUrl("https://example.com/health?token=secret") is not null, "wrong pairing path accepted");

using var plainHealthClient = new PlayerokClient("https://example.com/poll?token=secret", new StaticResponseHandler("OK\n"));
Assert(await plainHealthClient.CheckHealthAsync(), "plain-text health response rejected");
using var jsonHealthClient = new PlayerokClient("https://example.com/poll?token=secret", new StaticResponseHandler("{\"ok\":true}"));
Assert(await jsonHealthClient.CheckHealthAsync(), "JSON health response rejected");
using var invalidHealthClient = new PlayerokClient("https://example.com/poll?token=secret", new StaticResponseHandler("Offline"));
Assert(!await invalidHealthClient.CheckHealthAsync(), "invalid health response accepted");

var eventRecord = EventRecord.Parse("EVENT2\t42\tORDER_PAID\tdeal-1\tНовый заказ\tТовар оплачен");
Assert(eventRecord is { Id: 42, DealId: "deal-1" }, "EVENT2 parse failed");
Assert(EventRecord.Parse("NONE") is null, "NONE parse failed");

var now = new DateTimeOffset(2026, 8, 10, 12, 0, 0, TimeSpan.Zero);
var orders = new[]
{
    new Order { DealId = "sale-1", Direction = "OUT", Price = "100", SellerNetAmount = "90", PaidAt = "2026-08-10T10:00:00Z", SellerFulfilled = false },
    new Order { DealId = "sale-2", Direction = "OUT", Price = "200", SellerNetAmount = "180", PaidAt = "2026-08-09T10:00:00Z", SellerFulfilled = true, RecipientConfirmed = true },
    new Order { DealId = "refund", Direction = "OUT", Price = "300", SellerNetAmount = "270", PaidAt = "2026-08-08T10:00:00Z", RolledBack = true },
    new Order { DealId = "buy", Direction = "IN", Price = "50", PaidAt = "2026-08-10T09:00:00Z" }
};
var stats = StatisticsEngine.Calculate(orders, now);
Assert(stats.Sales == 3 && stats.Purchases == 1, "direction totals failed");
Assert(stats.NetRevenue == 270 && stats.NewOrders == 1, "net/new totals failed");
Assert(stats.Returns == 1 && Math.Abs(stats.CompletionRate - 50d) < .01d, "terminal totals failed");
Assert(stats.Daily.Sum(point => point.NetRevenue) == 270, "daily aggregation failed");

var actorOrder = new Order { Direction = "OUT" };
Assert(actorOrder.Actor("seller", "SELLER", "SELF") == "Вы", "self actor failed");
Assert(actorOrder.Actor("buyer", "BUYER", "COUNTERPARTY") == "@buyer", "counterparty actor failed");

var reviewedOrder = new Order { ReviewRating = 4, ReviewText = "Всё хорошо" };
Assert(reviewedOrder.HasReview, "review presence failed");
Assert(reviewedOrder.ReviewStars == "★★★★☆", "review stars failed");
Assert(!new Order().HasReview && new Order().ReviewStars == "", "empty review failed");

Console.WriteLine("PlayerokMonitor.Core.Tests: 18 assertions passed");

sealed class StaticResponseHandler(string content) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
        Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(content) });
}
