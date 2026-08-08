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
            outer.setPadding(0, Ui.dp(context, 6), 0, Ui.dp(context, 6));

            LinearLayout card = new LinearLayout(context);
            card.setOrientation(LinearLayout.VERTICAL);
            card.setPadding(Ui.dp(context, 18), Ui.dp(context, 16), Ui.dp(context, 18), Ui.dp(context, 16));
            outer.addView(card, new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT));

            LinearLayout top = new LinearLayout(context);
            top.setOrientation(LinearLayout.HORIZONTAL);
            top.setGravity(Gravity.CENTER_VERTICAL);
            card.addView(top, new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT));

            h.name = Ui.text(context, "", 16, Ui.TEXT, true);
            top.addView(h.name, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

            h.price = Ui.text(context, "", 16, Ui.TEXT, true);
            h.price.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
            top.addView(h.price);

            LinearLayout meta = new LinearLayout(context);
            meta.setOrientation(LinearLayout.HORIZONTAL);
            meta.setGravity(Gravity.CENTER_VERTICAL);
            LinearLayout.LayoutParams metaParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT);
            metaParams.topMargin = Ui.dp(context, 10);
            card.addView(meta, metaParams);

            h.status = Ui.text(context, "", 12, Ui.GREEN, true);
            h.status.setGravity(Gravity.CENTER);
            h.status.setPadding(Ui.dp(context, 10), Ui.dp(context, 5), Ui.dp(context, 10), Ui.dp(context, 5));
            meta.addView(h.status);

            h.counterparty = Ui.text(context, "", 13, Ui.MUTED, false);
            LinearLayout.LayoutParams personParams = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
            personParams.leftMargin = Ui.dp(context, 10);
            meta.addView(h.counterparty, personParams);

            h.date = Ui.text(context, "", 13, Ui.MUTED, false);
            h.date.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
            meta.addView(h.date);

            h.info = Ui.text(context, "", 13, Ui.MUTED, true);
            LinearLayout.LayoutParams infoParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT);
            infoParams.topMargin = Ui.dp(context, 10);
            card.addView(h.info, infoParams);

            convertView = outer;
            h.card = card;
            convertView.setTag(h);
        } else {
            h = (Holder) convertView.getTag();
        }

        OrderData order = orders.get(position);
        h.name.setText(order.displayName());
        h.price.setText(order.price.isEmpty() ? "—" : order.price);
        String person = order.counterparty.isEmpty() ? "—" : "@" + order.counterparty;
        h.counterparty.setText(order.counterpartyLabel() + ": " + person);
        h.date.setText(Ui.formatDate(order.paidAt));

        if (order.rolledBack) {
            h.status.setText("ВОЗВРАТ");
            h.status.setTextColor(Ui.RED);
            h.status.setBackground(Ui.rounded(context, Ui.RED_BG, 10));
            h.card.setBackground(Ui.roundedStroke(context, Ui.CARD, Ui.withAlpha(Ui.RED, 90), 20));
            h.info.setText("Возврат оформил: " + order.refundActorLabel() + "\n" + order.lifecycleSummary());
            h.info.setTextColor(Ui.RED);
            h.info.setVisibility(View.VISIBLE);
        } else if (order.problemActive) {
            h.status.setText("ПРОБЛЕМА");
            h.status.setTextColor(Ui.RED);
            h.status.setBackground(Ui.rounded(context, Ui.RED_BG, 10));
            h.card.setBackground(Ui.roundedStroke(context, Ui.CARD, Ui.withAlpha(Ui.RED, 90), 20));
            h.info.setText("Проблему создал: " + order.problemReporterLabel() + " — требуется реакция\n" + order.lifecycleSummary());
            h.info.setTextColor(Ui.RED);
            h.info.setVisibility(View.VISIBLE);
        } else if (!order.problemResolvedAt.isEmpty()) {
            h.status.setText("РЕШЕНО");
            h.status.setTextColor(Ui.GREEN);
            h.status.setBackground(Ui.rounded(context, Ui.GREEN_BG, 10));
            h.card.setBackground(Ui.roundedStroke(context, Ui.CARD, Ui.BORDER, 20));
            h.info.setText("Проблему решил: " + order.problemResolverLabel() + "\n" + order.lifecycleSummary());
            h.info.setTextColor(Ui.GREEN);
            h.info.setVisibility(View.VISIBLE);
        } else {
            h.status.setText("ОПЛАЧЕН");
            h.status.setTextColor(Ui.GREEN);
            h.status.setBackground(Ui.rounded(context, Ui.GREEN_BG, 10));
            h.card.setBackground(Ui.roundedStroke(context, Ui.CARD, Ui.BORDER, 20));
            h.info.setText(order.lifecycleSummary());
            h.info.setTextColor(Ui.MUTED);
            h.info.setVisibility(View.VISIBLE);
        }
        return convertView;
    }

    private static final class Holder {
        LinearLayout card;
        TextView name;
        TextView price;
        TextView status;
        TextView counterparty;
        TextView date;
        TextView info;
    }
}
