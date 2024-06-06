# Defender configuration validator

Validates an arbitrary configuration file against published JSON schema, and reports any issues found.

Reads one or many files provided on the command line, each file can be of one of the following formats:
- Simple macOS Plist file like [JAMF Pro Property List](https://learn.microsoft.com/en-us/defender-endpoint/mac-preferences?view=o365-worldwide#property-list-for-jamf-recommended-configuration-profile)
- Unsigned .mobileconfig file like from the [Intune example](https://learn.microsoft.com/en-us/defender-endpoint/mac-preferences?view=o365-worldwide#intune-recommended-profile)
- Signed .mobileconfig file like exported configuration profile from JAMF Pro
- Simple JSON file like [Linux managed configuration](https://learn.microsoft.com/en-us/defender-endpoint/linux-preferences?view=o365-worldwide#sample-profile)

## Prerequisites

You need Python 3 installed

## Usage

The easiest is to run the wrapper script:

```
./validate-config-profile ~/Downloads/DefenderConfiguration.mobileconfig'

Collecting jschon==0.11.1 (from -r requirements.txt (line 1))
  Using cached jschon-0.11.1-py3-none-any.whl.metadata (5.4 kB)
Collecting rfc3986==2.0.0 (from -r requirements.txt (line 2))
  Using cached rfc3986-2.0.0-py2.py3-none-any.whl.metadata (6.6 kB)
Using cached jschon-0.11.1-py3-none-any.whl (66 kB)
Using cached rfc3986-2.0.0-py2.py3-none-any.whl (31 kB)
Installing collected packages: rfc3986, jschon
Successfully installed jschon-0.11.1 rfc3986-2.0.0
[INFO] Downloading schema from https://raw.githubusercontent.com/microsoft/mdatp-xplat/master/macos/schema/schema.json
[INFO] Analyzing file: /Users/mavel/Downloads/Defender Configuration.mobileconfig
[INFO] JSON is valid: Defender Configuration (7B1483A4-A83C-4517-BCD1-B431FB19F296) / D355A609-6250-4647-97FD-BE729F777E04 / com.microsoft.wdav #1
✅    /properties/antivirusEngine
✅      /properties/antivirusEngine/properties
✅        /properties/antivirusEngine/properties/scanHistoryMaximumItems
✅    /properties/edr
✅      /properties/edr/properties
✅        /properties/edr/properties/groupIds
✅        /properties/edr/properties/tags
✅          /properties/edr/properties/tags/items
✅            /properties/edr/properties/tags/items/properties
✅              /properties/edr/properties/tags/items/properties/key
✅              /properties/edr/properties/tags/items/properties/value
✅    /properties/tamperProtection
✅      /properties/tamperProtection/properties
✅        /properties/tamperProtection/properties/enforcementLevel
✅        /properties/tamperProtection/properties/exclusions
✅          /properties/tamperProtection/properties/exclusions/items
✅            /properties/tamperProtection/properties/exclusions/items/properties
✅              /properties/tamperProtection/properties/exclusions/items/properties/path
✅              /properties/tamperProtection/properties/exclusions/items/properties/signingId
✅              /properties/tamperProtection/properties/exclusions/items/properties/teamId
✅              /properties/tamperProtection/properties/exclusions/items/properties/args
✅                /properties/tamperProtection/properties/exclusions/items/properties/args/items
```

The shell script will create a temporary virtual environment, install all modules and run Python script with provided parameters.

By default it reports settings that both passed and failed validation, and settings that are not defined by the Schema.

You can run the Python script directly, though you will need to install modules that the script requires: `pip install -r requirements':

```
python ./validate-config-profile.py /tmp/s.plist

[INFO] Downloading schema from https://raw.githubusercontent.com/microsoft/mdatp-xplat/master/macos/schema/schema.json
[INFO] Analyzing file: /tmp/s.plist
[WARN] JSON is invalid
❌    /properties/antivirusEngine
❌      /properties/antivirusEngine/properties: Properties ['passiveMode'] are invalid
❌        /properties/antivirusEngine/properties/passiveMode
❌          /properties/antivirusEngine/properties/passiveMode/type: The instance must be of type "boolean"
✅    /properties/tamperProtection
✅      /properties/tamperProtection/properties
✅        /properties/tamperProtection/properties/enforcementLevel
[WARN] Unexpected nodes found (either misspelled or not at the expected location):
❌    /garbage
```

In the example above, the script reports that the setting /antivirusEngine is invalid because its subsetting /antivirusEngine/passiveMode has invalid type.
/tamperProtections settings are OK, and will be used by Defender.
There is a setting /garbage defined at the top level, which is not supported by the schema.
Most probably it was added there by mistake.

Another example, let's take the following Plist:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>antivirusEngine</key>
    <dict>
      <key>passiveMode</key>
      <false/>
      <key>tamperProtection</key>
      <dict>
        <key>enforcementLevel</key>
        <string>block</string>
      </dict>
    </dict>
  </dict>
</plist>
```

And try it with the tool:

```bash
python ./validate-config-profile.py /tmp/ss.plist

[INFO] Downloading schema from https://raw.githubusercontent.com/microsoft/mdatp-xplat/master/macos/schema/schema.json
[INFO] Analyzing file: /tmp/ss.plist
[INFO] JSON is valid
✅    /properties/antivirusEngine
✅      /properties/antivirusEngine/properties
✅        /properties/antivirusEngine/properties/passiveMode
[WARN] Unexpected nodes found (either misspelled or not at the expected location):
❌      /antivirusEngine/tamperProtection
❌        /antivirusEngine/tamperProtection/enforcementLevel
```

Here, Defender will use /antivirusEngine/passiveMode setting under /antivirusEngine.
However, tamperProtection/enforcementLevel will be ignored.
Because it was defined under /antivirusEngine, not at the top of the config file.

## Other

You can run the tool without arguments, and it will report how to use it:

```bash
./validate-config-profile

usage: validate-config-profile.py [-h] [--schema SCHEMA] [--verbose] [--print-valid] [--print-invalid] [--print-unsupported] file [file ...]

Validate configuration profile against schema

positional arguments:
  file

options:
  -h, --help           show this help message and exit
  --schema SCHEMA      Path to the schema file
  --verbose            Include verbose output
  --print-valid        Include list of configuration values passed validation
  --print-invalid      Include list of configuration values failed validation
  --print-unsupported  Include list of configuration values out of schema scope
```

By default it downloads the current schema from [Github](https://github.com/microsoft/mdatp-xplat/tree/master/macos/schema). 
You can provide a custom schema/avoid downloading schema with the --schema parameter.

--verbose gives more details information on what the tool does.

By default, the tool produced both valid, invalid and unsupported settings.
You can tell it what to report by providing --print-* flags.
