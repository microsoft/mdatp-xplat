# Live Response: Client Analyzer

These actions install and run the binary or Python Client Analyzer in a private workspace during a Microsoft Defender for Endpoint Live Response session.

## Requirements

- The installer and matching runner must execute as the same operating-system user.
- The complete `ClientAnalyzer` directory must remain together so the wrappers can load `client_analyzer_handoff.py`.
- `curl`, `mktemp`, `sha256sum`, `stat`, and `unzip` must be available.
- The endpoint must be able to reach the Microsoft download endpoint.
- Retrieve generated diagnostic archives before the private workspace is removed.

The workspace is created under `/var/tmp` with a random name and `0700` permissions. `/var/tmp` can be cleaned by local policy, so rerun the installer if a saved workspace is no longer available.

## Binary Client Analyzer

Upload `client_analyzer_handoff.py`, `InstallXMDEClientAnalyzer.sh`, and `MDESupportTool.sh`.

Run the installer without parameters:

```text
run InstallXMDEClientAnalyzer.sh
```

Copy the printed workspace ID and pass only that ID to the runner:

```text
run MDESupportTool.sh -parameters "mde-client-analyzer-binary-{16 characters}"
```

The installer selects and verifies the amd64 or arm64 package.

## Python Client Analyzer

Upload `client_analyzer_handoff.py`, `InstallXMDEPythonClientAnalyzer.sh`, and `MDEPythonSupportTool.sh`.

Run the installer without parameters:

```text
run InstallXMDEPythonClientAnalyzer.sh
```

Pass the printed workspace ID to the runner:

```text
run MDEPythonSupportTool.sh -parameters "mde-client-analyzer-python-{16 characters}"
```

The installer runs the package's existing dependency preparation before publishing the workspace.

## Security Model

- Workspaces are random, private, and inaccessible to a different local user.
- Downloads require HTTPS for both the initial URL and redirects.
- Outer, architecture-specific inner, and entrypoint SHA-256 values fail closed.
- A `0600` completion record is written only after installation succeeds.
- Runners validate token format, ownership, permissions, link counts, completion content, and entrypoint hashes.
- Runners use fixed `--bypass-disclaimer -d` arguments instead of forwarding an unspecified Live Response parameter string.
- Incomplete workspaces are removed after ordinary failures, HUP, INT, or TERM.

The implementation trusts the internal structure of an artifact after its exact pinned hash matches. Network integrity tests audit the current published ZIP paths, file types, sizes, architecture archives, and entrypoint hashes. The shared helper centralizes this handoff logic while the existing action names remain unchanged. Same-UID and root attackers remain outside this protection boundary.

## Validation

```text
python3 linux/LiveResponse/ClientAnalyzer/tests/test_minimal_client_analyzer_handoff.py -v
RUN_NETWORK_INTEGRITY_TESTS=1 python3 linux/LiveResponse/ClientAnalyzer/tests/test_minimal_client_analyzer_handoff.py -v
```

For the broader product workflow, see [Run the Microsoft Defender for Endpoint Client Analyzer on Linux](https://learn.microsoft.com/en-us/defender-endpoint/run-analyzer-linux).
