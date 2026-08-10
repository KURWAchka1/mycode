using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Shapes;
using PlayerokMonitor.Core;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
using Button = System.Windows.Controls.Button;
using Color = System.Windows.Media.Color;
using KeyEventArgs = System.Windows.Input.KeyEventArgs;
using MessageBox = System.Windows.MessageBox;
using EmojiRichTextBox = Emoji.Wpf.RichTextBox;
using EmojiTextBlock = Emoji.Wpf.TextBlock;

namespace PlayerokMonitor.Desktop;

public partial class MainWindow : Window
{
    private readonly DesktopStateStore _store = new();
    private readonly WindowsNotifier _notifier = new();
    private readonly ObservableCollection<Order> _visibleOrders = [];
    private readonly List<EmojiRichTextBox> _messageBoxes = [];
    private DesktopState _state = new();
    private MonitorCoordinator? _monitor;
    private TrayService? _tray;
    private DesktopUpdateService.UpdateInfo? _pendingUpdate;
    private List<Order> _allOrders = [];
    private string _filter = "new";
    private string _section = "orders";
    private bool _connected;
    private bool _exiting;
    private AutoReplySettings? _replySettings;
    private readonly bool _previewMode;
    private readonly List<CommandEntry> _commands =
    [
        new("new", "Новые заказы", "Открыть очередь невыполненных заказов", "Ctrl+1"),
        new("sales", "Продажи", "Показать все продажи", ""),
        new("purchases", "Покупки", "Показать покупки", ""),
        new("stats", "Статистика", "Открыть локальную статистику за 14 дней", "Ctrl+2"),
        new("settings", "Настройки", "Подключение, Windows и автосообщения", "Ctrl+,"),
        new("refresh", "Обновить заказы", "Запросить актуальный снимок вручную", "F5")
    ];

