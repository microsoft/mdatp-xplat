# HelloDefender Android App

This is the default app used by the `android-studio` performance-profile scenario.

## What Is Included

- Android app package: `com.microsoft.mdatp.xplat.hellodefender`
- Launch activity: `MainActivity`
- UI marker view id: `helloTitle`
- Unit test: `HelloDefenderUnitTest`
- Instrumentation test: `HelloDefenderInstrumentedTest`

## Build Bootstrap

`gradlew` in this folder is a repository-local bootstrap script that downloads the Gradle distribution from `gradle/wrapper/gradle-wrapper.properties` into `.gradle/wrapper/dists` and then runs Gradle tasks.

## Scenario Workflow

The `android-studio` scenario runs this sequence for both baseline and optimized phases:

1. `clean`
2. `connectedDebugAndroidTest` (default-on)
3. `assembleDebug`
4. `adb install -r app-debug.apk`
5. `adb shell am start ...`

## Requirements

- Android Studio installed (default location: `/Applications/Android Studio.app`)
- Android SDK installed via Android Studio (the scenario auto-detects the default SDK path `~/Library/Android/sdk`)
- At least one Android Virtual Device (AVD) created in Android Studio Device Manager
	- Android Studio -> Tools -> Device Manager -> Create device
	- Verify AVDs exist with `emulator -list-avds`
- At least one emulator bootable for connected tests (recommended: start an AVD once before running the demo)

## Run

From `macos/performance-profiles`:

```bash
python3 demo.py android-studio
```
