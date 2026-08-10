using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using PlayerokMonitor.Core;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
using Button = System.Windows.Controls.Button;
using Color = System.Windows.Media.Color;
using MessageBox = System.Windows.MessageBox;

namespace PlayerokMonitor.Desktop;

public partial class MainWindow : Window
{
    private readonly DesktopStateStore _store = new();
    private readonly WindowsNotifier _notifier = new();
    private readonly ObservableCollection<Order> _visibleOrders = [];
    private readonly List<System.Windows.Controls.TextBox> _messageBoxes = [];
    private DesktopState _state = new();
    private MonitorCoordinator? _monitor;
    private TrayService? _tray;
    private DesktopUpdateService.UpdateInfo? _pendingUpdate;
    private List<Order> _allOrders = [];
    private string _filter = "new";
    private bool _connected;
    private bool _exiting;
    private AutoReplySettings? _replySettings;
    private readonly bool _previewMode;

    public MainWindow(bool previewMode = false)
    {
        _previewMode = previewMode;
        InitializeComponent();
        OrdersList.ItemsSource = _visibleOrders;
        if (!previewMode) Loaded += MainWindow_Loaded;
        Closing += MainWindow_Closing;
        StateChanged += (_, _) => MaximizeButton.Content = WindowState == WindowState.Maximized ? "❐" : "□";
        ConfigureTimeZones();
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
        _tray?.Update(_allOrders.Count(order => order.IsNew), _connected);
        if (!string.IsNullOrWhiteSpace(selectedId)) OrdersList.SelectedItem = _visibleOrders.FirstOrDefault(order => order.DealId == selectedId);
    }

    internal void LoadPreviewData(string section)
    {
        var now = DateTimeOffset.Now;
        ApplyOrders([
            new Order { DealId = "preview-new", Direction = "OUT", ItemName = "100 BC в дни x2 · без привязки", Price = "249", SellerNetAmount = "224", SellerNetStatus = "PROCESSING", Counterparty = "galaxy_buyer", PaidAt = now.AddMinutes(-8).ToString("O"), ReplyMode = "SLEEP", SleepReplySent = true, WakeReplyAvailable = true },
            new Order { DealId = "preview-sale", Direction = "OUT", ItemName = "Игровая валюта · быстрая выдача", Price = "590", SellerNetAmount = "531", SellerNetStatus = "CONFIRMED", Counterparty = "buyer_ok", PaidAt = now.AddDays(-1).ToString("O"), SellerFulfilled = true, RecipientConfirmed = true },
            new Order { DealId = "preview-buy", Direction = "IN", ItemName = "Подписка на месяц", Price = "399", Counterparty = "seller_pro", PaidAt = now.AddDays(-2).ToString("O"), SellerFulfilled = true }
        ]);
        SelectFilter("new");
        SelectSection(section);
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
        var grid = new Grid { Margin = new Thickness(0, 12, 0, 0) };
        grid.ColumnDefinitions.Add(new ColumnDefinition());
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.Children.Add(new TextBlock { Text = label, Foreground = (Brush)FindResource("MutedBrush"), FontSize = 13 });
        var text = new TextBlock { Text = value, FontSize = 13, FontWeight = FontWeights.SemiBold, TextAlignment = TextAlignment.Right, MaxWidth = 310, TextWrapping = TextWrapping.Wrap };
        Grid.SetColumn(text, 1);
        grid.Children.Add(text);
        DetailFields.Children.Add(grid);
    }

    private void AddStatusCard(string title, string description, string tone)
    {
        var colors = tone switch
        {
            "green" => (Color.FromArgb(34, 70, 216, 135), Color.FromRgb(70, 216, 135)),
            "red" => (Color.FromArgb(34, 255, 111, 125), Color.FromRgb(255, 111, 125)),
            "amber" => (Color.FromArgb(34, 255, 199, 102), Color.FromRgb(255, 199, 102)),
            "blue" => (Color.FromArgb(34, 77, 154, 255), Color.FromRgb(77, 154, 255)),
            _ => (Color.FromArgb(22, 255, 255, 255), Color.FromRgb(174, 181, 194))
        };
        var stack = new StackPanel();
        stack.Children.Add(new TextBlock { Text = title, FontWeight = FontWeights.SemiBold, Foreground = new SolidColorBrush(colors.Item2) });
        stack.Children.Add(new TextBlock { Text = description, TextWrapping = TextWrapping.Wrap, Foreground = (Brush)FindResource("MutedBrush"), FontSize = 12, Margin = new Thickness(0, 4, 0, 0) });
        DetailFields.Children.Add(new Border { Background = new SolidColorBrush(colors.Item1), BorderBrush = new SolidColorBrush(Color.FromArgb(65, colors.Item2.R, colors.Item2.G, colors.Item2.B)), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(15), Padding = new Thickness(13), Margin = new Thickness(0, 12, 0, 0), Child = stack });
    }

    private void SetConnectionStatus(string text, bool online)
    {
        _connected = online;
        ConnectionText.Text = text;
        ConnectionDot.Fill = (Brush)FindResource(online ? "GreenBrush" : "AmberBrush");
        ConnectionPill.Background = new SolidColorBrush(online ? Color.FromArgb(24, 70, 216, 135) : Color.FromArgb(24, 255, 199, 102));
        _tray?.Update(_allOrders.Count(order => order.IsNew), online);
    }

    private void SelectSection(string section)
    {
        OrdersView.Visibility = section == "orders" ? Visibility.Visible : Visibility.Collapsed;
        StatsView.Visibility = section == "stats" ? Visibility.Visible : Visibility.Collapsed;
        SettingsView.Visibility = section == "settings" ? Visibility.Visible : Visibility.Collapsed;
        OrdersNav.Background = section == "orders" ? (Brush)FindResource("AccentSoftBrush") : Brushes.Transparent;
        StatsNav.Background = section == "stats" ? (Brush)FindResource("AccentSoftBrush") : Brushes.Transparent;
        SettingsNav.Background = section == "settings" ? (Brush)FindResource("AccentSoftBrush") : Brushes.Transparent;
        PageTitle.Text = section switch { "stats" => "Статистика", "settings" => "Настройки", _ => "Заказы" };
        PageSubtitle.Text = section switch { "stats" => "Только полезные показатели из локального снимка", "settings" => "Подключение, Windows и сообщения", _ => "Новые заказы, продажи и покупки" };
        if (section == "settings" && _replySettings is null) _ = LoadRepliesAsync();
        if (section == "stats") RenderStatistics();
    }

    private void SelectFilter(string filter)
    {
        _filter = filter;
        foreach (var button in new[] { NewTab, SalesTab, PurchasesTab, AllTab }) button.Background = Brushes.Transparent;
        var selected = filter switch { "sales" => SalesTab, "purchases" => PurchasesTab, "all" => AllTab, _ => NewTab };
        selected.Background = (Brush)FindResource("AccentSoftBrush");
        ApplyFilter();
    }

    private async Task RefreshOrdersAsync()
    {
        if (_monitor is null) return;
        RefreshButton.IsEnabled = false;
        RefreshButton.Content = "…";
        try { await _monitor.RefreshAsync(); }
        catch (Exception error) { ShowError("Не удалось обновить", error.Message); }
        finally { RefreshButton.IsEnabled = true; RefreshButton.Content = "↻"; }
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
        var box = new System.Windows.Controls.TextBox { Text = text, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 58 };
        var remove = new Button { Content = "×", Width = 40, Height = 40, Padding = new Thickness(0), Margin = new Thickness(8, 0, 0, 0), ToolTip = "Удалить сообщение" };
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
}
