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

if adb logcat -d -b crash | grep -F "$PACKAGE"; then
    echo "ERROR: application crash detected" >&2
    exit 1
fi

echo "Smoke test OK: package=$PACKAGE pid=$PID"
