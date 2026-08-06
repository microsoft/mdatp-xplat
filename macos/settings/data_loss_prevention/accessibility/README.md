# Process Accessibility Example
Adds support for extracting and forwarding DLP accessibility settings from managed configuration to Endpoint DLP for macOS 27 AX-off handling (Golden Gate).

### Intune
For Intune users, create a configuration profile to add accessibility setting specific to Unallowed Browser Mode and Paste to Browser Mode from DLP enforcement.
Example mobileconfig file for accessibility -> enforcement -> unallowedBrowserMode: audit.

### JAMF Pro
For Jamf Pro users, create a configuration profile under Application & Custom Settings with the following:
- Preferences Domain: com.microsoft.wdav.ext

- Scope: Required groups/users

**Using schema.json**

Modify the MDE Preferences Configuration Profile to use the latest version of [schema.json](/macos/schema/schema.json). Add the `Data Loss Prevention` key with the `Accessiblity` sub-key, then include enforcement.

**Using plist**

Example plist file to exclude the com.azul.zulu.java signing ID: [com.microsoft.wdav.plist](./com.microsoft.wdav.plist).