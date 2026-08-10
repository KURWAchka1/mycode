# Playerok Monitor for Android 16

Android client for the Playerok Monitor VPS service.

- `compileSdk 36`, `targetSdk 36`, `minSdk 26`
- HTTPS long-poll to the user's VPS
- foreground monitoring service
- boot restore when monitoring was enabled
- dedicated high-importance order notification channel
- deterministic custom notification sound generated during the Gradle build
- system silent/vibrate/DND/channel sound settings remain authoritative
- CI builds, installs and launches the APK in an Android 16 emulator, then repeats the UI check at 200% system text size

## Build

```bash
gradle :app:assembleDebug
```

The CI artifact is named `PlayerokMonitor-2.3.10-OneUI85` and includes default, large-text and dark-mode screenshots alongside the APK.
