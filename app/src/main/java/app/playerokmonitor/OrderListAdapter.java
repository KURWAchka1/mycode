package app.playerokmonitor;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

final class OrderListAdapter extends BaseAdapter {
    private final Context context;
    private final ArrayList<OrderData> orders = new ArrayList<>();

    OrderListAdapter(Context context) { this.context = context; }

    void setOrders(List<OrderData> values) {
        orders.clear();
        if (values != null) orders.addAll(values);
        notifyDataSetChanged();
    }

    OrderData getOrder(int position) { return orders.get(position); }

    @Override public int getCount() { return orders.size(); }
    @Override public Object getItem(int position) { return orders.get(position); }
    @Override public long getItemId(int position) { return position; }

    @Override
    public View getView(int position, View convertView, ViewGroup parent) {
        Holder h;
        if (convertView == null) {
            h = new Holder();
            LinearLayout outer = new LinearLayout(context);
            outer.setOrientation(LinearLayout.VERTICAL);
            outer.setPadding(0, Ui.dp(context, 6), 0, Ui.dp(context, 5));

            LinearLayout card = new LinearLayout(context);
            card.setOrientation(LinearLayout.HORIZONTAL);
            card.setClipToOutline(true);
            Ui.elevate(card, 1);
            outer.addView(card, new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT));

            h.rail = new View(context);
            card.addView(h.rail, new LinearLayout.LayoutParams(
                    Ui.dp(context, 4),
                    LinearLayout.LayoutParams.MATCH_PARENT));

            LinearLayout body = new LinearLayout(context);
            body.setOrientation(LinearLayout.VERTICAL);
            body.setPadding(Ui.dp(context, 17), Ui.dp(context, 15),
                    Ui.dp(context, 17), Ui.dp(context, 16));
            card.addView(body, new LinearLayout.LayoutParams(
                    0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

            LinearLayout meta = new LinearLayout(context);
            meta.setOrientation(LinearLayout.HORIZONTAL);
            meta.setGravity(Gravity.CENTER_VERTICAL);
            body.addView(meta, new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT));

            h.status = Ui.text(context, "", 12, Ui.GREEN, true);
            h.status.setGravity(Gravity.CENTER);
            h.status.setPadding(Ui.dp(context, 10), Ui.dp(context, 5), Ui.dp(context, 10), Ui.dp(context, 5));
            meta.addView(h.status);

            h.rating = Ui.text(context, "", 14, Ui.AMBER, true);
            LinearLayout.LayoutParams ratingParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT);
            ratingParams.leftMargin = Ui.dp(context, 9);
            meta.addView(h.rating, ratingParams);

            h.date = Ui.text(context, "", 13, Ui.MUTED, false);
            h.date.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
            LinearLayout.LayoutParams dateParams = new LinearLayout.LayoutParams(
                    0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
            dateParams.leftMargin = Ui.dp(context, 10);
            meta.addView(h.date, dateParams);

            h.name = Ui.text(context, "", 18, Ui.TEXT, true);
            h.name.setMaxLines(3);
            LinearLayout.LayoutParams nameParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT);
            nameParams.topMargin = Ui.dp(context, 12);
            body.addView(h.name, nameParams);

            h.price = Ui.text(context, "", 18, Ui.ACCENT, true);
            LinearLayout.LayoutParams priceParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT);
            priceParams.topMargin = Ui.dp(context, 5);
            body.addView(h.price, priceParams);

