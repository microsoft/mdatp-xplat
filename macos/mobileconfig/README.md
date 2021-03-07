# macOS/mobileconfig

Configuration profiles for MDM (JAMF, Intune)

- [Combined profile - a single profile that contains complete set of settings for Microsoft Defender ATP](combined/)
- [Individual profiles - individual profiles in separate files, one per type](profiles/)

- `identifier "com.microsoft.wdav" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */ and certificate leaf[field.1.2.840.113635.100.6.1.13] /* exists */ and certificate leaf[subject.OU] = UBF8T346G9`