    public MainWindow(bool previewMode = false)
    {
        _previewMode = previewMode;
        InitializeComponent();
        OrdersList.ItemsSource = _visibleOrders;
        CommandList.ItemsSource = _commands;
        if (!previewMode) Loaded += MainWindow_Loaded;
        Closing += MainWindow_Closing;
        StateChanged += (_, _) => UpdateMaximizeGlyph();
        ConfigureTimeZones();
        ApplyAdaptiveLayout(Width);
    }

    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        _state = await _store.LoadAsync();
        PairingUrlBox.Text = _state.PairingUrl;
        MonitoringCheck.IsChecked = _state.MonitoringEnabled;
        NotificationsCheck.IsChecked = _state.NotificationsEnabled;
        AutoStartCheck.IsChecked = _state.StartWithWindows;
        CloseToTrayCheck.IsChecked = _state.CloseToTray;
        _allOrders = _state.Orders;
        _notifier.Register();
        _tray = new TrayService();
        _tray.OpenRequested += ShowFromTray;
        _tray.RefreshRequested += () => Dispatcher.Invoke(async () => await RefreshOrdersAsync());
        _tray.ExitRequested += () => Dispatcher.Invoke(ExitApplication);
        _monitor = new MonitorCoordinator(_state, _store);
        _monitor.OrdersChanged += orders => Dispatcher.Invoke(() => ApplyOrders(orders));
        _monitor.EventReceived += record => Dispatcher.Invoke(() => OnEvent(record));
        _monitor.StatusChanged += (text, online) => Dispatcher.Invoke(() => SetConnectionStatus(text, online));
        SelectSection("orders");
        SelectFilter("new");
        ApplyOrders(_allOrders);
        await _monitor.RestartAsync();
        _ = CheckForUpdatesAsync();
    }

    private void OnEvent(EventRecord record)
    {
        if (_state.NotificationsEnabled) _notifier.Show(record.Title, record.Body, record.DealId);
        if (!IsVisible) _tray?.Update(_allOrders.Count(order => order.IsNew), _connected);
    }

    private void ApplyOrders(IReadOnlyList<Order> orders)
    {
        var selectedId = (OrdersList.SelectedItem as Order)?.DealId;
        _allOrders = orders.OrderByDescending(order => order.PaidAtValue ?? DateTimeOffset.MinValue).ToList();
        ApplyFilter();
        RenderStatistics();
        UpdatePageHeader();
        _tray?.Update(_allOrders.Count(order => order.IsNew), _connected);
        if (!string.IsNullOrWhiteSpace(selectedId)) OrdersList.SelectedItem = _visibleOrders.FirstOrDefault(order => order.DealId == selectedId);
    }

    internal void LoadPreviewData(string section)
    {
        var now = DateTimeOffset.Now;
        ApplyOrders([
            new Order { DealId = "preview-new", Direction = "OUT", ItemName = "🎮 100 BC в дни x2 · без привязки", Price = "249", SellerNetAmount = "224", SellerNetStatus = "PROCESSING", Counterparty = "galaxy_buyer", PaidAt = now.AddMinutes(-8).ToString("O"), ReplyMode = "SLEEP", SleepReplySent = true, WakeReplyAvailable = true },
            new Order { DealId = "preview-sale", Direction = "OUT", ItemName = "⚡ Игровая валюта · быстрая выдача", Price = "590", SellerNetAmount = "531", SellerNetStatus = "CONFIRMED", Counterparty = "buyer_ok", PaidAt = now.AddDays(-1).ToString("O"), SellerFulfilled = true, RecipientConfirmed = true },
            new Order { DealId = "preview-buy", Direction = "IN", ItemName = "✨ Подписка на месяц", Price = "399", Counterparty = "seller_pro", PaidAt = now.AddDays(-2).ToString("O"), SellerFulfilled = true }
        ]);
        SelectFilter("new");
        if (section.Equals("settings", StringComparison.OrdinalIgnoreCase) || section.Equals("sleep", StringComparison.OrdinalIgnoreCase))
        {
            SleepStartBox.SelectedItem = "00:00";
            SleepEndBox.SelectedItem = "08:00";
            SleepTimezoneBox.SelectedItem = "Europe/Moscow";
            FulfillmentMessageBox.Text = "✅ Заказ выполнен. Подтвердите получение, пожалуйста.";
            SleepMessageBox.Text = "🌙 Возможно, продавец сейчас спит. Ответит после пробуждения.";
            if (_messageBoxes.Count == 0) AddMessageRow("Спасибо за заказ! 🎉 Ожидайте сообщение продавца.");
        }
        if (section.Equals("command", StringComparison.OrdinalIgnoreCase))
        {
            SelectSection("orders");
            OpenCommandPalette();
        }
        else if (section.Equals("sleep", StringComparison.OrdinalIgnoreCase))
        {
            SelectSection("settings");
            Dispatcher.BeginInvoke(() => SettingsView.ScrollToVerticalOffset(640), System.Windows.Threading.DispatcherPriority.Loaded);
        }
        else SelectSection(section);
    }

    private void ApplyFilter()
    {
        var search = SearchBox.Text.Trim();
        IEnumerable<Order> values = _filter switch
        {
            "new" => _allOrders.Where(order => order.IsNew),
            "sales" => _allOrders.Where(order => order.IsSale),
            "purchases" => _allOrders.Where(order => order.IsPurchase),
            _ => _allOrders
        };
        if (!string.IsNullOrWhiteSpace(search))
        {
            values = values.Where(order => order.DisplayName.Contains(search, StringComparison.CurrentCultureIgnoreCase)
                || order.CounterpartyDisplay.Contains(search, StringComparison.CurrentCultureIgnoreCase)
                || order.DealId.Contains(search, StringComparison.OrdinalIgnoreCase));
        }
        _visibleOrders.Clear();
        foreach (var order in values) _visibleOrders.Add(order);
        EmptyOrders.Visibility = _visibleOrders.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
        OrdersList.Visibility = _visibleOrders.Count == 0 ? Visibility.Collapsed : Visibility.Visible;
        EmptyOrdersText.Text = _filter == "new" && string.IsNullOrWhiteSpace(search) ? "Новых заказов нет" : "Ничего не найдено";
        if (_visibleOrders.Count > 0 && OrdersList.SelectedItem is null) OrdersList.SelectedIndex = 0;
        if (_visibleOrders.Count == 0) RenderOrder(null);
    }

    private void RenderStatistics()
    {
        var snapshot = StatisticsEngine.Calculate(_allOrders);
        StatNet.Text = $"{snapshot.NetRevenue:N0} ₽";
        StatSales.Text = snapshot.Sales.ToString(CultureInfo.InvariantCulture);
        StatAverage.Text = $"{snapshot.AverageSale:N0} ₽";
        StatCompletion.Text = $"{snapshot.CompletionRate:N0}%";
        StatNew.Text = snapshot.NewOrders.ToString(CultureInfo.InvariantCulture);
        StatProblems.Text = snapshot.Problems.ToString(CultureInfo.InvariantCulture);
        StatReturns.Text = snapshot.Returns.ToString(CultureInfo.InvariantCulture);
        StatPurchases.Text = snapshot.Purchases.ToString(CultureInfo.InvariantCulture);
        RevenueChart.SetData(snapshot.Daily);
    }

    private void RenderOrder(Order? order)
    {
        NoSelection.Visibility = order is null ? Visibility.Visible : Visibility.Collapsed;
        OrderDetails.Visibility = order is null ? Visibility.Collapsed : Visibility.Visible;
        if (order is null) return;
        DetailDirection.Text = order.DirectionLabel.ToUpperInvariant();
        DetailTitle.Text = order.DisplayName;
        DetailPrice.Text = order.IsSale && !string.IsNullOrWhiteSpace(order.SellerNetAmount)
            ? $"{order.PriceDisplay}  ·  вам {order.NetDisplay}"
            : order.PriceDisplay;
        var dealUrl = string.IsNullOrWhiteSpace(order.DealUrl) ? $"https://playerok.com/deal/{order.DealId}" : order.DealUrl;
        OpenDealButton.Tag = dealUrl;
        WakeButton.Visibility = order.WakeReplyAvailable ? Visibility.Visible : Visibility.Collapsed;
        WakeButton.Content = order.WakeReplyRequested ? "Повторить отправку" : "Я проснулся";
        var canRelist = order.IsSale && order.RelistEligible && !order.RolledBack && !order.ProblemActive && order.SellerFulfilled && !order.IsRelisted && !order.RelistState.Equals("PUBLISHING", StringComparison.OrdinalIgnoreCase);
        RelistButton.Visibility = canRelist ? Visibility.Visible : Visibility.Collapsed;
        DetailFields.Children.Clear();
        AddField("Заказ", order.DealId);
        AddField(order.IsSale ? "Покупатель" : "Продавец", string.IsNullOrWhiteSpace(order.CounterpartyDisplay) ? "—" : $"@{order.CounterpartyDisplay.TrimStart('@')}");
        AddField("Оплачен", order.PaidAtDisplay);
        AddStatusCard(order.SellerFulfilled ? "Выполнение подтверждено" : "Выполнение не подтверждено", order.IsSale ? (order.SellerFulfilled ? "Вами" : "Нужно выполнить заказ на Playerok") : (order.SellerFulfilled ? $"Продавцом · {order.Actor(order.SellerFulfilledByName, order.SellerFulfilledByRole, order.SellerFulfilledByRelation)}" : "Продавец ещё не подтвердил выполнение"), order.SellerFulfilled ? "green" : "amber");
        AddStatusCard(order.RecipientConfirmed ? "Получение подтверждено" : "Получение не подтверждено", ReceiptDescription(order), order.RecipientConfirmed ? "green" : "neutral");
        if (order.ProblemActive || !string.IsNullOrWhiteSpace(order.ProblemReportedAt))
        {
            var reporter = order.Actor(order.ProblemReportedByName, order.ProblemReportedByRole, order.ProblemReportedByRelation);
            var description = order.ProblemActive ? $"Создал: {reporter}" : $"Создал: {reporter}. Решена: {order.Actor(order.ProblemResolvedByName, order.ProblemResolvedByRole, order.ProblemResolvedByRelation)}";
            AddStatusCard(order.ProblemActive ? "Активная проблема" : "Проблема решена", description, order.ProblemActive ? "red" : "green");
        }
        if (order.RolledBack) AddStatusCard("Оформлен возврат", $"Кем: {order.Actor(order.RolledBackByName, order.RolledBackByRole, order.RolledBackByRelation)}", "red");
        if (order.SleepReplySent) AddStatusCard(order.WakeReplySent ? "Сообщение после пробуждения отправлено" : "Покупатель предупреждён о сне", order.WakeReplyAvailable ? "Можно нажать «Я проснулся» — обычное сообщение отправится один раз." : "Обычная цепочка сообщений уже обработана.", order.WakeReplyAvailable ? "blue" : "green");
        if (order.IsRelisted) AddStatusCard("Товар выставлен снова", $"Цена: {order.RelistListingPrice:N0} ₽ · размещение: {(order.RelistPriorityPrice <= 0 ? "бесплатно" : $"{order.RelistPriorityPrice:N0} ₽")}", "green");
        if (!string.IsNullOrWhiteSpace(order.BuyerComment)) AddStatusCard("Комментарий покупателя", order.BuyerComment, "neutral");
    }

    private string ReceiptDescription(Order order)
    {
        if (!order.RecipientConfirmed) return order.IsSale ? "Покупатель ещё не подтвердил получение" : "Вы ещё не подтвердили получение";
        if (order.RecipientConfirmationAutomatic) return "Playerok подтвердил получение автоматически";
        return order.IsSale ? "Покупатель подтвердил получение" : "Получение подтверждено вами";
    }

    private void AddField(string label, string value)
    {
        var grid = new Grid { Margin = new Thickness(0, 8, 0, 0) };
        grid.ColumnDefinitions.Add(new ColumnDefinition());
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.Children.Add(new TextBlock { Text = label, Foreground = (Brush)FindResource("MutedBrush"), FontSize = 12 });
        var text = new EmojiTextBlock { Text = value, FontSize = 12, FontWeight = FontWeights.SemiBold, TextAlignment = TextAlignment.Right, MaxWidth = 310, TextWrapping = TextWrapping.Wrap };
        Grid.SetColumn(text, 1);
        grid.Children.Add(text);
        DetailFields.Children.Add(grid);
    }

    private void AddStatusCard(string title, string description, string tone)
    {
        var colors = tone switch
        {
            "green" => Color.FromRgb(88, 214, 141),
            "red" => Color.FromRgb(242, 123, 133),
            "amber" => Color.FromRgb(232, 185, 95),
            "blue" => Color.FromRgb(114, 169, 249),
            _ => Color.FromRgb(164, 171, 182)
        };
        var grid = new Grid();
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(12) });
        grid.ColumnDefinitions.Add(new ColumnDefinition());
        grid.Children.Add(new Ellipse { Width = 7, Height = 7, Fill = new SolidColorBrush(colors), HorizontalAlignment = System.Windows.HorizontalAlignment.Left, VerticalAlignment = System.Windows.VerticalAlignment.Top, Margin = new Thickness(0, 5, 0, 0) });
        var stack = new StackPanel();
        stack.Children.Add(new EmojiTextBlock { Text = title, FontWeight = FontWeights.SemiBold, FontSize = 12, Foreground = new SolidColorBrush(colors) });
        stack.Children.Add(new EmojiTextBlock { Text = description, TextWrapping = TextWrapping.Wrap, Foreground = (Brush)FindResource("MutedBrush"), FontSize = 11, Margin = new Thickness(0, 3, 0, 0) });
        Grid.SetColumn(stack, 1);
        grid.Children.Add(stack);
        DetailFields.Children.Add(new Border { BorderBrush = (Brush)FindResource("DividerBrush"), BorderThickness = new Thickness(0, 1, 0, 0), Padding = new Thickness(0, 10, 0, 0), Margin = new Thickness(0, 10, 0, 0), Child = grid });
    }

    private void SetConnectionStatus(string text, bool online)
    {
        _connected = online;
        ConnectionText.Text = text;
        ConnectionDot.Fill = (Brush)FindResource(online ? "GreenBrush" : "AmberBrush");
        ConnectionPill.Background = new SolidColorBrush(online ? Color.FromArgb(28, 88, 214, 141) : Color.FromArgb(28, 232, 185, 95));
        ConnectionPill.ToolTip = text;
        _tray?.Update(_allOrders.Count(order => order.IsNew), online);
    }

    private void SelectSection(string section)
    {
        _section = section;
        OrdersView.Visibility = section == "orders" ? Visibility.Visible : Visibility.Collapsed;
        StatsView.Visibility = section == "stats" ? Visibility.Visible : Visibility.Collapsed;
        SettingsView.Visibility = section == "settings" ? Visibility.Visible : Visibility.Collapsed;
        foreach (var button in new[] { OrdersNav, StatsNav, SettingsNav })
        {
            button.Background = Brushes.Transparent;
            button.Foreground = (Brush)FindResource("MutedBrush");
        }
        var selected = section switch { "stats" => StatsNav, "settings" => SettingsNav, _ => OrdersNav };
        selected.Background = (Brush)FindResource("AccentSoftBrush");
        selected.Foreground = (Brush)FindResource("AccentBrush");
        UpdatePageHeader();
        if (section == "settings" && _replySettings is null) _ = LoadRepliesAsync();
        if (section == "stats") RenderStatistics();
    }

    private void SelectFilter(string filter)
    {
        _filter = filter;
        foreach (var button in new[] { NewTab, SalesTab, PurchasesTab, AllTab })
        {
            button.Background = Brushes.Transparent;
            button.Foreground = (Brush)FindResource("MutedBrush");
        }
        var selected = filter switch { "sales" => SalesTab, "purchases" => PurchasesTab, "all" => AllTab, _ => NewTab };
        selected.Background = (Brush)FindResource("AccentSoftBrush");
        selected.Foreground = (Brush)FindResource("TextBrush");
        ApplyFilter();
    }

    private async Task RefreshOrdersAsync()
    {
        if (_monitor is null) return;
        RefreshButton.IsEnabled = false;
        try { await _monitor.RefreshAsync(); }
        catch (Exception error) { ShowError("Не удалось обновить", error.Message); }
        finally { RefreshButton.IsEnabled = true; }
    }

    private async Task LoadRepliesAsync()
    {
        if (_monitor?.Client is null) { RepliesStatus.Text = "Сначала подключите VPS"; return; }
        RepliesStatus.Text = "Загрузка…";
        try
        {
            _replySettings = await _monitor.Client.GetAutoRepliesAsync();
            DisableRepliesCheck.IsChecked = !_replySettings.Enabled;
            FulfillmentMessageBox.Text = _replySettings.FulfillmentMessage;
            FulfillmentHint.Text = $"По умолчанию: {_replySettings.DefaultFulfillmentMessage}";
            SleepEnabledCheck.IsChecked = _replySettings.SleepEnabled;
            SleepStartBox.Text = _replySettings.SleepStart;
            SleepEndBox.Text = _replySettings.SleepEnd;
            SleepTimezoneBox.Text = _replySettings.SleepTimezone;
            SleepMessageBox.Text = _replySettings.SleepMessage;
            SleepHint.Text = $"По умолчанию: {_replySettings.DefaultSleepMessage}";
            _messageBoxes.Clear();
            MessagesPanel.Children.Clear();
            IEnumerable<string> messages = _replySettings.Messages.Count == 0 ? new[] { "" } : _replySettings.Messages;
            foreach (var message in messages) AddMessageRow(message);
            RepliesStatus.Text = "Настройки загружены";
        }
        catch (Exception error) { RepliesStatus.Text = error.Message; }
    }

    private void AddMessageRow(string text)
    {
        if (_messageBoxes.Count >= 8) return;
        var grid = new Grid { Margin = new Thickness(0, 0, 0, 8) };
        grid.ColumnDefinitions.Add(new ColumnDefinition());
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var box = new EmojiRichTextBox { Text = text, AcceptsReturn = true, MinHeight = 58 };
        var remove = new Button
        {
            Content = new TextBlock { Text = "\uE74D", FontSize = 16, Style = (Style)FindResource("FluentIcon") },
            Width = 36,
            Height = 36,
            Padding = new Thickness(0),
            Margin = new Thickness(8, 0, 0, 0),
            ToolTip = "Удалить сообщение",
            Style = (Style)FindResource("IconButton")
        };
        remove.Click += (_, _) => { _messageBoxes.Remove(box); MessagesPanel.Children.Remove(grid); if (_messageBoxes.Count == 0) AddMessageRow(""); };
        grid.Children.Add(box);
        Grid.SetColumn(remove, 1);
        grid.Children.Add(remove);
        MessagesPanel.Children.Add(grid);
        _messageBoxes.Add(box);
        if (_replySettings is not null && _messageBoxes.Count == 1)
        {
            grid.ToolTip = $"Если оставить пустым, сервер применит: {_replySettings.DefaultMessage}";
        }
    }

    private async Task SaveRepliesAsync()
    {
        if (_monitor?.Client is null) { RepliesStatus.Text = "Сначала подключите VPS"; return; }
        var start = SleepStartBox.Text.Trim();
        var end = SleepEndBox.Text.Trim();
        if (!TimeOnly.TryParseExact(start, "HH:mm", CultureInfo.InvariantCulture, DateTimeStyles.None, out _) || !TimeOnly.TryParseExact(end, "HH:mm", CultureInfo.InvariantCulture, DateTimeStyles.None, out _))
        {
            RepliesStatus.Text = "Время нужно указать в формате ЧЧ:ММ";
            return;
        }
        if (start == end && SleepEnabledCheck.IsChecked == true)
        {
            RepliesStatus.Text = "Начало и конец сна не должны совпадать";
            return;
        }
        var request = new AutoReplyRequest
        {
            Enabled = DisableRepliesCheck.IsChecked != true,
            Messages = _messageBoxes.Select(box => box.Text.Trim()).Where(text => !string.IsNullOrWhiteSpace(text)).Take(8).ToList(),
            FulfillmentMessage = FulfillmentMessageBox.Text.Trim(),
            SleepEnabled = SleepEnabledCheck.IsChecked == true,
            SleepStart = start,
            SleepEnd = end,
            SleepTimezone = SleepTimezoneBox.Text.Trim(),
            SleepMessage = SleepMessageBox.Text.Trim()
        };
        RepliesStatus.Text = "Сохранение…";
        try { _replySettings = await _monitor.Client.SaveAutoRepliesAsync(request); RepliesStatus.Text = "Сохранено на VPS · Android увидит те же настройки"; }
        catch (Exception error) { RepliesStatus.Text = error.Message; }
    }

    private void ConfigureTimeZones()
    {
        var times = Enumerable.Range(0, 96).Select(value => $"{value / 4:00}:{value % 4 * 15:00}").ToList();
        SleepStartBox.ItemsSource = times;
        SleepEndBox.ItemsSource = times;
        SleepTimezoneBox.ItemsSource = new[] { "Europe/Moscow", "Europe/Kaliningrad", "Europe/Samara", "Asia/Yekaterinburg", "Asia/Omsk", "Asia/Krasnoyarsk", "Asia/Irkutsk", "Asia/Yakutsk", "Asia/Vladivostok", "Asia/Magadan", "Asia/Kamchatka" };
    }

    private async Task CheckForUpdatesAsync()
    {
        await Task.Delay(2500);
        try
        {
            _pendingUpdate = await new DesktopUpdateService().CheckAsync();
            if (_pendingUpdate is null) return;
            await Dispatcher.InvokeAsync(() => { UpdateText.Text = $"Доступна версия {_pendingUpdate.Version}"; UpdateBanner.Visibility = Visibility.Visible; });
        }
        catch { }
    }

    private async void SaveConnectionButton_Click(object sender, RoutedEventArgs e)
    {
        var value = PairingUrlBox.Text.Trim();
        var validation = PlayerokClient.ValidatePairingUrl(value);
        if (validation is not null) { ShowError("Не удалось подключить", validation); return; }
        try
        {
            using var client = new PlayerokClient(value);
            if (!await client.CheckHealthAsync()) throw new InvalidOperationException("VPS не подтвердил готовность");
            _state.PairingUrl = value;
            _state.EventSourceFingerprint = "";
            await _store.SaveAsync(_state);
            if (_monitor is not null) await _monitor.RestartAsync();
            SetConnectionStatus("Подключено к VPS", true);
        }
        catch (Exception error) { ShowError("Не удалось подключить", error.Message); }
    }

    private async void SaveWindowsSettingsButton_Click(object sender, RoutedEventArgs e)
    {
        _state.MonitoringEnabled = MonitoringCheck.IsChecked == true;
        _state.NotificationsEnabled = NotificationsCheck.IsChecked == true;
        _state.StartWithWindows = AutoStartCheck.IsChecked == true;
        _state.CloseToTray = CloseToTrayCheck.IsChecked == true;
        try { AutoStartManager.SetEnabled(_state.StartWithWindows); await _store.SaveAsync(_state); if (_monitor is not null) await _monitor.RestartAsync(); }
        catch (Exception error) { ShowError("Не удалось сохранить", error.Message); }
    }

    private async void TestNotificationButton_Click(object sender, RoutedEventArgs e)
    {
        if (_monitor?.Client is null) { ShowError("Нет подключения", "Сначала сохраните Pairing URL"); return; }
        try { await _monitor.Client.TriggerTestNotificationAsync(); }
        catch (Exception error) { ShowError("Не удалось отправить тест", error.Message); }
    }

    private async void WakeButton_Click(object sender, RoutedEventArgs e)
    {
        if (OrdersList.SelectedItem is not Order order || _monitor?.Client is null) return;
        if (MessageBox.Show(this, "Покупателю отправятся обычные сообщения «После оплаты». Сервер не создаст дубль при повторном нажатии.", "Сообщить о пробуждении?", MessageBoxButton.OKCancel, MessageBoxImage.Question) != MessageBoxResult.OK) return;
        WakeButton.IsEnabled = false;
        try
        {
            var result = await _monitor.Client.WakeAsync(order.DealId);
            if (!result.Ok) throw new InvalidOperationException(result.Message);
            await RefreshOrdersAsync();
        }
        catch (Exception error) { ShowError("Не удалось отправить", error.Message + "\n\nПовторный запрос безопасен и не создаст дубль."); }
        finally { WakeButton.IsEnabled = true; }
    }

    private void RelistButton_Click(object sender, RoutedEventArgs e)
    {
        if (OrdersList.SelectedItem is not Order order || _monitor?.Client is null) return;
        var dialog = new RelistWindow(_monitor.Client, order) { Owner = this };
        if (dialog.ShowDialog() == true) _ = RefreshOrdersAsync();
    }

    private void OpenDealButton_Click(object sender, RoutedEventArgs e)
    {
        if (OpenDealButton.Tag is not string url) return;
        try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); }
        catch (Exception error) { ShowError("Не удалось открыть Playerok", error.Message); }
    }

    private async void InstallUpdateButton_Click(object sender, RoutedEventArgs e)
    {
        if (_pendingUpdate is null) return;
        InstallUpdateButton.IsEnabled = false;
        InstallUpdateButton.Content = "Загрузка…";
        try { await _pendingUpdate.DownloadAndRestartAsync(); }
        catch (Exception error) { ShowError("Не удалось обновить", error.Message); InstallUpdateButton.IsEnabled = true; InstallUpdateButton.Content = "Повторить"; }
    }

    private void UpdatePageHeader()
    {
        PageTitle.Text = _section switch { "stats" => "Статистика", "settings" => "Настройки", _ => "Заказы" };
        PageSubtitle.Text = _section switch
        {
            "stats" => "Локально · последние 14 дней",
            "settings" => "Подключение, Windows и сообщения",
            _ => $"Новых: {_allOrders.Count(order => order.IsNew)}  ·  продаж: {_allOrders.Count(order => order.IsSale)}  ·  покупок: {_allOrders.Count(order => order.IsPurchase)}"
        };
    }

    private void UpdateMaximizeGlyph()
    {
        var maximized = WindowState == WindowState.Maximized;
        MaximizeIcon.Text = maximized ? "\uE923" : "\uE922";
        MaximizeButton.ToolTip = maximized ? "Восстановить" : "Развернуть";
    }

    private void ApplyAdaptiveLayout(double windowWidth)
    {
        var compact = windowWidth < 980;
        NavigationColumn.Width = new GridLength(compact ? 54 : 62);
        SearchContainer.Width = compact ? 178 : 240;
        PageSubtitle.Visibility = windowWidth < 860 ? Visibility.Collapsed : Visibility.Visible;
        StatsMetricsGrid.Columns = windowWidth < 1040 ? 2 : 4;

        if (windowWidth < 840)
        {
            OrderListColumn.MinWidth = 270;
            OrderDetailColumn.MinWidth = 300;
            OrderListColumn.Width = new GridLength(45, GridUnitType.Star);
            OrderDetailColumn.Width = new GridLength(55, GridUnitType.Star);
            Grid.SetColumn(StatsStatusPanel, 0);
            Grid.SetRow(StatsStatusPanel, 1);
            StatsStatusPanel.Margin = new Thickness(0, 10, 0, 0);
            StatsContentGrid.ColumnDefinitions[1].Width = new GridLength(0);
            StatsContentGrid.ColumnDefinitions[2].Width = new GridLength(0);
        }
        else
        {
            OrderListColumn.MinWidth = 300;
            OrderDetailColumn.MinWidth = 340;
            OrderListColumn.Width = new GridLength(42, GridUnitType.Star);
            OrderDetailColumn.Width = new GridLength(58, GridUnitType.Star);
            Grid.SetColumn(StatsStatusPanel, 2);
            Grid.SetRow(StatsStatusPanel, 0);
            StatsStatusPanel.Margin = new Thickness(0);
            StatsContentGrid.ColumnDefinitions[1].Width = new GridLength(10);
            StatsContentGrid.ColumnDefinitions[2].Width = new GridLength(1, GridUnitType.Star);
        }
    }

    private void OpenCommandPalette()
    {
        CommandSearchBox.Clear();
        CommandList.ItemsSource = _commands;
        CommandList.SelectedIndex = 0;
        CommandPaletteOverlay.Visibility = Visibility.Visible;
        Dispatcher.BeginInvoke(() => CommandSearchBox.Focus(), System.Windows.Threading.DispatcherPriority.Input);
    }

    private void CloseCommandPalette()
    {
        CommandPaletteOverlay.Visibility = Visibility.Collapsed;
        Focus();
    }

    private void FilterCommands()
    {
        var query = CommandSearchBox.Text.Trim();
        var matches = string.IsNullOrWhiteSpace(query)
            ? _commands
            : _commands.Where(command => command.Title.Contains(query, StringComparison.CurrentCultureIgnoreCase)
                || command.Description.Contains(query, StringComparison.CurrentCultureIgnoreCase)).ToList();
        CommandList.ItemsSource = matches;
        CommandList.SelectedIndex = matches.Count > 0 ? 0 : -1;
        CommandSearchHint.Visibility = string.IsNullOrEmpty(CommandSearchBox.Text) ? Visibility.Visible : Visibility.Collapsed;
    }

    private void ExecuteCommand(CommandEntry? command)
    {
        if (command is null) return;
        CloseCommandPalette();
        switch (command.Id)
        {
            case "new": SelectSection("orders"); SelectFilter("new"); break;
            case "sales": SelectSection("orders"); SelectFilter("sales"); break;
            case "purchases": SelectSection("orders"); SelectFilter("purchases"); break;
            case "stats": SelectSection("stats"); break;
            case "settings": SelectSection("settings"); break;
            case "refresh": _ = RefreshOrdersAsync(); break;
        }
    }

    private void MainWindow_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (CommandPaletteOverlay.Visibility == Visibility.Visible && e.Key == Key.Escape)
        {
            CloseCommandPalette();
            e.Handled = true;
            return;
        }
        if (Keyboard.Modifiers.HasFlag(ModifierKeys.Control) && e.Key == Key.K)
        {
            OpenCommandPalette();
            e.Handled = true;
        }
        else if (Keyboard.Modifiers.HasFlag(ModifierKeys.Control) && e.Key == Key.D1)
        {
            SelectSection("orders"); SelectFilter("new"); e.Handled = true;
        }
        else if (Keyboard.Modifiers.HasFlag(ModifierKeys.Control) && e.Key == Key.D2)
        {
            SelectSection("stats"); e.Handled = true;
        }
        else if (Keyboard.Modifiers.HasFlag(ModifierKeys.Control) && e.Key == Key.OemComma)
        {
            SelectSection("settings"); e.Handled = true;
        }
        else if (Keyboard.Modifiers.HasFlag(ModifierKeys.Control) && e.Key == Key.F)
        {
            SelectSection("orders"); SearchBox.Focus(); SearchBox.SelectAll(); e.Handled = true;
        }
        else if (e.Key == Key.F5)
        {
            _ = RefreshOrdersAsync(); e.Handled = true;
        }
    }

    private void MainWindow_SizeChanged(object sender, SizeChangedEventArgs e) => ApplyAdaptiveLayout(e.NewSize.Width);
    private void CommandPaletteButton_Click(object sender, RoutedEventArgs e) => OpenCommandPalette();
    private void CloseCommandPaletteButton_Click(object sender, RoutedEventArgs e) => CloseCommandPalette();
    private void CommandSearchBox_TextChanged(object sender, TextChangedEventArgs e) => FilterCommands();
    private void CommandSearchBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Down && CommandList.Items.Count > 0) { CommandList.Focus(); CommandList.SelectedIndex = Math.Max(0, CommandList.SelectedIndex); e.Handled = true; }
        else if (e.Key == Key.Enter) { ExecuteCommand(CommandList.SelectedItem as CommandEntry); e.Handled = true; }
    }
    private void CommandList_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) { ExecuteCommand(CommandList.SelectedItem as CommandEntry); e.Handled = true; }
        else if (e.Key == Key.Escape) { CloseCommandPalette(); e.Handled = true; }
    }
    private void CommandList_MouseDoubleClick(object sender, MouseButtonEventArgs e) => ExecuteCommand(CommandList.SelectedItem as CommandEntry);

    private static void ShowError(string title, string message) => MessageBox.Show(message, title, MessageBoxButton.OK, MessageBoxImage.Warning);
    private void OrdersList_SelectionChanged(object sender, SelectionChangedEventArgs e) => RenderOrder(OrdersList.SelectedItem as Order);
    private void SearchBox_TextChanged(object sender, TextChangedEventArgs e) { SearchHint.Visibility = string.IsNullOrEmpty(SearchBox.Text) ? Visibility.Visible : Visibility.Collapsed; if (IsLoaded) ApplyFilter(); }
    private async void RefreshButton_Click(object sender, RoutedEventArgs e) => await RefreshOrdersAsync();
    private void OrdersNav_Click(object sender, RoutedEventArgs e) => SelectSection("orders");
    private void StatsNav_Click(object sender, RoutedEventArgs e) => SelectSection("stats");
    private void SettingsNav_Click(object sender, RoutedEventArgs e) => SelectSection("settings");
    private void NewTab_Click(object sender, RoutedEventArgs e) => SelectFilter("new");
    private void SalesTab_Click(object sender, RoutedEventArgs e) => SelectFilter("sales");
    private void PurchasesTab_Click(object sender, RoutedEventArgs e) => SelectFilter("purchases");
    private void AllTab_Click(object sender, RoutedEventArgs e) => SelectFilter("all");
    private async void LoadRepliesButton_Click(object sender, RoutedEventArgs e) => await LoadRepliesAsync();
    private void AddMessageButton_Click(object sender, RoutedEventArgs e) => AddMessageRow("");
    private async void SaveRepliesButton_Click(object sender, RoutedEventArgs e) => await SaveRepliesAsync();
    private void MinimizeButton_Click(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;
    private void MaximizeButton_Click(object sender, RoutedEventArgs e) => WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
    private void CloseButton_Click(object sender, RoutedEventArgs e) => Close();

    private void MainWindow_Closing(object? sender, CancelEventArgs e)
    {
        if (_previewMode) return;
        if (!_exiting && _state.CloseToTray)
        {
            e.Cancel = true;
            Hide();
            return;
        }
        if (!_exiting)
        {
            _exiting = true;
            Dispatcher.BeginInvoke(() => System.Windows.Application.Current.Shutdown());
        }
        _monitor?.DisposeAsync().AsTask().GetAwaiter().GetResult();
        _notifier.Dispose();
        _tray?.Dispose();
    }

    private void ShowFromTray()
    {
        Dispatcher.Invoke(() => { Show(); WindowState = WindowState.Normal; Activate(); });
    }

    private void ExitApplication()
    {
        _exiting = true;
        Close();
        System.Windows.Application.Current.Shutdown();
    }

    private sealed record CommandEntry(string Id, string Title, string Description, string Shortcut);
}
