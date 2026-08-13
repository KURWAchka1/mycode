#!/usr/bin/env bash
set -Eeuo pipefail

APK="app/build/outputs/apk/release/app-release.apk"
PACKAGE="app.playerokmonitor"
ACTIVITY="app.playerokmonitor/.MainActivity"

[[ -s "$APK" ]] || { echo "APK not found: $APK" >&2; exit 1; }

echo "Installing $APK"
adb install -r "$APK"

# The real app asks the user for notification permission. In unattended CI we
# grant it first so Android's PermissionController does not become the resumed
# Activity and invalidate the launch check.
adb shell pm grant "$PACKAGE" android.permission.POST_NOTIFICATIONS
adb shell am force-stop "$PACKAGE"
adb logcat -c

echo "Launching $ACTIVITY"
adb shell am start -W -n "$ACTIVITY"
sleep 5

PID="$(adb shell pidof "$PACKAGE" 2>/dev/null | tr -d '\r' || true)"
if [[ -z "$PID" ]]; then
    echo "ERROR: application process is not alive after launch" >&2
    echo "--- crash buffer ---" >&2
    adb logcat -d -b crash || true
    echo "--- relevant main log ---" >&2
    adb logcat -d | grep -E 'AndroidRuntime|FATAL EXCEPTION|app\.playerokmonitor' | tail -200 || true
    exit 1
fi

if ! adb shell dumpsys activity activities | grep -F "$ACTIVITY"; then
    echo "ERROR: MainActivity is not present in the activity stack" >&2
    adb shell dumpsys activity activities | tail -250 >&2 || true
    exit 1
fi

adb shell uiautomator dump /sdcard/playerok-window.xml >/dev/null
WINDOW_XML="$(adb shell cat /sdcard/playerok-window.xml | tr -d '\r')"
grep -F "Новые заказы" <<<"$WINDOW_XML"
grep -F "Playerok Заказы" <<<"$WINDOW_XML"
adb pull /sdcard/playerok-window.xml android16-main-default.xml >/dev/null
adb exec-out screencap -p > android16-main-default.png

# Horizontal gestures on the content area switch only adjacent tabs. Verify
# both directions while the ListView/empty ScrollView keep their normal touch
# handling for vertical scrolling and item clicks.
adb shell input swipe 900 1100 180 1100 420
sleep 1
adb shell uiautomator dump /sdcard/playerok-window-swipe-sales.xml >/dev/null
adb pull /sdcard/playerok-window-swipe-sales.xml android16-main-swipe-sales.xml >/dev/null
python3 - <<'PY'
import xml.etree.ElementTree as ET

node = next(node for node in ET.parse("android16-main-swipe-sales.xml").iter("node")
            if node.attrib.get("text") == "Продажи")
if node.attrib.get("selected") != "true":
    raise SystemExit("left swipe did not select Продажи")
PY
adb shell input swipe 180 1100 900 1100 420
sleep 1
adb shell uiautomator dump /sdcard/playerok-window-swipe-new.xml >/dev/null
adb pull /sdcard/playerok-window-swipe-new.xml android16-main-swipe-new.xml >/dev/null
python3 - <<'PY'
import xml.etree.ElementTree as ET

node = next(node for node in ET.parse("android16-main-swipe-new.xml").iter("node")
            if node.attrib.get("text") == "Новые заказы")
if node.attrib.get("selected") != "true":
    raise SystemExit("right swipe did not return to Новые заказы")
PY

# At an intermediate font scale the longest label can wrap while the other
# two remain on one line. All three tab containers must still share one bottom
# coordinate so the selected indicator never jumps vertically.
adb shell settings put system font_scale 1.3
adb shell am force-stop "$PACKAGE"
adb shell am start -W -n "$ACTIVITY" >/dev/null
sleep 3
adb shell uiautomator dump /sdcard/playerok-window-wrapped-tabs.xml >/dev/null
adb pull /sdcard/playerok-window-wrapped-tabs.xml android16-main-wrapped-tabs.xml >/dev/null
python3 - <<'PY'
import re
import xml.etree.ElementTree as ET

labels = {"Новые заказы", "Продажи", "Покупки"}
nodes = [node for node in ET.parse("android16-main-wrapped-tabs.xml").iter("node")
         if node.attrib.get("text") in labels]
if len(nodes) != 3:
    raise SystemExit(f"expected 3 tabs, found {len(nodes)}")
bottoms = [int(re.findall(r"\d+", node.attrib["bounds"])[3]) for node in nodes]
if len(set(bottoms)) != 1:
    raise SystemExit(f"tab bottoms are not aligned: {bottoms}")
print(f"Tab indicators share bottom={bottoms[0]}")
PY
adb exec-out screencap -p > android16-main-wrapped-tabs.png

