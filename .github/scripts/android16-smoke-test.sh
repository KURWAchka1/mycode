#!/usr/bin/env bash
set -Eeuo pipefail

APK="app/build/outputs/apk/debug/app-debug.apk"
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
grep -F "Заказы" <<<"$WINDOW_XML"
adb pull /sdcard/playerok-window.xml android16-main-default.xml >/dev/null
adb exec-out screencap -p > android16-main-default.png

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
adb pull /sdcard/playerok-window-large-text.xml android16-main-large-text.xml >/dev/null
adb exec-out screencap -p > android16-main-large-text.png

# The third label intentionally moves off-screen instead of being squeezed.
# Swipe the adaptive tab row and confirm that it remains reachable in full.
adb shell input swipe 900 1500 180 1500 450
sleep 1
adb shell uiautomator dump /sdcard/playerok-window-large-text-scrolled.xml >/dev/null
SCROLLED_WINDOW_XML="$(adb shell cat /sdcard/playerok-window-large-text-scrolled.xml | tr -d '\r')"
grep -F "Покупки" <<<"$SCROLLED_WINDOW_XML"
adb pull /sdcard/playerok-window-large-text-scrolled.xml android16-main-large-text-scrolled.xml >/dev/null
adb exec-out screencap -p > android16-main-large-text-scrolled.png

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
adb pull /sdcard/playerok-window-dark.xml android16-main-dark.xml >/dev/null
adb exec-out screencap -p > android16-main-dark.png

if adb logcat -d -b crash | grep -F "$PACKAGE"; then
    echo "ERROR: application crash detected" >&2
    exit 1
fi

echo "Smoke test OK: package=$PACKAGE pid=$PID"
