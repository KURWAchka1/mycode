using System.Diagnostics;
using System.Windows;
using PlayerokMonitor.Core;
using MessageBox = System.Windows.MessageBox;

namespace PlayerokMonitor.Desktop;

public partial class RelistWindow : Window
{
    private readonly PlayerokClient _client;
    private readonly Order _order;
    private RelistOffer? _setup;
    private RelistOffer? _offer;

    public RelistWindow(PlayerokClient client, Order order)
    {
        _client = client;
        _order = order;
        InitializeComponent();
        WindowWorkArea.Attach(this);
        Loaded += RelistWindow_Loaded;
    }

    private async void RelistWindow_Loaded(object sender, RoutedEventArgs e)
    {
        PreviewButton.IsEnabled = false;
        try
        {
            _setup = await _client.GetRelistSetupAsync(_order.DealId);
            EnsureSuccess(_setup);
            if (_setup.IsPublished)
            {
                ShowPublished(_setup);
                return;
            }
            ItemTitle.Text = string.IsNullOrWhiteSpace(_setup.ItemName) ? _order.DisplayName : _setup.ItemName;
            var defaultPrice = Math.Max(1, _setup.ItemPrice > 0 ? _setup.ItemPrice : _setup.SourceItemPrice);
            PriceBox.Text = _setup.PriceLocked || _setup.PriceCustomized ? defaultPrice.ToString() : "";
            PriceBox.IsEnabled = !_setup.PriceLocked;
            PriceHint.Text = _setup.PriceLocked ? "Цена закреплена за уже созданным черновиком" : $"Если оставить пустым: {defaultPrice:N0} ₽ — цена проданного товара без скидки";
            PremiumCheck.IsChecked = string.IsNullOrWhiteSpace(_setup.PriorityType) || _setup.IsPremium;
            PreviewButton.IsEnabled = true;
            StatusText.Text = _setup.HasCover || _setup.CoverPreserved ? "Исходная обложка найдена и будет сохранена." : "Сервер проверит обложку ещё раз перед публикацией.";
        }
        catch (Exception error) { StatusText.Text = error.Message; }
    }

    private async void PreviewButton_Click(object sender, RoutedEventArgs e)
    {
        if (_setup is null) return;
        var defaultPrice = Math.Max(1, _setup.ItemPrice > 0 ? _setup.ItemPrice : _setup.SourceItemPrice);
        var raw = PriceBox.Text.Trim();
        if (!string.IsNullOrEmpty(raw) && (!int.TryParse(raw, out var parsed) || parsed is < 1 or > 10_000_000))
        {
            StatusText.Text = "Введите целую цену от 1 до 10 000 000 ₽";
            PriceBox.Focus();
            return;
        }
        var price = string.IsNullOrEmpty(raw) ? defaultPrice : int.Parse(raw);
        SetBusy(true, "Получаю актуальную стоимость у Playerok…");
        try
        {
            _offer = await _client.PreviewRelistAsync(_order.DealId, price, PremiumCheck.IsChecked == true);
            EnsureSuccess(_offer);
            if (_offer.IsPublished) { ShowPublished(_offer); return; }
            OfferFee.Text = _offer.FeeLabel;
            OfferDetails.Text = $"Цена объявления: {_offer.ItemPrice:N0} ₽" + (_offer.PriorityPeriodDays > 0 ? $"\nПериод продвижения: {_offer.PriorityPeriodDays} дн." : "") + (_offer.IsPremium && _offer.PriorityCalculationPrice > 0 ? $"\nPremium рассчитан Playerok для цены {_offer.PriorityCalculationPrice:N0} ₽." : "\nPremium отключён — выбрано обычное размещение.");
            PublishButton.Content = _offer.PriorityPrice <= 0 ? "Выставить бесплатно" : _offer.IsPremium ? $"Оплатить Premium · {_offer.PriorityPrice:N0} ₽" : $"Оплатить размещение · {_offer.PriorityPrice:N0} ₽";
            OfferCard.Visibility = Visibility.Visible;
            StatusText.Text = "Условия закреплены за этим заказом. Измените параметры, чтобы пересчитать их.";
        }
        catch (Exception error) { StatusText.Text = error.Message; OfferCard.Visibility = Visibility.Collapsed; }
        finally { SetBusy(false, null); }
    }

    private async void PublishButton_Click(object sender, RoutedEventArgs e)
    {
        if (_offer is null) return;
        var warning = $"Будет опубликован один товар по цене {_offer.ItemPrice:N0} ₽.\n{_offer.FeeLabel}\n\nОбложка и параметры останутся прежними. Повторно использовать этот заказ будет нельзя.";
        if (MessageBox.Show(this, warning, "Подтвердить публикацию?", MessageBoxButton.OKCancel, MessageBoxImage.Warning) != MessageBoxResult.OK) return;
        SetBusy(true, "Публикую один раз…");
        try
        {
            var result = await _client.ExecuteRelistAsync(_order.DealId, _offer);
            EnsureSuccess(result);
            if (!result.IsPublished) throw new InvalidOperationException("Playerok не подтвердил публикацию");
            ShowPublished(result);
            DialogResult = true;
        }
        catch (Exception error)
        {
            StatusText.Text = error.Message + " Повторная проверка безопасна: сервер не создаст второй товар.";
            SetBusy(false, null);
        }
    }

    private void ShowPublished(RelistOffer result)
    {
        ItemTitle.Text = "Товар уже выставлен";
        PriceBox.IsEnabled = false;
        PremiumCheck.IsEnabled = false;
        PreviewButton.Visibility = Visibility.Collapsed;
        OfferCard.Visibility = Visibility.Visible;
        OfferFee.Text = "Публикация подтверждена";
        OfferDetails.Text = $"Цена: {result.ItemPrice:N0} ₽\nОбложка сохранена. Лимит этого заказа использован.";
        PublishButton.Content = "Открыть товар";
        PublishButton.IsEnabled = !string.IsNullOrWhiteSpace(result.EffectiveItemUrl);
        PublishButton.Click -= PublishButton_Click;
        PublishButton.Click += (_, _) =>
        {
            if (!string.IsNullOrWhiteSpace(result.EffectiveItemUrl)) Process.Start(new ProcessStartInfo(result.EffectiveItemUrl) { UseShellExecute = true });
        };
        StatusText.Text = "Повторное выставление для этого заказа заблокировано сервером.";
    }

    private static void EnsureSuccess(RelistOffer offer)
    {
        if (!offer.Ok) throw new InvalidOperationException(string.IsNullOrWhiteSpace(offer.Message) ? "VPS отклонил запрос" : offer.Message);
    }

    private void SetBusy(bool busy, string? message)
    {
        PreviewButton.IsEnabled = !busy && _setup is not null && !_setup.IsPublished;
        PublishButton.IsEnabled = !busy;
        if (message is not null) StatusText.Text = message;
    }

    private void CloseButton_Click(object sender, RoutedEventArgs e) => Close();
}
