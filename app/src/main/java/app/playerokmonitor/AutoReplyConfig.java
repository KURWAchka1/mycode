package app.playerokmonitor;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

final class AutoReplyConfig {
    static final String DEFAULT_MESSAGE =
            "Ожидайте, пожалуйста. Продавец скоро приступит к выполнению Вашего заказа.";
    static final String DEFAULT_FULFILLMENT_MESSAGE =
            "Заказ выполнен. Пожалуйста, проверьте товар и подтвердите получение, если всё в порядке.";
    static final int DEFAULT_MAX_MESSAGES = 8;

    final boolean enabled;
    final ArrayList<String> messages;
    final String defaultMessage;
    final String fulfillmentMessage;
    final String defaultFulfillmentMessage;
    final int maxMessages;

    private AutoReplyConfig(
            boolean enabled,
            ArrayList<String> messages,
            String defaultMessage,
            String fulfillmentMessage,
            String defaultFulfillmentMessage,
            int maxMessages
    ) {
        this.enabled = enabled;
        this.messages = messages;
        this.defaultMessage = defaultMessage;
        this.fulfillmentMessage = fulfillmentMessage;
        this.defaultFulfillmentMessage = defaultFulfillmentMessage;
        this.maxMessages = Math.max(1, maxMessages);
    }

    static AutoReplyConfig fromJson(String raw) throws Exception {
        JSONObject object = new JSONObject(raw);
        if (!object.optBoolean("ok", false)) {
            throw new IllegalStateException(object.optString("message", "VPS отклонил настройки"));
        }
        String defaultMessage = object.optString("default_message", DEFAULT_MESSAGE).trim();
        if (defaultMessage.isEmpty()) defaultMessage = DEFAULT_MESSAGE;
        ArrayList<String> messages = new ArrayList<>();
        JSONArray array = object.optJSONArray("messages");
        if (array != null) {
            for (int index = 0; index < array.length(); index++) {
                String message = array.optString(index, "").trim();
                if (!message.isEmpty()) messages.add(message);
            }
        }
        // Servers before 2.3.8 returned the effective default as editable text.
        // Treat that exact legacy value as an empty override so it becomes the
        // requested background hint after either side updates first.
        if (!object.has("effective_messages")
                && messages.size() == 1
                && defaultMessage.equals(messages.get(0))) {
            messages.clear();
        }
        String defaultFulfillmentMessage = object.optString(
                "default_fulfillment_message", DEFAULT_FULFILLMENT_MESSAGE).trim();
        if (defaultFulfillmentMessage.isEmpty()) {
            defaultFulfillmentMessage = DEFAULT_FULFILLMENT_MESSAGE;
        }
        String fulfillmentMessage = object.optString("fulfillment_message", "").trim();
        JSONObject limits = object.optJSONObject("limits");
        int max = limits == null ? DEFAULT_MAX_MESSAGES
                : limits.optInt("max_messages", DEFAULT_MAX_MESSAGES);
        return new AutoReplyConfig(
                object.optBoolean("enabled", true),
                messages,
                defaultMessage,
                fulfillmentMessage,
                defaultFulfillmentMessage,
                max
        );
    }

    static String requestJson(
            boolean enabled,
            List<String> messages,
            String fulfillmentMessage
    ) throws Exception {
        JSONObject object = new JSONObject();
        object.put("enabled", enabled);
        JSONArray array = new JSONArray();
        for (String message : messages) array.put(message == null ? "" : message);
        object.put("messages", array);
        object.put("fulfillment_message", fulfillmentMessage == null ? "" : fulfillmentMessage);
        return object.toString();
    }
}
