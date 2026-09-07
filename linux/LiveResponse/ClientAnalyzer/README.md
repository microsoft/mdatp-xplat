# Live Response: Client Analyzer

These actions install and run the binary and Python Client Analyzer packages during a Microsoft Defender for Endpoint Live Response session.

## Requirements

- Python 3 must be available on the endpoint.
- The complete `ClientAnalyzer` directory must remain together so every wrapper can load `client_analyzer_action.py` beside it.
- The installer and matching runner must execute as the same operating-system user.
- The endpoint must be able to reach the Microsoft download endpoint during installation.
- Retrieve generated diagnostic archives before removing the private workspace.

The actions use private random workspaces under `/var/tmp`. The operating system may eventually clean this temporary storage, so rerun the installer if a saved workspace is no longer available.

## Binary Client Analyzer

Upload these actions to the Live Response library:

- `client_analyzer_action.py`
- `InstallXMDEClientAnalyzer.sh`
- `MDESupportTool.sh`

Run the installer without parameters. It prints an opaque workspace ID:

```text
run InstallXMDEClientAnalyzer.sh
```

Pass only that workspace ID to the runner:

```text
run MDESupportTool.sh -parameters "mde-client-analyzer-binary-<32 hexadecimal characters>"
```

The installer selects the amd64 or arm64 package from the endpoint architecture. Unsupported architectures fail without retaining partial state.

## Python Client Analyzer

Upload these actions to the Live Response library:

- `client_analyzer_action.py`
- `InstallXMDEPythonClientAnalyzer.sh`
- `MDEPythonSupportTool.sh`

Run the installer without parameters. It verifies and extracts the Python package, then runs its existing no-argument dependency preparation:

```text
run InstallXMDEPythonClientAnalyzer.sh
```

Pass only the printed workspace ID to the runner:

```text
run MDEPythonSupportTool.sh -parameters "mde-client-analyzer-python-<32 hexadecimal characters>"
```

Dependency preparation can access configured Python package indexes. The package currently owns that behavior; these actions isolate it in the private workspace.

## Runner Behavior

Both runners map the workspace ID to the fixed noninteractive diagnostic arguments:

```text
--bypass-disclaimer -d
```

They do not accept arbitrary Analyzer arguments because Linux Live Response does not publicly define how its single parameter string is split into shell positional arguments. Run these actions only after the required data-collection authorization has been obtained.

Each invocation creates a new private `runs/run-<random>` directory beneath the workspace and sets `TMPDIR` to that directory. The Analyzer output identifies the generated diagnostic archive for retrieval.

## Security Properties

- Downloads allow HTTPS only, including redirects.
- The current Microsoft artifacts and architecture-specific binary archives are pinned by SHA-256.
- A checksum, download, setup, or extraction failure removes partial workspace state.
- ZIP entries with traversal paths, duplicate paths, encryption, links, special files, unsupported compression, or excessive expansion are rejected.
- Validated archives are extracted into a newly created private workspace and normalized to owner-only permissions.
- A completion record binds the workspace type, architecture, artifact, inner archive, and entrypoint digests.
- Runners validate the workspace token, ownership, permissions, completion record, link count, and entrypoint digest before execution.
- Loader and Python environment overrides are removed before the Analyzer starts.

## Updating Published Artifacts

Artifact rotation requires a reviewed update to the centralized URL or digest constants in `client_analyzer_action.py`. Run the local tests and the opt-in network integrity tests before publishing the new package:

```text
python3 linux/LiveResponse/ClientAnalyzer/tests/test_client_analyzer_actions.py -v
RUN_NETWORK_INTEGRITY_TESTS=1 python3 linux/LiveResponse/ClientAnalyzer/tests/test_client_analyzer_actions.py -v
```

For the broader product workflow, see [Run the Microsoft Defender for Endpoint Client Analyzer on Linux](https://learn.microsoft.com/en-us/defender-endpoint/run-analyzer-linux).