# Samsung's accessibility guidance requires content to survive substantially
# enlarged text. Relaunch at 200% and assert that the complete tab label is
# still present; its WRAP_CONTENT height must grow instead of clipping.
adb shell settings put system font_scale 2.0
adb shell am force-stop "$PACKAGE"
adb shell am start -W -n "$ACTIVITY" >/dev/null
sleep 3
adb shell uiautomator dump /sdcard/playerok-window-large-text.xml >/dev/null
LARGE_WINDOW_XML="$(adb shell cat /sdcard/playerok-window-large-text.xml | tr -d '\r')"
grep -F "Новые заказы" <<<"$LARGE_WINDOW_XML"
grep -F "Продажи" <<<"$LARGE_WINDOW_XML"
grep -F "Playerok Заказы" <<<"$LARGE_WINDOW_XML"
adb pull /sdcard/playerok-window-large-text.xml android16-main-large-text.xml >/dev/null
adb exec-out screencap -p > android16-main-large-text.png

# The third label intentionally moves off-screen instead of being squeezed.
# Swipe the adaptive tab row and confirm that it remains reachable in full.
TAB_Y="$(python3 - <<'PY'
import re
import xml.etree.ElementTree as ET

root = ET.parse("android16-main-large-text.xml")
tabs = next(node for node in root.iter("node")
            if node.attrib.get("class") == "android.widget.HorizontalScrollView")
left, top, right, bottom = map(int, re.findall(r"\d+", tabs.attrib["bounds"]))
print((top + bottom) // 2)
PY
)"
adb shell input swipe 900 "$TAB_Y" 180 "$TAB_Y" 450
sleep 1
adb shell uiautomator dump /sdcard/playerok-window-large-text-scrolled.xml >/dev/null
SCROLLED_WINDOW_XML="$(adb shell cat /sdcard/playerok-window-large-text-scrolled.xml | tr -d '\r')"
grep -F "Покупки" <<<"$SCROLLED_WINDOW_XML"
adb pull /sdcard/playerok-window-large-text-scrolled.xml android16-main-large-text-scrolled.xml >/dev/null
adb exec-out screencap -p > android16-main-large-text-scrolled.png

# Vertical content movement must never take the compact app bar or tabs away.
adb shell input swipe 540 2100 540 1100 450
sleep 1
adb shell uiautomator dump /sdcard/playerok-window-pinned.xml >/dev/null
PINNED_WINDOW_XML="$(adb shell cat /sdcard/playerok-window-pinned.xml | tr -d '\r')"
grep -F "Playerok Заказы" <<<"$PINNED_WINDOW_XML"
grep -F "Продажи" <<<"$PINNED_WINDOW_XML"

# The user's Galaxy runs the dark palette. Exercise the night resources and
# transparent controls as a separate launch instead of trusting theme XML.
adb shell settings put system font_scale 1.0
adb shell cmd uimode night yes
adb shell am force-stop "$PACKAGE"
adb shell am start -W -n "$ACTIVITY" >/dev/null
sleep 3
adb shell uiautomator dump /sdcard/playerok-window-dark.xml >/dev/null
DARK_WINDOW_XML="$(adb shell cat /sdcard/playerok-window-dark.xml | tr -d '\r')"
grep -F "Новые заказы" <<<"$DARK_WINDOW_XML"
grep -F "Playerok Заказы" <<<"$DARK_WINDOW_XML"
adb pull /sdcard/playerok-window-dark.xml android16-main-dark.xml >/dev/null
adb exec-out screencap -p > android16-main-dark.png

# The sleep editor is a native settings section: it must remain reachable in
# the same large-text-safe scroll container and expose the configured interval.
read -r SETTINGS_X SETTINGS_Y < <(python3 - <<'PY'
import re
import xml.etree.ElementTree as ET

root = ET.parse("android16-main-dark.xml")
settings = next(node for node in root.iter("node")
                if node.attrib.get("content-desc") == "Настройки")
left, top, right, bottom = map(int, re.findall(r"\d+", settings.attrib["bounds"]))
print((left + right) // 2, (top + bottom) // 2)
PY
)
adb shell input tap "$SETTINGS_X" "$SETTINGS_Y"
sleep 2
adb shell dumpsys activity activities | grep -F "$PACKAGE/.SettingsActivity"
adb shell uiautomator dump /sdcard/playerok-settings-top.xml >/dev/null
SETTINGS_TOP_XML="$(adb shell cat /sdcard/playerok-settings-top.xml | tr -d '\r')"
grep -F "Проверить обновления приложения" <<<"$SETTINGS_TOP_XML"
grep -F "Версия 2.3.18" <<<"$SETTINGS_TOP_XML"
for _ in 1 2 3 4; do adb shell input swipe 540 2050 540 700 350; done
sleep 1
adb shell uiautomator dump /sdcard/playerok-settings-sleep.xml >/dev/null
SETTINGS_XML="$(adb shell cat /sdcard/playerok-settings-sleep.xml | tr -d '\r')"
grep -F "Когда я могу спать" <<<"$SETTINGS_XML"
grep -F "Предупреждать покупателя" <<<"$SETTINGS_XML"
grep -F "С 00:00" <<<"$SETTINGS_XML"
grep -F "До 08:00" <<<"$SETTINGS_XML"
adb pull /sdcard/playerok-settings-sleep.xml android16-settings-sleep.xml >/dev/null
adb exec-out screencap -p > android16-settings-sleep.png

if adb logcat -d -b crash | grep -F "$PACKAGE"; then
    echo "ERROR: application crash detected" >&2
    exit 1
fi

echo "Smoke test OK: package=$PACKAGE pid=$PID"