            h.counterparty = Ui.text(context, "", 13, Ui.MUTED, false);
            LinearLayout.LayoutParams personParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT);
            personParams.topMargin = Ui.dp(context, 11);
            body.addView(h.counterparty, personParams);

            h.info = Ui.text(context, "", 13, Ui.MUTED, false);
            LinearLayout.LayoutParams infoParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT);
            infoParams.topMargin = Ui.dp(context, 6);
            body.addView(h.info, infoParams);

            convertView = outer;
            h.card = card;
            convertView.setTag(h);
        } else {
            h = (Holder) convertView.getTag();
        }

        OrderData order = orders.get(position);
        h.name.setText(order.displayName());
        h.price.setText(order.priceSummary());
        String person = order.counterparty.isEmpty() ? "—" : "@" + order.counterparty;
        h.counterparty.setText(order.counterpartyLabel() + ": " + person);
        h.date.setText(Ui.formatDate(order.paidAt));
        h.rating.setText(order.reviewStars());
        h.rating.setVisibility(order.hasReview() ? View.VISIBLE : View.GONE);

        if (order.rolledBack) {
            h.status.setText("ВОЗВРАТ");
            h.status.setTextColor(Ui.RED);
            h.status.setBackground(Ui.rounded(context, Ui.RED_BG, 10));
            h.rail.setBackgroundColor(Ui.RED);
            h.card.setBackground(Ui.roundedStroke(context, Ui.CARD, Ui.withAlpha(Ui.RED, 60), 22));
            h.info.setText("Возврат оформил: " + order.refundActorLabel() + "\n" + order.lifecycleSummary());
            h.info.setTextColor(Ui.RED);
            h.info.setVisibility(View.VISIBLE);
        } else if (order.problemActive) {
            h.status.setText("ПРОБЛЕМА");
            h.status.setTextColor(Ui.RED);
            h.status.setBackground(Ui.rounded(context, Ui.RED_BG, 10));
            h.rail.setBackgroundColor(Ui.RED);
            h.card.setBackground(Ui.roundedStroke(context, Ui.CARD, Ui.withAlpha(Ui.RED, 60), 22));
            h.info.setText("Проблему создал: " + order.problemReporterLabel() + " — требуется реакция\n" + order.lifecycleSummary());
            h.info.setTextColor(Ui.RED);
            h.info.setVisibility(View.VISIBLE);
        } else if (!order.problemResolvedAt.isEmpty()) {
            h.status.setText("РЕШЕНО");
            h.status.setTextColor(Ui.GREEN);
            h.status.setBackground(Ui.rounded(context, Ui.GREEN_BG, 10));
            h.rail.setBackgroundColor(Ui.GREEN);
            h.card.setBackground(Ui.roundedStroke(context, Ui.CARD, Ui.BORDER, 22));
            h.info.setText("Проблему решил: " + order.problemResolverLabel() + "\n" + order.lifecycleSummary());
            h.info.setTextColor(Ui.GREEN);
            h.info.setVisibility(View.VISIBLE);
        } else {
            int stateColor;
            int stateBackground;
            if (order.sellerFulfilled && order.recipientConfirmed) {
                h.status.setText("ЗАВЕРШЁН");
                stateColor = Ui.GREEN;
                stateBackground = Ui.GREEN_BG;
            } else if (order.sellerFulfilled) {
                h.status.setText("ВЫПОЛНЕНО");
                stateColor = Ui.ACCENT;
                stateBackground = Ui.ACCENT_BG;
            } else if (order.isSale()) {
                h.status.setText("НОВЫЙ");
                stateColor = Ui.AMBER;
                stateBackground = Ui.AMBER_BG;
            } else {
                h.status.setText("ОПЛАЧЕН");
                stateColor = Ui.ACCENT;
                stateBackground = Ui.ACCENT_BG;
            }
            h.status.setTextColor(stateColor);
            h.status.setBackground(Ui.rounded(context, stateBackground, 10));
            h.rail.setBackgroundColor(stateColor);
            h.card.setBackground(Ui.roundedStroke(context, Ui.CARD, Ui.BORDER, 22));
            h.info.setText(order.lifecycleSummary());
            h.info.setTextColor(Ui.MUTED);
            h.info.setVisibility(View.VISIBLE);
        }
        return convertView;
    }

    private static final class Holder {
        LinearLayout card;
        View rail;
        TextView name;
        TextView price;
        TextView status;
        TextView rating;
        TextView counterparty;
        TextView date;
        TextView info;
    }
}
