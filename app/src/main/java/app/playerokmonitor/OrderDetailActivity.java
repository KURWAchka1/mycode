package app.playerokmonitor;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Insets;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

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
        TextView price = Ui.text(this, order.price.isEmpty() ? "Цена не указана" : order.price, 25, Ui.ACCENT, true);
        LinearLayout.LayoutParams priceParams = matchWrap();
        priceParams.topMargin = Ui.dp(this, 8);
        card.addView(price, priceParams);

        String person = order.counterparty.isEmpty() ? "—" : "@" + order.counterparty;
        addField(card, order.counterpartyLabel(), person);
        addField(card, "Оплачено", Ui.formatDate(order.paidAt));
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
