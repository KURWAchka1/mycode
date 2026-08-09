package app.playerokmonitor;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Insets;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class OrderDetailActivity extends Activity {
    static final String EXTRA_DEAL_ID = "deal_id";

    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private String dealId = "";
    private LinearLayout content;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Ui.prepareWindow(this);
        dealId = getIntent().getStringExtra(EXTRA_DEAL_ID);
        if (dealId == null) dealId = "";
        setContentView(buildRoot());
        render(OrdersRepository.findCached(this, dealId));
        sync(false);
    }

    private View buildRoot() {
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Ui.BG);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        int p = Ui.dp(this, Ui.isWide(this) ? 48 : 24);
        content.setPadding(p, p, p, p);
        scroll.addView(content, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT));
        content.setOnApplyWindowInsetsListener((v, insets) -> {
            int left = p, top = p, right = p, bottom = p;
            if (Build.VERSION.SDK_INT >= 30) {
                Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
                left += bars.left;
                top += bars.top;
                right += bars.right;
                bottom += bars.bottom;
            }
            v.setPadding(left, top, right, bottom);
            return insets;
        });
        return scroll;
    }

    private void render(OrderData order) {
        content.removeAllViews();

        LinearLayout head = new LinearLayout(this);
        head.setOrientation(LinearLayout.HORIZONTAL);
        head.setGravity(Gravity.CENTER_VERTICAL);
        content.addView(head, matchWrap());

        ImageButton back = Ui.iconButton(this, R.drawable.ic_nav_back, "Назад");
        back.setOnClickListener(v -> { Ui.haptic(v); finish(); });
        head.addView(back, new LinearLayout.LayoutParams(Ui.dp(this, 52), Ui.dp(this, 52)));

        String titleText = order == null ? "Сделка" : (order.isSale() ? "Моя продажа" : "Моя покупка");
        TextView title = Ui.text(this, titleText, 32, Ui.TEXT, true);
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        tp.leftMargin = Ui.dp(this, 10);
        head.addView(title, tp);

        ImageButton refresh = Ui.iconButton(this, R.drawable.ic_nav_refresh, "Обновить сделку");
        refresh.setOnClickListener(v -> { Ui.haptic(v); sync(true); });
        head.addView(refresh, new LinearLayout.LayoutParams(Ui.dp(this, 52), Ui.dp(this, 52)));

        if (order == null) {
            TextView missing = Ui.text(this,
                    "Сделка ещё не загружена. Обновите список или проверьте соединение с VPS.",
                    15, Ui.MUTED, false);
            missing.setGravity(Gravity.CENTER);
            missing.setPadding(0, Ui.dp(this, 60), 0, 0);
            content.addView(missing, matchWrap());
            return;
        }

        LinearLayout banner = new LinearLayout(this);
        banner.setOrientation(LinearLayout.VERTICAL);
        banner.setPadding(Ui.dp(this, 16), Ui.dp(this, 14), Ui.dp(this, 16), Ui.dp(this, 14));
        String bannerTitle;
        String bannerBody;
        int bannerTextColor;
        if (order.rolledBack) {
            banner.setBackground(Ui.roundedStroke(this, Ui.RED_BG, Ui.withAlpha(Ui.RED, 90), 20));
            bannerTitle = "ВОЗВРАТ ПО СДЕЛКЕ";
            bannerBody = "Возврат оформил: " + order.refundActorLabel();
            bannerTextColor = Ui.RED;
        } else if (order.problemActive) {
            banner.setBackground(Ui.roundedStroke(this, Ui.RED_BG, Ui.withAlpha(Ui.RED, 90), 20));
            bannerTitle = "ПРОБЛЕМА ПО СДЕЛКЕ";
            bannerBody = "Проблему создал: " + order.problemReporterLabel() + ". Проверьте сделку и чат как можно скорее.";
            bannerTextColor = Ui.RED;
        } else if (!order.problemResolvedAt.isEmpty()) {
            banner.setBackground(Ui.roundedStroke(this, Ui.GREEN_BG, Ui.withAlpha(Ui.GREEN, 90), 20));
            bannerTitle = "ПРОБЛЕМА РЕШЕНА";
            bannerBody = "Проблему решил: " + order.problemResolverLabel();
            bannerTextColor = Ui.GREEN;
        } else {
            banner.setBackground(Ui.roundedStroke(this, Ui.GREEN_BG, Ui.withAlpha(Ui.GREEN, 90), 20));
            bannerTitle = order.isSale() ? "ПРОДАЖА ОПЛАЧЕНА" : "ПОКУПКА ОПЛАЧЕНА";
            bannerBody = "Сделка сохранена в базе VPS";
            bannerTextColor = Ui.GREEN;
        }
        banner.addView(Ui.text(this, bannerTitle, 15, bannerTextColor, true));
        TextView bannerDetails = Ui.text(this, bannerBody, 14, bannerTextColor, false);
        LinearLayout.LayoutParams bp = matchWrap();
        bp.topMargin = Ui.dp(this, 6);
        banner.addView(bannerDetails, bp);
        LinearLayout.LayoutParams bannerParams = matchWrap();
        bannerParams.topMargin = Ui.dp(this, 16);
        content.addView(banner, bannerParams);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(Ui.dp(this, 16), Ui.dp(this, 16), Ui.dp(this, 16), Ui.dp(this, 16));
        card.setBackground(Ui.roundedStroke(this, Ui.CARD, Ui.BORDER, 20));
        LinearLayout.LayoutParams cp = matchWrap();
        cp.topMargin = Ui.dp(this, 14);
        content.addView(card, cp);

        card.addView(Ui.text(this, order.displayName(), 21, Ui.TEXT, true));
        TextView price = Ui.text(this, order.price.isEmpty() ? "Цена не указана" : order.priceSummary(), 25, Ui.ACCENT, true);
        LinearLayout.LayoutParams priceParams = matchWrap();
        priceParams.topMargin = Ui.dp(this, 8);
        card.addView(price, priceParams);

        String person = order.counterparty.isEmpty() ? "—" : "@" + order.counterparty;
        addField(card, order.counterpartyLabel(), person);
        addField(card, "Оплачено", Ui.formatDate(order.paidAt));
        if (
                order.isSale()
                        && "PROCESSING".equalsIgnoreCase(order.sellerNetStatus)
                        && !order.sellerNetAvailableAt.isEmpty()
        ) {
            addField(card, "Ожидаемое зачисление", Ui.formatDate(order.sellerNetAvailableAt));
        }
        addField(
                card,
                order.isSale() ? "Выполнение вами" : "Выполнение продавцом",
                order.sellerFulfilled ? "Подтверждено" : "Не подтверждено"
        );
        if (order.sellerFulfilled && !order.sellerFulfilledAt.isEmpty()) {
            addField(card, "Выполнение подтверждено", Ui.formatDate(order.sellerFulfilledAt));
        }
        addField(
                card,
                order.isSale() ? "Получение покупателем" : "Получение вами",
                order.recipientConfirmed
                        ? (order.recipientConfirmationAutomatic ? "Автоматически" : "Подтверждено")
                        : "Не подтверждено"
        );
        if (order.recipientConfirmed && !order.recipientConfirmedAt.isEmpty()) {
            addField(card, "Получение подтверждено", Ui.formatDate(order.recipientConfirmedAt));
        }
        if (order.recipientConfirmed && !order.recipientConfirmedByRelation.isEmpty()) {
            addField(card, "Получение подтвердил", order.recipientConfirmationActorLabel());
        }
        if (order.isSale()) {
            addField(card, "Автоответ", order.replySent ? "Отправлен" : "Ожидает отправки");
        }
        if (!order.problemReportedAt.isEmpty()) {
            addField(card, "Проблема создана", Ui.formatDate(order.problemReportedAt));
            addField(card, "Проблему создал", order.problemReporterLabel());
        }
        if (!order.problemResolvedAt.isEmpty()) {
            addField(card, "Проблема решена", Ui.formatDate(order.problemResolvedAt));
            addField(card, "Проблему решил", order.problemResolverLabel());
        }
        if (order.rolledBack) {
            addField(card, "Возврат оформлен", Ui.formatDate(order.rolledBackAt));
            addField(card, "Возврат оформил", order.refundActorLabel());
        }

        if (!order.buyerComment.isEmpty()) {
            LinearLayout note = new LinearLayout(this);
            note.setOrientation(LinearLayout.VERTICAL);
            note.setPadding(Ui.dp(this, 16), Ui.dp(this, 14), Ui.dp(this, 16), Ui.dp(this, 14));
            note.setBackground(Ui.roundedStroke(this, Ui.ACCENT_BG, Ui.BORDER, 20));
            LinearLayout.LayoutParams np = matchWrap();
            np.topMargin = Ui.dp(this, 14);
            content.addView(note, np);
            note.addView(Ui.text(this, order.isSale() ? "Комментарий покупателя" : "Комментарий к покупке", 14, Ui.ACCENT, true));
            TextView comment = Ui.text(this, order.buyerComment, 15, Ui.TEXT, false);
            LinearLayout.LayoutParams ccp = matchWrap();
            ccp.topMargin = Ui.dp(this, 7);
            note.addView(comment, ccp);
        }

        if (order.isSale() && order.relistEligible) addRelistCard(order);

        Button open = Ui.button(this, "", true);
        if (order.rolledBack) {
            open.setText("Открыть возврат в Playerok");
        } else if (order.problemActive) {
            open.setText("Открыть проблемную сделку");
        } else {
            open.setText("Открыть сделку в Playerok");
        }
        open.setCompoundDrawablesWithIntrinsicBounds(0, 0, R.drawable.ic_nav_open, 0);
        open.setCompoundDrawablePadding(Ui.dp(this, 8));
        open.setOnClickListener(v -> {
            Ui.haptic(v);
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(order.dealUrl)));
            } catch (Exception e) {
                toast("Не удалось открыть Playerok");
            }
        });
        LinearLayout.LayoutParams op = matchWrap();
        op.topMargin = Ui.dp(this, 14);
        content.addView(open, op);

        LinearLayout ids = new LinearLayout(this);
        ids.setOrientation(LinearLayout.VERTICAL);
        ids.setPadding(Ui.dp(this, 16), Ui.dp(this, 14), Ui.dp(this, 16), Ui.dp(this, 14));
        ids.setBackground(Ui.roundedStroke(this, Ui.CARD, Ui.BORDER, 20));
        LinearLayout.LayoutParams ip = matchWrap();
        ip.topMargin = Ui.dp(this, 14);
        content.addView(ids, ip);
        ids.addView(Ui.text(this, "Технические данные", 14, Ui.MUTED, true));
        TextView direction = Ui.text(this, "direction: " + order.direction, 12, Ui.MUTED, false);
        direction.setTypeface(Typeface.MONOSPACE);
        LinearLayout.LayoutParams dirp = matchWrap(); dirp.topMargin = Ui.dp(this, 8); ids.addView(direction, dirp);
        TextView deal = Ui.text(this, "deal: " + order.dealId, 12, Ui.MUTED, false);
        deal.setTypeface(Typeface.MONOSPACE);
        LinearLayout.LayoutParams dp = matchWrap(); dp.topMargin = Ui.dp(this, 4); ids.addView(deal, dp);
        TextView chat = Ui.text(this, "chat: " + order.chatId, 12, Ui.MUTED, false);
        chat.setTypeface(Typeface.MONOSPACE);
        LinearLayout.LayoutParams chp = matchWrap(); chp.topMargin = Ui.dp(this, 4); ids.addView(chat, chp);
        Ui.reveal(content);
    }

    private void addRelistCard(OrderData order) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(Ui.dp(this, 18), Ui.dp(this, 17), Ui.dp(this, 18), Ui.dp(this, 17));
        LinearLayout.LayoutParams params = matchWrap();
        params.topMargin = Ui.dp(this, 14);
        content.addView(card, params);

        if (order.isRelisted()) {
            card.setBackground(Ui.roundedStroke(this, Ui.GREEN_BG, Ui.withAlpha(Ui.GREEN, 80), 22));
            card.addView(Ui.text(this, "Выставлен снова", 18, Ui.GREEN, true));
            TextView details = Ui.text(
                    this,
                    "Исходная карточка и обложка сохранены. Для этого заказа лимит использован.",
                    14,
                    Ui.TEXT,
                    false
            );
            LinearLayout.LayoutParams detailsParams = matchWrap();
            detailsParams.topMargin = Ui.dp(this, 7);
            card.addView(details, detailsParams);
            if (!order.relistedAt.isEmpty()) addField(card, "Опубликован", Ui.formatDate(order.relistedAt));
            if (order.relistListingPrice > 0) addField(card, "Цена объявления", order.relistListingPrice + " ₽");
            addField(card, "Размещение", order.relistPriorityPrice <= 0 ? "Бесплатно" : order.relistPriorityPrice + " ₽");
            if (!order.relistedItemUrl.isEmpty()) {
                Button openItem = Ui.button(this, "Открыть товар", false);
                LinearLayout.LayoutParams buttonParams = matchWrap();
                buttonParams.topMargin = Ui.dp(this, 14);
                card.addView(openItem, buttonParams);
                openItem.setOnClickListener(v -> {
                    Ui.haptic(v);
                    openPlayerokUrl(order.relistedItemUrl);
                });
            }
            return;
        }

        card.setBackground(Ui.roundedStroke(this, Ui.ACCENT_BG, Ui.BORDER, 22));
        card.addView(Ui.text(this, "Выставить этот товар снова", 18, Ui.ACCENT, true));
        String description;
        boolean available = true;
        if (order.rolledBack) {
            description = "Недоступно: по заказу оформлен возврат.";
            available = false;
        } else if (order.problemActive) {
            description = "Недоступно, пока по заказу активна проблема.";
            available = false;
        } else if (!order.sellerFulfilled) {
            description = "Станет доступно после того, как вы подтвердите выполнение заказа на Playerok.";
            available = false;
        } else if ("PUBLISHING".equalsIgnoreCase(order.relistState)) {
            description = "Публикация уже выполняется на VPS. Повторный запрос не создаст второй товар.";
            available = false;
        } else if ("FAILED".equalsIgnoreCase(order.relistState)) {
            description = "Черновик сохранён. Можно заново проверить размещение и изменить Premium; второй товар не создастся.";
        } else {
            description = "Перед публикацией выберите новую цену и решите, нужно ли оплачивать Premium.";
        }
        TextView body = Ui.text(this, description, 14, Ui.TEXT, false);
        LinearLayout.LayoutParams bodyParams = matchWrap();
        bodyParams.topMargin = Ui.dp(this, 7);
        card.addView(body, bodyParams);

        Button relist = Ui.button(this, "Настроить публикацию", true);
        relist.setEnabled(available);
        relist.setAlpha(available ? 1f : 0.55f);
        LinearLayout.LayoutParams buttonParams = matchWrap();
        buttonParams.topMargin = Ui.dp(this, 14);
        card.addView(relist, buttonParams);
        if (available) {
            relist.setOnClickListener(v -> {
                Ui.haptic(v);
                loadRelistSetup(order, relist);
            });
        }
    }

    private void loadRelistSetup(OrderData order, Button button) {
        String pairingUrl = Prefs.getUrl(this);
        String validation = UrlTools.validatePairingUrl(pairingUrl);
        if (validation != null) {
            toast(validation);
            return;
        }
        button.setEnabled(false);
        button.setText("Проверяю Playerok…");
        network.execute(() -> {
            try {
                String raw = HttpTextClient.get(
                        UrlTools.relistSetupUrl(pairingUrl, order.dealId),
                        25_000
                );
                RelistOffer setup = RelistOffer.fromJson(raw);
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    if (setup.isPublished()) {
                        toast("Этот заказ уже был перевыставлен");
                        sync(false);
                    } else {
                        button.setEnabled(true);
                        button.setText("Настроить публикацию");
                        showRelistSetup(order, setup, button);
                    }
                });
            } catch (Exception e) {
                String message = serverMessage(e);
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    button.setEnabled(true);
                    button.setText("Настроить публикацию");
                    toast(message);
                });
            }
        });
    }

    private void showRelistSetup(OrderData order, RelistOffer setup, Button button) {
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        int horizontal = Ui.dp(this, 24);
        form.setPadding(horizontal, Ui.dp(this, 8), horizontal, 0);

        form.addView(Ui.text(
                this,
                setup.itemName.isEmpty() ? order.displayName() : setup.itemName,
                16,
                Ui.TEXT,
                true
        ));

        TextView priceLabel = Ui.text(this, "Цена нового объявления", 13, Ui.MUTED, true);
        LinearLayout.LayoutParams labelParams = matchWrap();
        labelParams.topMargin = Ui.dp(this, 18);
        form.addView(priceLabel, labelParams);

        EditText priceInput = new EditText(this);
        priceInput.setSingleLine(true);
        priceInput.setInputType(InputType.TYPE_CLASS_NUMBER);
        priceInput.setText(Integer.toString(Math.max(1, setup.itemPrice)));
        priceInput.setTextSize(19);
        priceInput.setTextColor(Ui.TEXT);
        priceInput.setHintTextColor(Ui.MUTED);
        priceInput.setPadding(
                Ui.dp(this, 16),
                Ui.dp(this, 13),
                Ui.dp(this, 16),
                Ui.dp(this, 13)
        );
        priceInput.setBackground(Ui.roundedStroke(this, Ui.CARD, Ui.BORDER, 18));
        priceInput.setEnabled(!setup.priceLocked);
        LinearLayout.LayoutParams inputParams = matchWrap();
        inputParams.topMargin = Ui.dp(this, 8);
        form.addView(priceInput, inputParams);

        if (setup.priceLocked) {
            TextView locked = Ui.text(
                    this,
                    "Черновик уже создан с этой ценой. Она заблокирована, чтобы повтор не создал второй товар.",
                    12,
                    Ui.MUTED,
                    false
            );
            LinearLayout.LayoutParams lockedParams = matchWrap();
            lockedParams.topMargin = Ui.dp(this, 7);
            form.addView(locked, lockedParams);
        } else if (setup.sourceItemPrice > 0) {
            TextView original = Ui.text(
                    this,
                    "Цена исходного объявления: " + setup.sourceItemPrice + " ₽",
                    12,
                    Ui.MUTED,
                    false
            );
            LinearLayout.LayoutParams originalParams = matchWrap();
            originalParams.topMargin = Ui.dp(this, 7);
            form.addView(original, originalParams);
        }

        Switch premium = new Switch(this);
        premium.setText("Оплатить Premium-продвижение");
        premium.setTextColor(Ui.TEXT);
        premium.setTextSize(15);
        premium.setGravity(Gravity.CENTER_VERTICAL);
        premium.setChecked(setup.priorityType.isEmpty() || setup.isPremium());
        premium.setPadding(0, Ui.dp(this, 12), 0, Ui.dp(this, 4));
        LinearLayout.LayoutParams premiumParams = matchWrap();
        premiumParams.topMargin = Ui.dp(this, 12);
        form.addView(premium, premiumParams);

        TextView premiumHint = Ui.text(
                this,
                "Выключите, чтобы использовать обычное размещение без оплаты Premium.",
                12,
                Ui.MUTED,
                false
        );
        LinearLayout.LayoutParams hintParams = matchWrap();
        hintParams.topMargin = Ui.dp(this, 2);
        form.addView(premiumHint, hintParams);

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("Параметры публикации")
                .setView(form)
                .setNegativeButton("Отмена", null)
                .setPositiveButton("Рассчитать условия", null)
                .create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(v -> {
                    String rawPrice = priceInput.getText().toString().trim();
                    int listingPrice;
                    try {
                        listingPrice = Integer.parseInt(rawPrice);
                    } catch (NumberFormatException e) {
                        priceInput.setError("Введите целую цену в рублях");
                        return;
                    }
                    if (listingPrice < 1 || listingPrice > 10_000_000) {
                        priceInput.setError("Допустимо от 1 до 10 000 000 ₽");
                        return;
                    }
                    String priorityType = premium.isChecked() ? "PREMIUM" : "DEFAULT";
                    dialog.dismiss();
                    loadRelistOffer(order, button, listingPrice, priorityType);
                }));
        dialog.show();
    }

    private void loadRelistOffer(
            OrderData order,
            Button button,
            int listingPrice,
            String priorityType
    ) {
        String pairingUrl = Prefs.getUrl(this);
        button.setEnabled(false);
        button.setText("Рассчитываю условия…");
        network.execute(() -> {
            try {
                String raw = HttpTextClient.get(
                        UrlTools.relistPreviewUrl(
                                pairingUrl,
                                order.dealId,
                                listingPrice,
                                priorityType
                        ),
                        25_000
                );
                RelistOffer offer = RelistOffer.fromJson(raw);
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    if (offer.isPublished()) {
                        toast("Этот заказ уже был перевыставлен");
                        sync(false);
                    } else {
                        button.setEnabled(true);
                        button.setText("Настроить публикацию");
                        showRelistConfirmation(order, offer, button);
                    }
                });
            } catch (Exception e) {
                String message = serverMessage(e);
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    button.setEnabled(true);
                    button.setText("Настроить публикацию");
                    new AlertDialog.Builder(this)
                            .setTitle("Не удалось рассчитать")
                            .setMessage(message)
                            .setPositiveButton("Изменить параметры", (d, which) -> loadRelistSetup(order, button))
                            .setNegativeButton("Закрыть", null)
                            .show();
                });
            }
        });
    }

    private void showRelistConfirmation(OrderData order, RelistOffer offer, Button button) {
        StringBuilder message = new StringBuilder();
        message.append(offer.itemName.isEmpty() ? order.displayName() : offer.itemName);
        message.append("\n\n").append(offer.feeLabel());
        if (offer.priorityPeriodDays > 0) {
            message.append(" · ").append(offer.priorityPeriodDays).append(" дней");
        }
        if (offer.itemPrice > 0) {
            message.append("\nЦена нового объявления: ").append(offer.itemPrice).append(" ₽");
            if (offer.sourceItemPrice > 0 && offer.sourceItemPrice != offer.itemPrice) {
                message.append("\nЦена исходного объявления: ")
                        .append(offer.sourceItemPrice).append(" ₽");
            }
        }
        if (offer.isPremium() && offer.priorityCalculationPrice > 0) {
            message.append("\nСтоимость Premium получена напрямую от Playerok для цены ")
                    .append(offer.priorityCalculationPrice).append(" ₽.");
        } else if (!offer.isPremium()) {
            message.append("\nPremium отключён: сервер выбрал обычный вариант Playerok.");
        }
        message.append("\nОбложка, описание и параметры останутся прежними.");
        message.append("\n\nДля этого заказа товар можно выставить снова только один раз. ");
        message.append("Повторный тап или сетевой сбой не создадут дубль.");
        message.append("\n\nНе продолжайте, если это уникальный аккаунт или единичный товар, ");
        message.append("который нельзя продавать повторно по правилам категории.");

        String positive;
        if (!offer.isPremium()) {
            positive = offer.priorityPrice <= 0
                    ? "Выставить бесплатно"
                    : "Оплатить размещение · " + offer.priorityPrice + " ₽";
        } else {
            positive = offer.priorityPrice <= 0
                    ? "Выставить с Premium"
                    : "Оплатить Premium · " + offer.priorityPrice + " ₽";
        }
        new AlertDialog.Builder(this)
                .setTitle("Подтвердить публикацию")
                .setMessage(message.toString())
                .setNegativeButton("Отмена", null)
                .setNeutralButton("Изменить", (dialog, which) -> showRelistSetup(order, offer, button))
                .setPositiveButton(positive, (dialog, which) -> executeRelist(order, offer, button))
                .show();
    }

    private void executeRelist(OrderData order, RelistOffer offer, Button button) {
        String pairingUrl = Prefs.getUrl(this);
        button.setEnabled(false);
        button.setText("Выставляю один раз…");
        network.execute(() -> {
            try {
                String raw = HttpTextClient.post(
                        UrlTools.relistExecuteUrl(
                                pairingUrl,
                                order.dealId,
                                offer.priorityId,
                                offer.priorityPrice,
                                offer.itemPrice,
                                offer.priorityType
                        ),
                        45_000
                );
                RelistOffer result = RelistOffer.fromJson(raw);
                if (!result.isPublished()) throw new IllegalStateException("Playerok не подтвердил публикацию");
                OrderData refreshed = null;
                try {
                    OrdersRepository.sync(this, pairingUrl);
                    refreshed = OrdersRepository.findCached(this, dealId);
                } catch (Exception ignored) {
                    // The immutable server receipt already proves success. A
                    // later normal sync will refresh the local order card.
                }
                OrderData updated = refreshed;
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    if (updated != null) render(updated);
                    showRelistSuccess(result);
                });
            } catch (Exception e) {
                String message = serverMessage(e);
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    button.setEnabled(true);
                    button.setText("Настроить публикацию");
                    new AlertDialog.Builder(this)
                            .setTitle("Не удалось выставить")
                            .setMessage(message + "\n\nЛимит заказа не расходуется без подтверждённой публикации.")
                            .setPositiveButton(
                                    "Проверить снова",
                                    (d, which) -> loadRelistOffer(
                                            order,
                                            button,
                                            offer.itemPrice,
                                            offer.priorityType
                                    )
                            )
                            .setNegativeButton("Закрыть", null)
                            .show();
                });
            }
        });
    }

    private void showRelistSuccess(RelistOffer result) {
        AlertDialog.Builder dialog = new AlertDialog.Builder(this)
                .setTitle("Товар опубликован")
                .setMessage("Использована исходная карточка с той же обложкой. Повторное перевыставление для этого заказа заблокировано.")
                .setNegativeButton("Готово", null);
        if (!result.itemUrl.isEmpty()) {
            dialog.setPositiveButton("Открыть товар", (d, which) -> openPlayerokUrl(result.itemUrl));
        }
        dialog.show();
    }

    private void openPlayerokUrl(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception e) {
            toast("Не удалось открыть Playerok");
        }
    }

    private static String serverMessage(Exception error) {
        String raw = error.getMessage();
        if (raw == null || raw.trim().isEmpty()) return "Неизвестная ошибка";
        int jsonStart = raw.indexOf('{');
        if (jsonStart >= 0) {
            try {
                return new JSONObject(raw.substring(jsonStart)).optString("message", raw);
            } catch (Exception ignored) {
                // Fall through to the original network message.
            }
        }
        return raw;
    }

    private void addField(LinearLayout parent, String label, String value) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams rp = matchWrap();
        rp.topMargin = Ui.dp(this, 14);
        parent.addView(row, rp);
        TextView l = Ui.text(this, label, 14, Ui.MUTED, false);
        row.addView(l, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        TextView v = Ui.text(this, value, 14, Ui.TEXT, true);
        v.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
        row.addView(v);
    }

    private void sync(boolean manual) {
        String url = Prefs.getUrl(this);
        if (UrlTools.validatePairingUrl(url) != null) return;
        network.execute(() -> {
            try {
                OrdersRepository.sync(this, url);
                OrderData updated = OrdersRepository.findCached(this, dealId);
                runOnUiThread(() -> render(updated));
            } catch (Exception e) {
                if (manual) runOnUiThread(() -> toast("Ошибка обновления: " + e.getMessage()));
            }
        });
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private void toast(String text) { Toast.makeText(this, text, Toast.LENGTH_SHORT).show(); }

    @Override protected void onResume() { super.onResume(); sync(false); }
    @Override protected void onDestroy() { network.shutdownNow(); super.onDestroy(); }
}
