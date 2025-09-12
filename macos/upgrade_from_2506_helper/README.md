# upgrade_from_2506_helper

Attempts to upgrade Microsoft Defender for Endpoint on macOS from version 2506 (101.25062.0005) consistently failed.  Other versions of Defender and Security Intelligence Updates are not impacted. To overcome this issue, there is a workaround for supported macOS versions and beta versions of macOS 26.

Apply the workaround using an MDM such as Microsoft Intune or JAMF.

- Click here for the procedure on [Intune](Intune09122025.pdf)
- Click here for the procedure on [JAMF](JAMF09122025.pdf)

**NOTE** If you use another MDM, refer to the instructions on JAMF.

Click here to download the [upgrade_from_25062_helper](https://officecdn-microsoft-com.akamaized.net/pr/C1297A47-86C4-4C1F-97FA-950631F94777/MacAutoupdate/upgrade_from_25062_helper.pkg)

If you have any questions, please contact Microsoft support.

# Change Log

## September 10, 2025
- Initial release

## September 11, 2025
- Moved pkg from repo to Microsoft CDN

## September 12, 2025
- Updated Instructions to include clean-up instructions