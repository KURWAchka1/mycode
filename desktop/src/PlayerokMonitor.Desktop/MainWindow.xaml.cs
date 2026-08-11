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
using TextBox = System.Windows.Controls.TextBox;
using EmojiRichTextBox = Emoji.Wpf.RichTextBox;
using EmojiTextBlock = Emoji.Wpf.TextBlock;

namespace PlayerokMonitor.Desktop;

public partial class MainWindow : Window
{
    private readonly DesktopStateStore _store = new();
    private readonly WindowsNotifier _notifier = new();
    private readonly ObservableCollection<Order> _visibleOrders = [];
    private readonly List<EmojiRichTextBox> _messageBoxes = [];
    private readonly List<TextBlock> _messagePlaceholders = [];
    private DesktopState _state = new();
    private MonitorCoordinator? _monitor;
    private TrayService? _tray;
    private DesktopUpdateService.UpdateInfo? _pendingUpdate;
    private List<Order> _allOrders = [];
    private string _filter = "new";
    private string _section = "orders";
    private bool _connected;
    private bool _exiting;
    private bool _shutdownStarted;
    private bool _resourcesDisposed;
    private AutoReplySettings? _replySettings;
    private readonly bool _previewMode;
    private readonly List<CommandEntry> _commands =
    [
        new("new", "ĞĞ¾Ğ²Ñ‹Ğµ Ğ·Ğ°ĞºĞ°Ğ·Ñ‹", "ĞÑ‚ĞºÑ€Ñ‹Ñ‚ÑŒ Ğ¾Ñ‡ĞµÑ€ĞµĞ´ÑŒ Ğ½ĞµĞ²Ñ‹Ğ¿Ğ¾Ğ»Ğ½ĞµĞ½Ğ½Ñ‹Ñ… Ğ·Ğ°ĞºĞ°Ğ·Ğ¾Ğ²", "Ctrl+1"),
        new("sales", "ĞŸÑ€Ğ¾Ğ´Ğ°Ğ¶Ğ¸", "ĞŸĞ¾ĞºĞ°Ğ·Ğ°Ñ‚ÑŒ Ğ²ÑĞµ Ğ¿Ñ€Ğ¾Ğ´Ğ°Ğ¶Ğ¸", ""),
        new("purchases", "ĞŸĞ¾ĞºÑƒĞ¿ĞºĞ¸", "ĞŸĞ¾ĞºĞ°Ğ·Ğ°Ñ‚ÑŒ Ğ¿Ğ¾ĞºÑƒĞ¿ĞºĞ¸", ""),
        new("stats", "Ğ¡Ñ‚Ğ°Ñ‚Ğ¸ÑÑ‚Ğ¸ĞºĞ°", "ĞÑ‚ĞºÑ€Ñ‹Ñ‚ÑŒ Ğ»Ğ¾ĞºĞ°Ğ»ÑŒĞ½ÑƒÑ ÑÑ‚Ğ°Ñ‚Ğ¸ÑÑ‚Ğ¸ĞºÑƒ Ğ·Ğ° 14 Ğ´Ğ½ĞµĞ¹", "Ctrl+2"),
        new("settings", "ĞĞ°ÑÑ‚Ñ€Ğ¾Ğ¹ĞºĞ¸", "ĞŸĞ¾Ğ´ĞºĞ»ÑÑ‡ĞµĞ½Ğ¸Ğµ, Windows Ğ¸ Ğ°Ğ²Ñ‚Ğ¾ÑĞ¾Ğ¾Ğ±Ñ‰ĞµĞ½Ğ¸Ñ", "Ctrl+,"),
        new("refresh", "ĞĞ±Ğ½Ğ¾Ğ²Ğ¸Ñ‚ÑŒ Ğ·Ğ°ĞºĞ°Ğ·Ñ‹", "Ğ—Ğ°Ğ¿Ñ€Ğ¾ÑĞ¸Ñ‚ÑŒ Ğ°ĞºÑ‚ÑƒĞ°Ğ»ÑŒĞ½Ñ‹Ğ¹ ÑĞ½Ğ¸Ğ¼Ğ¾Ğº Ğ²Ñ€ÑƒÑ‡Ğ½ÑƒÑ", "F5")
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
        WindowWorkArea.Attach(this);
        ConfigureTimeZones();
        WireFixedMessageHints();
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
        var notificationReady = _notifier.Register();
        NotificationStatus.Text = notificationReady
            ? "ĞšĞ°Ğ½Ğ°Ğ» ÑƒĞ²ĞµĞ´Ğ¾Ğ¼Ğ»ĞµĞ½Ğ¸Ğ¹ Windows Ğ³Ğ¾Ñ‚Ğ¾Ğ²"
            : "Windows-toast Ğ½ĞµĞ´Ğ¾ÑÑ‚ÑƒĞ¿ĞµĞ½; ÑĞ¾Ğ±Ñ‹Ñ‚Ğ¸Ñ Ğ±ÑƒĞ´ÑƒÑ‚ Ğ¿Ğ¾ĞºĞ°Ğ·Ğ°Ğ½Ñ‹ Ñ‡ĞµÑ€ĞµĞ· Ğ·Ğ½Ğ°Ñ‡Ğ¾Ğº Ğ² Ñ‚Ñ€ĞµĞµ";
        _tray = new TrayService();
        _tray.OpenRequested += () => Dispatcher.BeginInvoke(new Action(ShowFromTray));
        _tray.RefreshRequested += () => Dispatcher.BeginInvoke(new Action(async () => await RefreshOrdersAsync()));
        _tray.ExitRequested += () => Dispatcher.BeginInvoke(new Action(ExitApplication));
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
        if (_state.NotificationsEnabled && !_notifier.Show(record.Title, record.Body, record.DealId))
        {
            _tray?.ShowNotification(record.Title, record.Body);
            NotificationStatus.Text = "Windows-toast Ğ½Ğµ ÑÑ€Ğ°Ğ±Ğ¾Ñ‚Ğ°Ğ» â€” Ğ²ĞºĞ»ÑÑ‡Ñ‘Ğ½ Ñ€ĞµĞ·ĞµÑ€Ğ² Ñ‡ĞµÑ€ĞµĞ· Ñ‚Ñ€ĞµĞ¹";
        }
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
            new Order { DealId = "preview-new", Direction = "OUT", ItemName = "ğŸ® 100 BC Ğ² Ğ´Ğ½Ğ¸ x2 Â· Ğ±ĞµĞ· Ğ¿Ñ€Ğ¸Ğ²ÑĞ·ĞºĞ¸", Price = "249", SellerNetAmount = "224", SellerNetStatus = "PROCESSING", Counterparty = "galaxy_buyer", PaidAt = now.AddMinutes(-8).ToString("O"), ReplyMode = "SLEEP", SleepReplySent = true, WakeReplyAvailable = true },
            new Order { DealId = "preview-sale", Direction = "OUT", ItemName = "âš¡ Ğ˜Ğ³Ñ€Ğ¾Ğ²Ğ°Ñ Ğ²Ğ°Ğ»ÑÑ‚Ğ° Â· Ğ±Ñ‹ÑÑ‚Ñ€Ğ°Ñ Ğ²Ñ‹Ğ´Ğ°Ñ‡Ğ°", Price = "590", SellerNetAmount = "531", SellerNetStatus = "CONFIRMED", Counterparty = "buyer_ok", PaidAt = now.AddDays(-1).ToString("O"), SellerFulfilled = true, RecipientConfirmed = true, ReviewRating = 5, ReviewText = "Ğ’ÑÑ‘ Ğ¿Ğ¾Ğ»ÑƒÑ‡Ğ¸Ğ» Ğ±Ñ‹ÑÑ‚Ñ€Ğ¾, ÑĞ¿Ğ°ÑĞ¸Ğ±Ğ¾!" },
            new Order { DealId = "preview-buy", Direction = "IN", ItemName = "âœ¨ ĞŸĞ¾Ğ´Ğ¿Ğ¸ÑĞºĞ° Ğ½Ğ° Ğ¼ĞµÑÑÑ†", Price = "399", Counterparty = "seller_pro", PaidAt = now.AddDays(-2).ToString("O"), SellerFulfilled = true }
        ]);
        SelectFilter("new");
        if (section.Equals("settings", StringComparison.OrdinalIgnoreCase) ||
            section.Equals("sleep", StringComparison.OrdinalIgnoreCase) ||
            section.Equals("defaults", StringComparison.OrdinalIgnoreCase) ||
            section.Equals("defaults-focused", StringComparison.OrdinalIgnoreCase) ||
            section.Equals("defaults-blurred", StringComparison.OrdinalIgnoreCase))
        {
            SleepStartBox.SelectedItem = "00:00";
            SleepEndBox.SelectedItem = "08:00";
            SleepTimezoneBox.SelectedItem = "Europe/Moscow";
            if (section.Equals("defaults", StringComparison.OrdinalIgnoreCase) ||
                section.Equals("defaults-focused", StringComparison.OrdinalIgnoreCase) ||
                section.Equals("defaults-blurred", StringComparison.OrdinalIgnoreCase))
            {
                _replySettings = new AutoReplySettings();
                FulfillmentMessageBox.Text = "";
                SleepMessageBox.Text = "";
                _messageBoxes.Clear();
                _messagePlaceholders.Clear();
                MessagesPanel.Children.Clear();
                AddMessageRow("");
            }
            else
            {
                FulfillmentMessageBox.Text = "âœ… Ğ—Ğ°ĞºĞ°Ğ· Ğ²Ñ‹Ğ¿Ğ¾Ğ»Ğ½ĞµĞ½. ĞŸĞ¾Ğ´Ñ‚Ğ²ĞµÑ€Ğ´Ğ¸Ñ‚Ğµ Ğ¿Ğ¾Ğ»ÑƒÑ‡ĞµĞ½Ğ¸Ğµ, Ğ¿Ğ¾Ğ¶Ğ°Ğ»ÑƒĞ¹ÑÑ‚Ğ°.";
                SleepMessageBox.Text = "ğŸŒ™ Ğ’Ğ¾Ğ·Ğ¼Ğ¾Ğ¶Ğ½Ğ¾, Ğ¿Ñ€Ğ¾Ğ´Ğ°Ğ²ĞµÑ† ÑĞµĞ¹Ñ‡Ğ°Ñ ÑĞ¿Ğ¸Ñ‚. ĞÑ‚Ğ²ĞµÑ‚Ğ¸Ñ‚ Ğ¿Ğ¾ÑĞ»Ğµ Ğ¿Ñ€Ğ¾Ğ±ÑƒĞ¶Ğ´ĞµĞ½Ğ¸Ñ.";
                if (_messageBoxes.Count == 0) AddMessageRow("Ğ¡Ğ¿Ğ°ÑĞ¸Ğ±Ğ¾ Ğ·Ğ° Ğ·Ğ°ĞºĞ°Ğ·! ğŸ‰ ĞĞ¶Ğ¸Ğ´Ğ°Ğ¹Ñ‚Ğµ ÑĞ¾Ğ¾Ğ±Ñ‰ĞµĞ½Ğ¸Ğµ Ğ¿Ñ€Ğ¾Ğ´Ğ°Ğ²Ñ†Ğ°.");
            }
        }
        if (section.Equals("command", StringComparison.OrdinalIgnoreCase))
        {
            SelectSection("orders");
            OpenCommandPalette();
        }
        else if (section.Equals("search", StringComparison.OrdinalIgnoreCase))
        {
            SelectSection("orders");
            Dispatcher.BeginInvoke(() => SearchBox.Focus(), System.Windows.Threading.DispatcherPriority.Input);
        }
        else if (section.Equals("sleep", StringComparison.OrdinalIgnoreCase))
        {
            SelectSection("settings");
            Dispatcher.BeginInvoke(() => SettingsView.ScrollToVerticalOffset(640), System.Windows.Threading.DispatcherPriority.Loaded);
        }
        else if (section.Equals("defaults", StringComparison.OrdinalIgnoreCase) ||
                 section.Equals("defaults-focused", StringComparison.OrdinalIgnoreCase) ||
                 section.Equals("defaults-blurred", StringComparison.OrdinalIgnoreCase))
        {
            SelectSection("settings");
            Dispatcher.BeginInvoke(() =>
            {
                SettingsView.ScrollToVerticalOffset(300);
                if (section.Equals("defaults-focused", StringComparison.OrdinalIgnoreCase)
                    || section.Equals("defaults-blurred", StringComparison.OrdinalIgnoreCase))
                {
                    _messageBoxes[0].Focus();
                    if (section.Equals("defaults-blurred", StringComparison.OrdinalIgnoreCase))
                    {
                        Dispatcher.BeginInvoke(() =>
                        {
                            Keyboard.ClearFocus();
                            SettingsView.Focus();
                        }, System.Windows.Threading.DispatcherPriority.Background);
                    }
                }
            }, System.Windows.Threading.DispatcherPriority.Loaded);
        }
        else if (section.Equals("review", StringComparison.OrdinalIgnoreCase))
        {
            SelectSection("orders");
            SelectFilter("sales");
            OrdersList.SelectedItem = _visibleOrders.FirstOrDefault(order => order.HasReview);
        }
        else SelectSection(section);
    }

    internal double SearchInsertionOffset => SearchBox.GetRectFromCharacterIndex(0).X;
    internal double CommandSearchInsertionOffset => CommandSearchBox.GetRectFromCharacterIndex(0).X;
    internal bool PaymentMessageHintVisible => _messagePlaceholders.Count > 0
        && _messagePlaceholders[0].Visibility == Visibility.Visible;
    internal bool PaymentMessageEditorFocused => _messageBoxes.Count > 0
        && _messageBoxes[0].IsKeyboardFocusWithin;

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
        EmptyOrdersText.Text = _filter == "new" && string.IsNullOrWhiteSpace(search) ? "ĞĞ¾Ğ²Ñ‹Ñ… Ğ·Ğ°ĞºĞ°Ğ·Ğ¾Ğ² Ğ½ĞµÑ‚" : "ĞĞ¸Ñ‡ĞµĞ³Ğ¾ Ğ½Ğµ Ğ½Ğ°Ğ¹Ğ´ĞµĞ½Ğ¾";
        if (_visibleOrders.Count > 0 && OrdersList.SelectedItem is null) OrdersList.SelectedIndex = 0;
        if (_visibleOrders.Count == 0) RenderOrder(null);
    }

    private void RenderStatistics()
    {
        var snapshot = StatisticsEngine.Calculate(_allOrders);
        StatNet.Text = $"{snapshot.NetRevenue:N0} â‚½";
        StatSales.Text = snapshot.Sales.ToString(CultureInfo.InvariantCulture);
        StatAverage.Text = $"{snapshot.AverageSale:N0} â‚½";
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
            ? $"{order.PriceDisplay}  Â·  Ğ²Ğ°Ğ¼ {order.NetDisplay}"
            : order.PriceDisplay;
        var dealUrl = string.IsNullOrWhiteSpace(order.DealUrl) ? $"https://playerok.com/deal/{order.DealId}" : order.DealUrl;
        OpenDealButton.Tag = dealUrl;
        WakeButton.Visibility = order.WakeReplyAvailable ? Visibility.Visible : Visibility.Collapsed;
        WakeButton.Content = order.WakeReplyRequested ? "ĞŸĞ¾Ğ²Ñ‚Ğ¾Ñ€Ğ¸Ñ‚ÑŒ Ğ¾Ñ‚Ğ¿Ñ€Ğ°Ğ²ĞºÑƒ" : "Ğ¯ Ğ¿Ñ€Ğ¾ÑĞ½ÑƒĞ»ÑÑ";
        var canRelist = order.IsSale && order.RelistEligible && !order.RolledBack && !order.ProblemActive && order.SellerFulfilled && !order.IsRelisted && !order.RelistState.Equals("PUBLISHING", StringComparison.OrdinalIgnoreCase);
        RelistButton.Visibility = canRelist ? Visibility.Visible : Visibility.Collapsed;
        DetailFields.Children.Clear();
        AddField("Ğ—Ğ°ĞºĞ°Ğ·", order.DealId);
        AddField(order.IsSale ? "ĞŸĞ¾ĞºÑƒĞ¿Ğ°Ñ‚ĞµĞ»ÑŒ" : "ĞŸÑ€Ğ¾Ğ´Ğ°Ğ²ĞµÑ†", string.IsNullOrWhiteSpace(order.CounterpartyDisplay) ? "â€”" : $"@{order.CounterpartyDisplay.TrimStart('@')}");
        AddField("ĞĞ¿Ğ»Ğ°Ñ‡ĞµĞ½", order.PaidAtDisplay);
        AddStatusCard(order.SellerFulfilled ? "Ğ’Ñ‹Ğ¿Ğ¾Ğ»Ğ½ĞµĞ½Ğ¸Ğµ Ğ¿Ğ¾Ğ´Ñ‚Ğ²ĞµÑ€Ğ¶Ğ´ĞµĞ½Ğ¾" : "Ğ’Ñ‹Ğ¿Ğ¾Ğ»Ğ½ĞµĞ½Ğ¸Ğµ Ğ½Ğµ Ğ¿Ğ¾Ğ´Ñ‚Ğ²ĞµÑ€Ğ¶Ğ´ĞµĞ½Ğ¾", order.IsSale ? (order.SellerFulfilled ? "Ğ’Ğ°Ğ¼Ğ¸" : "ĞÑƒĞ¶Ğ½Ğ¾ Ğ²Ñ‹Ğ¿Ğ¾Ğ»Ğ½Ğ¸Ñ‚ÑŒ Ğ·Ğ°ĞºĞ°Ğ· Ğ½Ğ° Playeroç½6¶‰Ëkºwµç]¥¹‘½İÌ¤ì…İ…¥Ğ}ÍÑ½É”¹M…Ù•Íå¹Œ¡}ÍÑ…Ñ”¤ì¥˜€¡}µ½¹¥Ñ½È¥Ì¹½Ğ¹Õ±°¤…İ…¥Ğ}µ½¹¥Ñ½È¹I•ÍÑ…ÉÑÍå¹Œ ¤ìô(€€€€€€€…Ñ €¡á•ÁÑ¥½¸•ÉÉ½È¤ìM¡½İÉÉ½È ‹BwBÔƒFBÓBÃBïBûFF0ƒFBûFFBÃB÷BãFF0ˆ°•ÉÉ½È¹5•ÍÍ…”¤ìô(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥Q•ÍÑ9½Ñ¥™¥…Ñ¥½¹	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤(€€€ì(€€€€€€€½¹ÍĞÍÑÉ¥¹œÑ¥Ñ±”€ô€‰A±…å•É½¬5½¹¥Ñ½Èˆì(€€€€€€€½¹ÍĞÍÑÉ¥¹œ‰½‘ä€ô€‹B‹B×FFBûBËBûBÔƒFBËB×BÓBûBóBïB×B÷BãBÔƒB÷BÀƒF7FBûBğƒBëBûBóBÿF3F;FB×FBÔˆì(€€€€€€€¥˜€¡}¹½Ñ¥™¥•È¹M¡½Ü¡Ñ¥Ñ±”°‰½‘ä°€ˆˆ¤¤(€€€€€€€ì(€€€€€€€€€€€9½Ñ¥™¥…Ñ¥½¹MÑ…ÑÕÌ¹Q•áĞ€ô€‹B‹B×FFƒBûFBÿFBÃBËBïB×BôƒBÈƒFB×B÷FF ƒFBËB×BÓBûBóBïB×B÷BãBä]¥¹‘½İÌˆì(€€€€€€€€€€€É•ÑÕÉ¸ì(€€€€€€€ô((€€€€€€€}ÑÉ…äü¹M¡½İ9½Ñ¥™¥…Ñ¥½¸¡Ñ¥Ñ±”°‰½‘ä¤ì(€€€€€€€9½Ñ¥™¥…Ñ¥½¹MÑ…ÑÕÌ¹Q•áĞ€ô€‹B‡BãFFB×BóB÷F/BäÑ½…ÍĞƒB÷B×BÓBûFFFBÿB×BôƒŠPƒFB×FFƒBÿBûBëBÃBßBÃBôƒFB×FB×BÜƒFFB×Bäˆì(€€€€€€€M¡½İÉÉ½È (€€€€€€€€€€€€‰]¥¹‘½İÌƒB÷BÔƒBÿFBãB÷F?BìƒFBãFFB×BóB÷BûBÔƒFBËB×BÓBûBóBïB×B÷BãBÔˆ°(€€€€€€€€€€€€‹BFBãBïBûBÛB×B÷BãBÔƒBÿBûBëBÃBßBÃBïBøƒFB×BßB×FBËB÷BûBÔƒFBËB×BÓBûBóBïB×B÷BãBÔƒFB×FB×BÜƒFFB×Bä¹q¹q»BSBãBÃBÏB÷BûFFBãBëBÀèí}¹½Ñ¥™¥•È¹1…ÍÑÉÉ½Éôˆ¤ì(€€€ô((€€€ÁÉ¥Ù…Ñ”…Íå¹ŒÙ½¥]…­•	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤(€€€ì(€€€€€€€¥˜€¡=É‘•ÉÍ1¥ÍĞ¹M•±•Ñ•‘%Ñ•´¥Ì¹½Ğ=É‘•È½É‘•Èñğ}µ½¹¥Ñ½Èü¹±¥•¹Ğ¥Ì¹Õ±°¤É•ÑÕÉ¸ì(€€€€€€€¥˜€¡5•ÍÍ…•	½à¹M¡½Ü¡Ñ¡¥Ì°€‹BBûBëFBÿBÃFB×BïF8ƒBûFBÿFBÃBËF?FFF<ƒBûBÇF/FB÷F/BÔƒFBûBûBÇF'B×B÷BãF<ƒ
¯BBûFBïBÔƒBûBÿBïBÃFF/
ì¸ƒB‡B×FBËB×F ƒB÷BÔƒFBûBßBÓBÃFFƒBÓFBÇBïF0ƒBÿFBàƒBÿBûBËFBûFB÷BûBğƒB÷BÃBÛBÃFBãBà¸ˆ°€‹B‡BûBûBÇF'BãFF0ƒBøƒBÿFBûBÇFBÛBÓB×B÷BãBàüˆ°5•ÍÍ…•	½á	ÕÑÑ½¸¹=-…¹•°°5•ÍÍ…•	½á%µ…”¹EÕ•ÍÑ¥½¸¤€„ô5•ÍÍ…•	½áI•ÍÕ±Ğ¹=,¤É•ÑÕÉ¸ì(€€€€€€€]…­•	ÕÑÑ½¸¹%Í¹…‰±•€ô™…±Í”ì(€€€€€€€ÑÉä(€€€€€€€ì(€€€€€€€€€€€Ù…ÈÉ•ÍÕ±Ğ€ô…İ…¥Ğ}µ½¹¥Ñ½È¹±¥•¹Ğ¹]…­•Íå¹Œ¡½É‘•È¹•…±%¤ì(€€€€€€€€€€€¥˜€ …É•ÍÕ±Ğ¹=¬¤Ñ¡É½Ü¹•Ü%¹Ù…±¥‘=Á•É…Ñ¥½¹á•ÁÑ¥½¸¡É•ÍÕ±Ğ¹5•ÍÍ…”¤ì(€€€€€€€€€€€…İ…¥ĞI•™É•Í¡=É‘•ÉÍÍå¹Œ ¤ì(€€€€€€€ô(€€€€€€€…Ñ €¡á•ÁÑ¥½¸•ÉÉ½È¤ìM¡½İÉÉ½È ‹BwBÔƒFBÓBÃBïBûFF0ƒBûFBÿFBÃBËBãFF0ˆ°•ÉÉ½È¹5•ÍÍ…”€¬€‰q¹q»BBûBËFBûFB÷F/BäƒBßBÃBÿFBûFƒBÇB×BßBûBÿBÃFB×BôƒBàƒB÷BÔƒFBûBßBÓBÃFFƒBÓFBÇBïF0¸ˆ¤ìô(€€€€€€€™¥¹…±±äì]…­•	ÕÑÑ½¸¹%Í¹…‰±•€ôÑÉÕ”ìô(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥I•±¥ÍÑ	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤(€€€ì(€€€€€€€¥˜€¡=É‘•ÉÍ1¥ÍĞ¹M•±•Ñ•‘%Ñ•´¥Ì¹½Ğ=É‘•È½É‘•Èñğ}µ½¹¥Ñ½Èü¹±¥•¹Ğ¥Ì¹Õ±°¤É•ÑÕÉ¸ì(€€€€€€€Ù…È‘¥…±½œ€ô¹•ÜI•±¥ÍÑ]¥¹‘½Ü¡}µ½¹¥Ñ½È¹±¥•¹Ğ°½É‘•È¤ì=İ¹•È€ôÑ¡¥Ìôì(€€€€€€€¥˜€¡‘¥…±½œ¹M¡½İ¥…±½œ ¤€ôôÑÉÕ”¤|€ôI•™É•Í¡=É‘•ÉÍÍå¹Œ ¤ì(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥=Á•¹•…±	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤(€€€ì(€€€€€€€¥˜€¡=Á•¹•…±	ÕÑÑ½¸¹Q…œ¥Ì¹½ĞÍÑÉ¥¹œÕÉ°¤É•ÑÕÉ¸ì(€€€€€€€ÑÉäìAÉ½•ÍÌ¹MÑ…ÉĞ¡¹•ÜAÉ½•ÍÍMÑ…ÉÑ%¹™¼¡ÕÉ°¤ìUÍ•M¡•±±á•ÕÑ”€ôÑÉÕ”ô¤ìô(€€€€€€€…Ñ €¡á•ÁÑ¥½¸•ÉÉ½È¤ìM¡½İÉÉ½È ‹BwBÔƒFBÓBÃBïBûFF0ƒBûFBëFF/FF0A±…å•É½¬ˆ°•ÉÉ½È¹5•ÍÍ…”¤ìô(€€€ô((€€€ÁÉ¥Ù…Ñ”…Íå¹ŒÙ½¥%¹ÍÑ…±±UÁ‘…Ñ•	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤(€€€ì(€€€€€€€¥˜€¡}Á•¹‘¥¹UÁ‘…Ñ”¥Ì¹Õ±°¤É•ÑÕÉ¸ì(€€€€€€€%¹ÍÑ…±±UÁ‘…Ñ•	ÕÑÑ½¸¹%Í¹…‰±•€ô™…±Í”ì(€€€€€€€%¹ÍÑ…±±UÁ‘…Ñ•	ÕÑÑ½¸¹½¹Ñ•¹Ğ€ô€‹B_BÃBÏFFBßBëBÃŠ˜ˆì(€€€€€€€ÑÉäì…İ…¥Ğ}Á•¹‘¥¹UÁ‘…Ñ”¹½İ¹±½…‘¹‘I•ÍÑ…ÉÑÍå¹Œ ¤ìô(€€€€€€€…Ñ €¡á•ÁÑ¥½¸•ÉÉ½È¤ìM¡½İÉÉ½È ‹BwBÔƒFBÓBÃBïBûFF0ƒBûBÇB÷BûBËBãFF0ˆ°•ÉÉ½È¹5•ÍÍ…”¤ì%¹ÍÑ…±±UÁ‘…Ñ•	ÕÑÑ½¸¹%Í¹…‰±•€ôÑÉÕ”ì%¹ÍÑ…±±UÁ‘…Ñ•	ÕÑÑ½¸¹½¹Ñ•¹Ğ€ô€‹BBûBËFBûFBãFF0ˆìô(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥UÁ‘…Ñ•A…•!•…‘•È ¤(€€€ì(€€€€€€€A…•Q¥Ñ±”¹Q•áĞ€ô}Í•Ñ¥½¸Íİ¥Ñ ì€‰ÍÑ…ÑÌˆ€ôø€‹B‡FBÃFBãFFBãBëBÀˆ°€‰Í•ÑÑ¥¹Ìˆ€ôø€‹BwBÃFFFBûBçBëBàˆ°|€ôø€‹B_BÃBëBÃBßF,ˆôì(€€€€€€€A…•MÕ‰Ñ¥Ñ±”¹Q•áĞ€ô}Í•Ñ¥½¸Íİ¥Ñ (€€€€€€€ì(€€€€€€€€€€€€‰ÍÑ…ÑÌˆ€ôø€‹BoBûBëBÃBïF3B÷Bøƒ
ÜƒBÿBûFBïB×BÓB÷BãBÔ€ÄĞƒBÓB÷B×Bäˆ°(€€€€€€€€€€€€‰Í•ÑÑ¥¹Ìˆ€ôø€‹BBûBÓBëBïF;FB×B÷BãBÔ°]¥¹‘½İÌƒBàƒFBûBûBÇF'B×B÷BãF<ˆ°(€€€€€€€€€€€|€ôø€‹BwBûBËF/Fèí}…±±=É‘•ÉÌ¹½Õ¹Ğ¡½É‘•È€ôø½É‘•È¹%Í9•Ü¥ô€ƒ
Ü€ƒBÿFBûBÓBÃBØèí}…±±=É‘•ÉÌ¹½Õ¹Ğ¡½É‘•È€ôø½É‘•È¹%ÍM…±”¥ô€ƒ
Ü€ƒBÿBûBëFBÿBûBèèí}…±±=É‘•ÉÌ¹½Õ¹Ğ¡½É‘•È€ôø½É‘•È¹%ÍAÕÉ¡…Í”¥ôˆ(€€€€€€€ôì(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥UÁ‘…Ñ•5…á¥µ¥é•±åÁ  ¤(€€€ì(€€€€€€€Ù…Èµ…á¥µ¥é•€ô]¥¹‘½İMÑ…Ñ”€ôô]¥¹‘½İMÑ…Ñ”¹5…á¥µ¥é•ì(€€€€€€€5…á¥µ¥é•%½¸¹Q•áĞ€ôµ…á¥µ¥é•€ü€‰qÕäÈÌˆ€è€‰qÕäÈÈˆì(€€€€€€€5…á¥µ¥é•	ÕÑÑ½¸¹Q½½±Q¥À€ôµ…á¥µ¥é•€ü€‹BKBûFFFBÃB÷BûBËBãFF0ˆ€è€‹BƒBÃBßBËB×FB÷FFF0ˆì(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥ÁÁ±å‘…ÁÑ¥Ù•1…å½ÕĞ¡‘½Õ‰±”İ¥¹‘½İ]¥‘Ñ ¤(€€€ì(€€€€€€€Ù…È½µÁ…Ğ€ôİ¥¹‘½İ]¥‘Ñ €ğ€äàÀì(€€€€€€€9…Ù¥…Ñ¥½¹½±Õµ¸¹]¥‘Ñ €ô¹•ÜÉ¥‘1•¹Ñ ¡½µÁ…Ğ€ü€ÔĞ€è€ØÈ¤ì(€€€€€€€M•…É¡½¹Ñ…¥¹•È¹]¥‘Ñ €ô½µÁ…Ğ€ü€ÄÜà€è€ÈĞÀì(€€€€€€€A…•MÕ‰Ñ¥Ñ±”¹Y¥Í¥‰¥±¥Ñä€ôİ¥¹‘½İ]¥‘Ñ €ğ€àØÀ€üY¥Í¥‰¥±¥Ñä¹½±±…ÁÍ•€èY¥Í¥‰¥±¥Ñä¹Y¥Í¥‰±”ì(€€€€€€€MÑ…ÑÍ5•ÑÉ¥ÍÉ¥¹½±Õµ¹Ì€ôİ¥¹‘½İ]¥‘Ñ €ğ€ÄÀĞÀ€ü€È€è€Ğì((€€€€€€€¥˜€¡İ¥¹‘½İ]¥‘Ñ €ğ€àĞÀ¤(€€€€€€€ì(€€€€€€€€€€€=É‘•É1¥ÍÑ½±Õµ¸¹5¥¹]¥‘Ñ €ô€ÈÜÀì(€€€€€€€€€€€=É‘•É•Ñ…¥±½±Õµ¸¹5¥¹]¥‘Ñ €ô€ÌÀÀì(€€€€€€€€€€€=É‘•É1¥ÍÑ½±Õµ¸¹]¥‘Ñ €ô¹•ÜÉ¥‘1•¹Ñ  ĞÔ°É¥‘U¹¥ÑQåÁ”¹MÑ…È¤ì(€€€€€€€€€€€=É‘•É•Ñ…¥±½±Õµ¸¹]¥‘Ñ €ô¹•ÜÉ¥‘1•¹Ñ  ÔÔ°É¥‘U¹¥ÑQåÁ”¹MÑ…È¤ì(€€€€€€€€€€€É¥¹M•Ñ½±Õµ¸¡MÑ…ÑÍMÑ…ÑÕÍA…¹•°°€À¤ì(€€€€€€€€€€€É¥¹M•ÑI½Ü¡MÑ…ÑÍMÑ…ÑÕÍA…¹•°°€Ä¤ì(€€€€€€€€€€€MÑ…ÑÍMÑ…ÑÕÍA…¹•°¹5…É¥¸€ô¹•ÜQ¡¥­¹•ÍÌ À°€ÄÀ°€À°€À¤ì(€€€€€€€€€€€MÑ…ÑÍ½¹Ñ•¹ÑÉ¥¹½±Õµ¹•™¥¹¥Ñ¥½¹ÍlÅt¹]¥‘Ñ €ô¹•ÜÉ¥‘1•¹Ñ  À¤ì(€€€€€€€€€€€MÑ…ÑÍ½¹Ñ•¹ÑÉ¥¹½±Õµ¹•™¥¹¥Ñ¥½¹ÍlÉt¹]¥‘Ñ €ô¹•ÜÉ¥‘1•¹Ñ  À¤ì(€€€€€€€ô(€€€€€€€•±Í”(€€€€€€€ì(€€€€€€€€€€€=É‘•É1¥ÍÑ½±Õµ¸¹5¥¹]¥‘Ñ €ô€ÌÀÀì(€€€€€€€€€€€=É‘•É•Ñ…¥±½±Õµ¸¹5¥¹]¥‘Ñ €ô€ÌĞÀì(€€€€€€€€€€€=É‘•É1¥ÍÑ½±Õµ¸¹]¥‘Ñ €ô¹•ÜÉ¥‘1•¹Ñ  ĞÈ°É¥‘U¹¥ÑQåÁ”¹MÑ…È¤ì(€€€€€€€€€€€=É‘•É•Ñ…¥±½±Õµ¸¹]¥‘Ñ €ô¹•ÜÉ¥‘1•¹Ñ  Ôà°É¥‘U¹¥ÑQåÁ”¹MÑ…È¤ì(€€€€€€€€€€€É¥¹M•Ñ½±Õµ¸¡MÑ…ÑÍMÑ…ÑÕÍA…¹•°°€È¤ì(€€€€€€€€€€€É¥¹M•ÑI½Ü¡MÑ…ÑÍMÑ…ÑÕÍA…¹•°°€À¤ì(€€€€€€€€€€€MÑ…ÑÍMÑ…ÑÕÍA…¹•°¹5…É¥¸€ô¹•ÜQ¡¥­¹•ÍÌ À¤ì(€€€€€€€€€€€MÑ…ÑÍ½¹Ñ•¹ÑÉ¥¹½±Õµ¹•™¥¹¥Ñ¥½¹ÍlÅt¹]¥‘Ñ €ô¹•ÜÉ¥‘1•¹Ñ  ÄÀ¤ì(€€€€€€€€€€€MÑ…ÑÍ½¹Ñ•¹ÑÉ¥¹½±Õµ¹•™¥¹¥Ñ¥½¹ÍlÉt¹]¥‘Ñ €ô¹•ÜÉ¥‘1•¹Ñ  Ä°É¥‘U¹¥ÑQåÁ”¹MÑ…È¤ì(€€€€€€€ô(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥=Á•¹½µµ…¹‘A…±•ÑÑ” ¤(€€€ì(€€€€€€€½µµ…¹‘M•…É¡	½à¹±•…È ¤ì(€€€€€€€½µµ…¹‘1¥ÍĞ¹%Ñ•µÍM½ÕÉ”€ô}½µµ…¹‘Ìì(€€€€€€€½µµ…¹‘1¥ÍĞ¹M•±•Ñ•‘%¹‘•à€ô€Àì(€€€€€€€½µµ…¹‘A…±•ÑÑ•=Ù•É±…ä¹Y¥Í¥‰¥±¥Ñä€ôY¥Í¥‰¥±¥Ñä¹Y¥Í¥‰±”ì(€€€€€€€¥ÍÁ…Ñ¡•È¹	•¥¹%¹Ù½­”  ¤€ôø½µµ…¹‘M•…É¡	½à¹½ÕÌ ¤°MåÍÑ•´¹]¥¹‘½İÌ¹Q¡É•…‘¥¹œ¹¥ÍÁ…Ñ¡•ÉAÉ¥½É¥Ñä¹%¹ÁÕĞ¤ì(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥±½Í•½µµ…¹‘A…±•ÑÑ” ¤(€€€ì(€€€€€€€½µµ…¹‘A…±•ÑÑ•=Ù•É±…ä¹Y¥Í¥‰¥±¥Ñä€ôY¥Í¥‰¥±¥Ñä¹½±±…ÁÍ•ì(€€€€€€€½ÕÌ ¤ì(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥¥±Ñ•É½µµ…¹‘Ì ¤(€€€ì(€€€€€€€Ù…ÈÅÕ•Éä€ô½µµ…¹‘M•…É¡	½à¹Q•áĞ¹QÉ¥´ ¤ì(€€€€€€€Ù…Èµ…Ñ¡•Ì€ôÍÑÉ¥¹œ¹%Í9Õ±±=É]¡¥Ñ•MÁ…”¡ÅÕ•Éä¤(€€€€€€€€€€€€ü}½µµ…¹‘Ì(€€€€€€€€€€€€è}½µµ…¹‘Ì¹]¡•É”¡½µµ…¹€ôø½µµ…¹¹Q¥Ñ±”¹½¹Ñ…¥¹Ì¡ÅÕ•Éä°MÑÉ¥¹½µÁ…É¥Í½¸¹ÕÉÉ•¹ÑÕ±ÑÕÉ•%¹½É•…Í”¤(€€€€€€€€€€€€€€€ñğ½µµ…¹¹•ÍÉ¥ÁÑ¥½¸¹½¹Ñ…¥¹Ì¡ÅÕ•Éä°MÑÉ¥¹½µÁ…É¥Í½¸¹ÕÉÉ•¹ÑÕ±ÑÕÉ•%¹½É•…Í”¤¤¹Q½1¥ÍĞ ¤ì(€€€€€€€½µµ…¹‘1¥ÍĞ¹%Ñ•µÍM½ÕÉ”€ôµ…Ñ¡•Ìì(€€€€€€€½µµ…¹‘1¥ÍĞ¹M•±•Ñ•‘%¹‘•à€ôµ…Ñ¡•Ì¹½Õ¹Ğ€ø€À€ü€À€è€´Äì(€€€€€€€UÁ‘…Ñ•%¹ÁÕÑ!¥¹Ğ¡½µµ…¹‘M•…É¡	½à°½µµ…¹‘M•…É¡!¥¹Ğ¤ì(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥á•ÕÑ•½µµ…¹¡½µµ…¹‘¹ÑÉäü½µµ…¹¤(€€€ì(€€€€€€€¥˜€¡½µµ…¹¥Ì¹Õ±°¤É•ÑÕÉ¸ì(€€€€€€€±½Í•½µµ…¹‘A…±•ÑÑ” ¤ì(€€€€€€€Íİ¥Ñ €¡½µµ…¹¹%¤(€€€€€€€ì(€€€€€€€€€€€…Í”€‰¹•ÜˆèM•±•ÑM•Ñ¥½¸ ‰½É‘•ÉÌˆ¤ìM•±•Ñ¥±Ñ•È ‰¹•Üˆ¤ì‰É•…¬ì(€€€€€€€€€€€…Í”€‰Í…±•ÌˆèM•±•ÑM•Ñ¥½¸ ‰½É‘•ÉÌˆ¤ìM•±•Ñ¥±Ñ•È ‰Í…±•Ìˆ¤ì‰É•…¬ì(€€€€€€€€€€€…Í”€‰ÁÕÉ¡…Í•ÌˆèM•±•ÑM•Ñ¥½¸ ‰½É‘•ÉÌˆ¤ìM•±•Ñ¥±Ñ•È ‰ÁÕÉ¡…Í•Ìˆ¤ì‰É•…¬ì(€€€€€€€€€€€…Í”€‰ÍÑ…ÑÌˆèM•±•ÑM•Ñ¥½¸ ‰ÍÑ…ÑÌˆ¤ì‰É•…¬ì(€€€€€€€€€€€…Í”€‰Í•ÑÑ¥¹ÌˆèM•±•ÑM•Ñ¥½¸ ‰Í•ÑÑ¥¹Ìˆ¤ì‰É•…¬ì(€€€€€€€€€€€…Í”€‰É•™É•Í ˆè|€ôI•™É•Í¡=É‘•ÉÍÍå¹Œ ¤ì‰É•…¬ì(€€€€€€€ô(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥5…¥¹]¥¹‘½İ}AÉ•Ù¥•İ-•å½İ¸¡½‰©•ĞÍ•¹‘•È°-•åÙ•¹ÑÉÌ”¤(€€€ì(€€€€€€€¥˜€¡½µµ…¹‘A…±•ÑÑ•=Ù•É±…ä¹Y¥Í¥‰¥±¥Ñä€ôôY¥Í¥‰¥±¥Ñä¹Y¥Í¥‰±”€˜˜”¹-•ä€ôô-•ä¹Í…Á”¤(€€€€€€€ì(€€€€€€€€€€€±½Í•½µµ…¹‘A…±•ÑÑ” ¤ì(€€€€€€€€€€€”¹!…¹‘±•€ôÑÉÕ”ì(€€€€€€€€€€€É•ÑÕÉ¸ì(€€€€€€€ô(€€€€€€€¥˜€¡-•å‰½…É¹5½‘¥™¥•ÉÌ¹!…Í±…œ¡5½‘¥™¥•É-•åÌ¹½¹ÑÉ½°¤€˜˜”¹-•ä€ôô-•ä¹,¤(€€€€€€€ì(€€€€€€€€€€€=Á•¹½µµ…¹‘A…±•ÑÑ” ¤ì(€€€€€€€€€€€”¹!…¹‘±•€ôÑÉÕ”ì(€€€€€€€ô(€€€€€€€•±Í”¥˜€¡-•å‰½…É¹5½‘¥™¥•ÉÌ¹!…Í±…œ¡5½‘¥™¥•É-•åÌ¹½¹ÑÉ½°¤€˜˜”¹-•ä€ôô-•ä¹Ä¤(€€€€€€€ì(€€€€€€€€€€€M•±•ÑM•Ñ¥½¸ ‰½É‘•ÉÌˆ¤ìM•±•Ñ¥±Ñ•È ‰¹•Üˆ¤ì”¹!…¹‘±•€ôÑÉÕ”ì(€€€€€€€ô(€€€€€€€•±Í”¥˜€¡-•å‰½…É¹5½‘¥™¥•ÉÌ¹!…Í±…œ¡5½‘¥™¥•É-•åÌ¹½¹ÑÉ½°¤€˜˜”¹-•ä€ôô-•ä¹È¤(€€€€€€€ì(€€€€€€€€€€€M•±•ÑM•Ñ¥½¸ ‰ÍÑ…ÑÌˆ¤ì”¹!…¹‘±•€ôÑÉÕ”ì(€€€€€€€ô(€€€€€€€•±Í”¥˜€¡-•å‰½…É¹5½‘¥™¥•ÉÌ¹!…Í±…œ¡5½‘¥™¥•É-•åÌ¹½¹ÑÉ½°¤€˜˜”¹-•ä€ôô-•ä¹=•µ½µµ„¤(€€€€€€€ì(€€€€€€€€€€€M•±•ÑM•Ñ¥½¸ ‰Í•ÑÑ¥¹Ìˆ¤ì”¹!…¹‘±•€ôÑÉÕ”ì(€€€€€€€ô(€€€€€€€•±Í”¥˜€¡-•å‰½…É¹5½‘¥™¥•ÉÌ¹!…Í±…œ¡5½‘¥™¥•É-•åÌ¹½¹ÑÉ½°¤€˜˜”¹-•ä€ôô-•ä¹¤(€€€€€€€ì(€€€€€€€€€€€M•±•ÑM•Ñ¥½¸ ‰½É‘•ÉÌˆ¤ìM•…É¡	½à¹½ÕÌ ¤ìM•…É¡	½à¹M•±•Ñ±° ¤ì”¹!…¹‘±•€ôÑÉÕ”ì(€€€€€€€ô(€€€€€€€•±Í”¥˜€¡”¹-•ä€ôô-•ä¹Ô¤(€€€€€€€ì(€€€€€€€€€€€|€ôI•™É•Í¡=É‘•ÉÍÍå¹Œ ¤ì”¹!…¹‘±•€ôÑÉÕ”ì(€€€€€€€ô(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥5…¥¹]¥¹‘½İ}M¥é•¡…¹•¡½‰©•ĞÍ•¹‘•È°M¥é•¡…¹•‘Ù•¹ÑÉÌ”¤€ôøÁÁ±å‘…ÁÑ¥Ù•1…å½ÕĞ¡”¹9•İM¥é”¹]¥‘Ñ ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥M•ÑÑ¥¹ÍY¥•İ}AÉ•Ù¥•İ5½ÕÍ•½İ¸¡½‰©•ĞÍ•¹‘•È°5½ÕÍ•	ÕÑÑ½¹Ù•¹ÑÉÌ”¤(€€€ì(€€€€€€€¥˜€¡%Í%¹Ñ•É…Ñ¥Ù•M•ÑÑ¥¹ÍQ…É•Ğ¡”¹=É¥¥¹…±M½ÕÉ”…Ì•Á•¹‘•¹å=‰©•Ğ¤¤É•ÑÕÉ¸ì(€€€€€€€-•å‰½…É¹±•…É½ÕÌ ¤ì(€€€€€€€M•ÑÑ¥¹ÍY¥•Ü¹½ÕÌ ¤ì(€€€€€€€¥ÍÁ…Ñ¡•È¹	•¥¹%¹Ù½­”  ¤€ôø(€€€€€€€ì(€€€€€€€€€€€I•™É•Í¡A…åµ•¹Ñ5•ÍÍ…•A±…•¡½±‘•ÉÌ ¤ì(€€€€€€€€€€€I•™É•Í¡¥á•‘5•ÍÍ…•!¥¹ÑÌ ¤ì(€€€€€€€ô°MåÍÑ•´¹]¥¹‘½İÌ¹Q¡É•…‘¥¹œ¹¥ÍÁ…Ñ¡•ÉAÉ¥½É¥Ñä¹%¹ÁÕĞ¤ì(€€€ô((€€€ÁÉ¥Ù…Ñ”ÍÑ…Ñ¥Œ‰½½°%Í%¹Ñ•É…Ñ¥Ù•M•ÑÑ¥¹ÍQ…É•Ğ¡•Á•¹‘•¹å=‰©•ĞüÍ½ÕÉ”¤(€€€ì(€€€€€€€İ¡¥±”€¡Í½ÕÉ”¥Ì¹½Ğ¹Õ±°¤(€€€€€€€ì(€€€€€€€€€€€¥˜€¡Í½ÕÉ”¥ÌMåÍÑ•´¹]¥¹‘½İÌ¹½¹ÑÉ½±Ì¹AÉ¥µ¥Ñ¥Ù•Ì¹Q•áÑ	½á	…Í”(€€€€€€€€€€€€€€€½ÈMåÍÑ•´¹]¥¹‘½İÌ¹½¹ÑÉ½±Ì¹AÉ¥µ¥Ñ¥Ù•Ì¹	ÕÑÑ½¹	…Í”(€€€€€€€€€€€€€€€½ÈMåÍÑ•´¹]¥¹‘½İÌ¹½¹ÑÉ½±Ì¹AÉ¥µ¥Ñ¥Ù•Ì¹M•±•Ñ½È(€€€€€€€€€€€€€€€½ÈMåÍÑ•´¹]¥¹‘½İÌ¹½¹ÑÉ½±Ì¹AÉ¥µ¥Ñ¥Ù•Ì¹I…¹•	…Í”¤(€€€€€€€€€€€€€€€É•ÑÕÉ¸ÑÉÕ”ì(€€€€€€€€€€€Í½ÕÉ”€ôÍ½ÕÉ”¥ÌY¥ÍÕ…°€üY¥ÍÕ…±QÉ••!•±Á•È¹•ÑA…É•¹Ğ¡Í½ÕÉ”¤€è¹Õ±°ì(€€€€€€€ô(€€€€€€€É•ÑÕÉ¸™…±Í”ì(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥½µµ…¹‘A…±•ÑÑ•	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôø=Á•¹½µµ…¹‘A…±•ÑÑ” ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥±½Í•½µµ…¹‘A…±•ÑÑ•	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôø±½Í•½µµ…¹‘A…±•ÑÑ” ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥½µµ…¹‘M•…É¡	½á}Q•áÑ¡…¹•¡½‰©•ĞÍ•¹‘•È°Q•áÑ¡…¹•‘Ù•¹ÑÉÌ”¤€ôø¥±Ñ•É½µµ…¹‘Ì ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥½µµ…¹‘M•…É¡	½á}½ÕÍ¡…¹•¡½‰©•ĞÍ•¹‘•È°-•å‰½…É‘½ÕÍ¡…¹•‘Ù•¹ÑÉÌ”¤€ôøUÁ‘…Ñ•%¹ÁÕÑ!¥¹Ğ¡½µµ…¹‘M•…É¡	½à°½µµ…¹‘M•…É¡!¥¹Ğ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥½µµ…¹‘M•…É¡	½á}-•å½İ¸¡½‰©•ĞÍ•¹‘•È°-•åÙ•¹ÑÉÌ”¤(€€€ì(€€€€€€€¥˜€¡”¹-•ä€ôô-•ä¹½İ¸€˜˜½µµ…¹‘1¥ÍĞ¹%Ñ•µÌ¹½Õ¹Ğ€ø€À¤ì½µµ…¹‘1¥ÍĞ¹½ÕÌ ¤ì½µµ…¹‘1¥ÍĞ¹M•±•Ñ•‘%¹‘•à€ô5…Ñ ¹5…à À°½µµ…¹‘1¥ÍĞ¹M•±•Ñ•‘%¹‘•à¤ì”¹!…¹‘±•€ôÑÉÕ”ìô(€€€€€€€•±Í”¥˜€¡”¹-•ä€ôô-•ä¹¹Ñ•È¤ìá•ÕÑ•½µµ…¹¡½µµ…¹‘1¥ÍĞ¹M•±•Ñ•‘%Ñ•´…Ì½µµ…¹‘¹ÑÉä¤ì”¹!…¹‘±•€ôÑÉÕ”ìô(€€€ô(€€€ÁÉ¥Ù…Ñ”Ù½¥½µµ…¹‘1¥ÍÑ}-•å½İ¸¡½‰©•ĞÍ•¹‘•È°-•åÙ•¹ÑÉÌ”¤(€€€ì(€€€€€€€¥˜€¡”¹-•ä€ôô-•ä¹¹Ñ•È¤ìá•ÕÑ•½µµ…¹¡½µµ…¹‘1¥ÍĞ¹M•±•Ñ•‘%Ñ•´…Ì½µµ…¹‘¹ÑÉä¤ì”¹!…¹‘±•€ôÑÉÕ”ìô(€€€€€€€•±Í”¥˜€¡”¹-•ä€ôô-•ä¹Í…Á”¤ì±½Í•½µµ…¹‘A…±•ÑÑ” ¤ì”¹!…¹‘±•€ôÑÉÕ”ìô(€€€ô(€€€ÁÉ¥Ù…Ñ”Ù½¥½µµ…¹‘1¥ÍÑ}5½ÕÍ•½Õ‰±•±¥¬¡½‰©•ĞÍ•¹‘•È°5½ÕÍ•	ÕÑÑ½¹Ù•¹ÑÉÌ”¤€ôøá•ÕÑ•½µµ…¹¡½µµ…¹‘1¥ÍĞ¹M•±•Ñ•‘%Ñ•´…Ì½µµ…¹‘¹ÑÉä¤ì((€€€ÁÉ¥Ù…Ñ”ÍÑ…Ñ¥ŒÙ½¥M¡½İÉÉ½È¡ÍÑÉ¥¹œÑ¥Ñ±”°ÍÑÉ¥¹œµ•ÍÍ…”¤€ôø5•ÍÍ…•	½à¹M¡½Ü¡µ•ÍÍ…”°Ñ¥Ñ±”°5•ÍÍ…•	½á	ÕÑÑ½¸¹=,°5•ÍÍ…•	½á%µ…”¹]…É¹¥¹œ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥=É‘•ÉÍ1¥ÍÑ}M•±•Ñ¥½¹¡…¹•¡½‰©•ĞÍ•¹‘•È°M•±•Ñ¥½¹¡…¹•‘Ù•¹ÑÉÌ”¤€ôøI•¹‘•É=É‘•È¡=É‘•ÉÍ1¥ÍĞ¹M•±•Ñ•‘%Ñ•´…Ì=É‘•È¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥M•…É¡	½á}Q•áÑ¡…¹•¡½‰©•ĞÍ•¹‘•È°Q•áÑ¡…¹•‘Ù•¹ÑÉÌ”¤ìUÁ‘…Ñ•%¹ÁÕÑ!¥¹Ğ¡M•…É¡	½à°M•…É¡!¥¹Ğ¤ì¥˜€¡%Í1½…‘•¤ÁÁ±å¥±Ñ•È ¤ìô(€€€ÁÉ¥Ù…Ñ”Ù½¥M•…É¡	½á}½ÕÍ¡…¹•¡½‰©•ĞÍ•¹‘•È°-•å‰½…É‘½ÕÍ¡…¹•‘Ù•¹ÑÉÌ”¤€ôøUÁ‘…Ñ•%¹ÁÕÑ!¥¹Ğ¡M•…É¡	½à°M•…É¡!¥¹Ğ¤ì((€€€ÁÉ¥Ù…Ñ”ÍÑ…Ñ¥ŒÙ½¥UÁ‘…Ñ•%¹ÁÕÑ!¥¹Ğ¡Q•áÑ	½à¥¹ÁÕĞ°Q•áÑ	±½¬¡¥¹Ğ¤(€€€ì(€€€€€€€¡¥¹Ğ¹Y¥Í¥‰¥±¥Ñä€ôÍÑÉ¥¹œ¹%Í9Õ±±=É]¡¥Ñ•MÁ…”¡¥¹ÁÕĞ¹Q•áĞ¤€˜˜€…¥¹ÁÕĞ¹%Í-•å‰½…É‘½ÕÍ]¥Ñ¡¥¸(€€€€€€€€€€€€üY¥Í¥‰¥±¥Ñä¹Y¥Í¥‰±”(€€€€€€€€€€€€èY¥Í¥‰¥±¥Ñä¹½±±…ÁÍ•ì(€€€ô((€€€ÁÉ¥Ù…Ñ”ÍÑ…Ñ¥ŒÙ½¥UÁ‘…Ñ•%¹ÁÕÑ!¥¹Ğ¡µ½©¥I¥¡Q•áÑ	½à¥¹ÁÕĞ°Q•áÑ	±½¬¡¥¹Ğ¤(€€€ì(€€€€€€€¡¥¹Ğ¹Y¥Í¥‰¥±¥Ñä€ôÍÑÉ¥¹œ¹%Í9Õ±±=É]¡¥Ñ•MÁ…”¡¥¹ÁÕĞ¹Q•áĞ¤€˜˜€…¥¹ÁÕĞ¹%Í-•å‰½…É‘½ÕÍ]¥Ñ¡¥¸(€€€€€€€€€€€€üY¥Í¥‰¥±¥Ñä¹Y¥Í¥‰±”(€€€€€€€€€€€€èY¥Í¥‰¥±¥Ñä¹½±±…ÁÍ•ì(€€€ô(€€€ÁÉ¥Ù…Ñ”…Íå¹ŒÙ½¥I•™É•Í¡	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôø…İ…¥ĞI•™É•Í¡=É‘•ÉÍÍå¹Œ ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥=É‘•ÉÍ9…Ù}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôøM•±•ÑM•Ñ¥½¸ ‰½É‘•ÉÌˆ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥MÑ…ÑÍ9…Ù}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôøM•±•ÑM•Ñ¥½¸ ‰ÍÑ…ÑÌˆ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥M•ÑÑ¥¹Í9…Ù}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôøM•±•ÑM•Ñ¥½¸ ‰Í•ÑÑ¥¹Ìˆ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥9•İQ…‰}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôøM•±•Ñ¥±Ñ•È ‰¹•Üˆ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥M…±•ÍQ…‰}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôøM•±•Ñ¥±Ñ•È ‰Í…±•Ìˆ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥AÕÉ¡…Í•ÍQ…‰}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôøM•±•Ñ¥±Ñ•È ‰ÁÕÉ¡…Í•Ìˆ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥±±Q…‰}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôøM•±•Ñ¥±Ñ•È ‰…±°ˆ¤ì(€€€ÁÉ¥Ù…Ñ”…Íå¹ŒÙ½¥1½…‘I•Á±¥•Í	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôø…İ…¥Ğ1½…‘I•Á±¥•ÍÍå¹Œ ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥‘‘5•ÍÍ…•	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôø‘‘5•ÍÍ…•I½Ü ˆˆ¤ì(€€€ÁÉ¥Ù…Ñ”…Íå¹ŒÙ½¥M…Ù•I•Á±¥•Í	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôø…İ…¥ĞM…Ù•I•Á±¥•ÍÍå¹Œ ¤ì(€€€ÁÉ¥Ù…Ñ”Ù½¥5¥¹¥µ¥é•	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôø]¥¹‘½İMÑ…Ñ”€ô]¥¹‘½İMÑ…Ñ”¹5¥¹¥µ¥é•ì(€€€ÁÉ¥Ù…Ñ”Ù½¥5…á¥µ¥é•	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôø]¥¹‘½İMÑ…Ñ”€ô]¥¹‘½İMÑ…Ñ”€ôô]¥¹‘½İMÑ…Ñ”¹5…á¥µ¥é•€ü]¥¹‘½İMÑ…Ñ”¹9½Éµ…°€è]¥¹‘½İMÑ…Ñ”¹5…á¥µ¥é•ì(€€€ÁÉ¥Ù…Ñ”Ù½¥±½Í•	ÕÑÑ½¹}±¥¬¡½‰©•ĞÍ•¹‘•È°I½ÕÑ•‘Ù•¹ÑÉÌ”¤€ôø±½Í” ¤ì((€€€ÁÉ¥Ù…Ñ”Ù½¥5…¥¹]¥¹‘½İ}±½Í¥¹œ¡½‰©•ĞüÍ•¹‘•È°…¹•±Ù•¹ÑÉÌ”¤(€€€ì(€€€€€€€¥˜€¡}ÁÉ•Ù¥•İ5½‘”¤É•ÑÕÉ¸ì(€€€€€€€¥˜€¡}•á¥Ñ¥¹œ¤É•ÑÕÉ¸ì(€€€€€€€”¹…¹•°€ôÑÉÕ”ì(€€€€€€€¥˜€¡}ÍÑ…Ñ”¹±½Í•Q½QÉ…ä¤(€€€€€€€ì(€€€€€€€€€€€!¥‘” ¤ì(€€€€€€€€€€€É•ÑÕÉ¸ì(€€€€€€€ô(€€€€€€€á¥ÑÁÁ±¥…Ñ¥½¸ ¤ì(€€€ô((€€€ÁÉ¥Ù…Ñ”Ù½¥M¡½İÉ½µQÉ…ä ¤(€€€ì(€€€€€€€¥ÍÁ…Ñ¡•È¹%¹Ù½­”  ¤€ôøìM¡½Ü ¤ì]¥¹‘½İMÑ…Ñ”€ô]¥¹‘½İMÑ…Ñ”¹9½Éµ…°ìÑ¥Ù…Ñ” ¤ìô¤ì(€€€ô((€€€ÁÉ¥Ù…Ñ”…Íå¹ŒÙ½¥á¥ÑÁÁ±¥…Ñ¥½¸ ¤(€€€ì(€€€€€€€¥˜€¡}Í¡ÕÑ‘½İ¹MÑ…ÉÑ•¤É•ÑÕÉ¸ì(€€€€€€€}Í¡ÕÑ‘½İ¹MÑ…ÉÑ•€ôÑÉÕ”ì(€€€€€€€}•á¥Ñ¥¹œ€ôÑÉÕ”ì(€€€€€€€!¥‘” ¤ì(€€€€€€€ÑÉä(€€€€€€€ì(€€€€€€€€€€€…İ…¥Ğ¥ÍÁ½Í•ÁÁ±¥…Ñ¥½¹I•Í½ÕÉ•ÍÍå¹Œ ¤ì(€€€€€€€ô(€€€€€€€™¥¹…±±ä(€€€€€€€ì(€€€€€€€€€€€±½Í¥¹œ€´ô5…¥¹]¥¹‘½İ}±½Í¥¹œì(€€€€€€€€€€€±½Í” ¤ì(€€€€€€€€€€€MåÍÑ•´¹]¥¹‘½İÌ¹ÁÁ±¥…Ñ¥½¸¹ÕÉÉ•¹Ğ¹M¡ÕÑ‘½İ¸ ¤ì(€€€€€€€ô(€€€ô((€€€ÁÉ¥Ù…Ñ”…Íå¹ŒQ…Í¬¥ÍÁ½Í•ÁÁ±¥…Ñ¥½¹I•Í½ÕÉ•ÍÍå¹Œ ¤(€€€ì(€€€€€€€¥˜€¡}É•Í½ÕÉ•Í¥ÍÁ½Í•¤É•ÑÕÉ¸ì(€€€€€€€}É•Í½ÕÉ•Í¥ÍÁ½Í•€ôÑÉÕ”ì((€€€€€€€Ù…ÈÑÉ…ä€ô}ÑÉ…äì(€€€€€€€}ÑÉ…ä€ô¹Õ±°ì(€€€€€€€ÑÉ…äü¹¥ÍÁ½Í” ¤ì((€€€€€€€ÑÉä(€€€€€€€ì(€€€€€€€€€€€¥˜€¡}µ½¹¥Ñ½È¥Ì¹½Ğ¹Õ±°¤…İ…¥Ğ}µ½¹¥Ñ½È¹¥ÍÁ½Í•Íå¹Œ ¤ì(€€€€€€€ô(€€€€€€€™¥¹…±±ä(€€€€€€€ì(€€€€€€€€€€€}µ½¹¥Ñ½È€ô¹Õ±°ì(€€€€€€€€€€€}¹½Ñ¥™¥•È¹¥ÍÁ½Í” ¤ì(€€€€€€€ô(€€€ô((€€€ÁÉ¥Ù…Ñ”Í•…±•É•½É½µµ…¹‘¹ÑÉä¡ÍÑÉ¥¹œ%°ÍÑÉ¥¹œQ¥Ñ±”°ÍÑÉ¥¹œ•ÍÉ¥ÁÑ¥½¸°ÍÑÉ¥¹œM¡½ÉÑÕĞ¤ì)ô(