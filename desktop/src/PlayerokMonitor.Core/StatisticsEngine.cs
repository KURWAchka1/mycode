namespace PlayerokMonitor.Core;

public sealed record DailyStatistic(DateOnly Day, int Sales, decimal NetRevenue);

public sealed record StatisticsSnapshot(
    int Sales,
    int Purchases,
    int NewOrders,
    int Problems,
    int Returns,
    decimal GrossRevenue,
    decimal NetRevenue,
    decimal AverageSale,
    double CompletionRate,
    IReadOnlyList<DailyStatistic> Daily);

public static class StatisticsEngine
{
    public static StatisticsSnapshot Calculate(IEnumerable<Order> source, DateTimeOffset? now = null, int days = 14)
    {
        var orders = source.ToList();
        var sales = orders.Where(order => order.IsSale).ToList();
        var current = (now ?? DateTimeOffset.Now).ToLocalTime();
        var firstDay = DateOnly.FromDateTime(current.Date.AddDays(-(Math.Max(1, days) - 1)));
        var daily = Enumerable.Range(0, Math.Max(1, days))
            .Select(index => new DailyStatistic(firstDay.AddDays(index), 0, 0m))
            .ToDictionary(point => point.Day);

        foreach (var sale in sales.Where(order => !order.RolledBack))
        {
            var paid = sale.PaidAtValue?.ToLocalTime();
            if (paid is null) continue;
            var day = DateOnly.FromDateTime(paid.Value.Date);
            if (!daily.TryGetValue(day, out var point)) continue;
            var net = Order.ParseMoney(sale.SellerNetAmount) ?? Order.ParseMoney(sale.Price) ?? 0m;
            daily[day] = point with { Sales = point.Sales + 1, NetRevenue = point.NetRevenue + net };
        }

        var completed = sales.Count(order => order.RecipientConfirmed && !order.RolledBack);
        var terminal = sales.Count(order => order.RecipientConfirmed || order.RolledBack);
        var gross = sales.Where(order => !order.RolledBack).Sum(order => Order.ParseMoney(order.Price) ?? 0m);
        var netRevenue = sales.Where(order => !order.RolledBack).Sum(order => Order.ParseMoney(order.SellerNetAmount) ?? Order.ParseMoney(order.Price) ?? 0m);
        var effectiveSales = sales.Count(order => !order.RolledBack);
        return new StatisticsSnapshot(
            sales.Count,
            orders.Count(order => order.IsPurchase),
            sales.Count(order => order.IsNew),
            orders.Count(order => order.ProblemActive),
            orders.Count(order => order.RolledBack),
            gross,
            netRevenue,
            effectiveSales == 0 ? 0m : netRevenue / effectiveSales,
            terminal == 0 ? 0d : completed * 100d / terminal,
            daily.Values.OrderBy(point => point.Day).ToList());
    }
}
