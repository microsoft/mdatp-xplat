# Accessibility Example
Adds support for extracting and forwarding DLP accessibility settings from managed configuration to Endpoint DLP for macOS 27 AX-off handling (Golden Gate).

### Intune
This sample configuration profile sets both the Unallowed Browser Mode and Paste to Browser Mode flags for Accessibility: [com.microsoft.wdav.mobileconfig](./com.microsoft.wdav.mobileconfig).


### JAMF Pro

**Using schema.json**

Modify the existing MDE Prefereneces Configuration Profile to use the latest version of [schema.json](/macos/schema/schema.json). Then add the `Data Loss Prevention` key, and `Accessibility` subkey.  Add the individual Accessibility Flag here.

![Add Settings in JAMF Pro](JAMF_Pro_DLP_Accessibility.jpeg)

**Using plist**

Example plist file to exclude the com.azul.zulu.java signing ID: [com.microsoft.wdav.plist](./com.microsoft.wdav.plist).

