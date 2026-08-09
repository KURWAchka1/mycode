package app.playerokmonitor;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

final class AutoReplyConfig {
    static final String DEFAULT_MESSAGE =
            "Ожидайте, пожалуйста. Продавец скоро приступит к выполнению Вашего заказа.";
    static final int DEFAULT_MAX_MESSAGES = 8;

    final boolean enabled;
    final ArrayList<String> messages;
    final int maxMessages;

    private AutoReplyConfig(boolean enabled, ArrayList<String> messages, int maxMessages) {
        this.enabled = enabled;
        this.messages = messages;
        this.maxMessages = Math.max(1, maxMessages);
    }

    static AutoReplyConfig fromJson(String raw) throws Exception {
        JSONObject object = new JSONObject(raw);
        if (!object.optBoolean("ok", false)) {
            throw new IllegalStateException(object.optString("message", "VPS отклонил настройки"));
        }
        ArrayList<String> messages = new ArrayList<>();
        JSONArray array = object.optJSONArray("messages");
        if (array != null) {
            for (int index = 0; index < array.length(); index++) {
                String message = array.optString(index, "").trim();
                if (!message.isEmpty()) messages.add(message);
            }
        }
        if (messages.isEmpty()) messages.add(object.optString("default_message", DEFAULT_MESSAGE));
        JSONObject limits = object.optJSONObject("limits");
        int max = limits == null ? DEFAULT_MAX_MESSAGES
                : limits.optInt("max_messages", DEFAULT_MAX_MESSAGES);
        return new AutoReplyConfig(object.optBoolean("enabled", true), messages, max);
    }

    static String requestJson(boolean enabled, List<String> messages) throws Exception {
        JSONObject object = new JSONObject();
        object.put("enabled", enabled);
        JSONArray array = new JSONArray();
        for (String message : messages) array.put(message == null ? "" : message);
        object.put("messages", array);
        return object.toString();
    }
}
