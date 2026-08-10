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
    static final String DEFAULT_SLEEP_MESSAGE =
            "Сейчас продавец может спать. Он увидит заказ после пробуждения и напишет вам.";
    static final int DEFAULT_MAX_MESSAGES = 8;

    final boolean enabled;
    final ArrayList<String> messages;
    final String defaultMessage;
    final String fulfillmentMessage;
    final String defaultFulfillmentMessage;
    final boolean sleepEnabled;
    final String sleepStart;
    final String sleepEnd;
    final String sleepTimezone;
    final String sleepMessage;
    final String defaultSleepMessage;
    final int maxMessages;

    private AutoReplyConfig(
            boolean enabled,
            ArrayList<String> messages,
            String defaultMessage,
            String fulfillmentMessage,
            String defaultFulfillmentMessage,
            boolean sleepEnabled,
            String sleepStart,
            String sleepEnd,
            String sleepTimezone,
            String sleepMessage,
            String defaultSleepMessage,
            int maxMessages
    ) {
        this.enabled = enabled;
        this.messages = messages;
        this.defaultMessage = defaultMessage;
        this.fulfillmentMessage = fulfillmentMessage;
        this.defaultFulfillmentMessage = defaultFulfillmentMessage;
        this.sleepEnabled = sleepEnabled;
        this.sleepStart = sleepStart;
        this.sleepEnd = sleepEnd;
        this.sleepTimezone = sleepTimezone;
        this.sleepMessage = sleepMessage;
        this.defaultSleepMessage = defaultSleepMessage;
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
        String defaultSleepMessage = object.optString(
                "default_sleep_message", DEFAULT_SLEEP_MESSAGE).trim();
        if (defaultSleepMessage.isEmpty()) defaultSleepMessage = DEFAULT_SLEEP_MESSAGE;
        String sleepMessage = object.optString("sleep_message", "").trim();
        String sleepStart = object.optString("sleep_start", "00:00").trim();
        String sleepEnd = object.optString("sleep_end", "08:00").trim();
        String sleepTimezone = object.optString("sleep_timezone", "Europe/Moscow").trim();
        JSONObject limits = object.optJSONObject("limits");
        int max = limits == null ? DEFAULT_MAX_MESSAGES
                : limits.optInt("max_messages", DEFAULT_MAX_MESSAGES);
        return new AutoReplyConfig(
                object.optBoolean("enabled", true),
                messages,
                defaultMessage,
                fulfillmentMessage,
                defaultFulfillmentMessage,
                object.optBoolean("sleep_enabled", false),
                sleepStart.isEmpty() ? "00:00" : sleepStart,
                sleepEnd.isEmpty() ? "08:00" : sleepEnd,
                sleepTimezone.isEmpty() ? "Europe/Moscow" : sleepTimezone,
                sleepMessage,
                defaultSleepMessage,
                max
        );
    }

    static String requestJson(
            boolean enabled,
            List<String> messages,
            String fulfillmentMessage,
            boolean sleepEnabled,
            String sleepStart,
            String sleepEnd,
            String sleepTimezone,
            String sleepMessage
    ) throws Exception {
        JSONObject object = new JSONObject();
        object.put("enabled", enabled);
        JSONArray array = new JSONArray();
        for (String message : messages) array.put(message == null ? "" : message);
        object.put("messages", array);
        object.put("fulfillment_message", fulfillmentMessage == null ? "" : fulfillmentMessage);
        object.put("sleep_enabled", sleepEnabled);
        object.put("sleep_start", sleepStart == null ? "00:00" : sleepStart);
        object.put("sleep_end", sleepEnd == null ? "08:00" : sleepEnd);
        object.put("sleep_timezone", sleepTimezone == null ? "Europe/Moscow" : sleepTimezone);
        object.put("sleep_message", sleepMessage == null ? "" : sleepMessage);
        return object.toString();
    }
}
