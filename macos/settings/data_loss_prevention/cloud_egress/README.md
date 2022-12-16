# Cloud Egress Examples

If you want to restrict the CloudEgress to browser, please set following in your com.microsoft.wdav.mobileconfig:

```xml
<key>dlp</key>
<dict>
	<key>features</key>
	<array>
		<dict>
			<key>name</key>
			<string>DLP_browser_only_cloud_egress</string>
			<key>state</key>
			<string>enabled</string>
		</dict>
	</array>
</dict>
```

You can also take a look at the sample file: [com.microsoft.wdav.mobileconfig](./com.microsoft.wdav.mobileconfig)