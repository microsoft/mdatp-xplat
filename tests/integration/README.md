# Integration Tests

This directory contains integration tests that require a full system environment to run.

## Overview

Integration tests verify that the scripts work correctly on actual systems with real package managers, file systems, and system configurations.

## Running Integration Tests

Integration tests should be run:
- In a VM or container to avoid affecting the host system
- With appropriate privileges (root for installer tests)
- On the target distribution being tested

## Test Categories

### Installation Tests

Test the full installation workflow on various distributions:
- Ubuntu (18.04, 20.04, 22.04, 24.04)
- Debian (11, 12, 13)
- RHEL/CentOS (7, 8, 9)
- Rocky Linux (8, 9)
- Fedora (38, 39, 40)
- SLES (12, 15)

### Onboarding Tests

Test the device onboarding process:
- Onboarding file validation
- File permissions verification
- Service startup

### Definition Update Tests

Test the offline definition download and update process:
- Download verification
- Update application
- Rollback scenarios

## Docker-based Testing

```bash
# Ubuntu 24.04
docker run -it -v $(pwd):/workspace ubuntu:24.04 bash
cd /workspace
./tests/integration/run_tests.sh

# Debian 12
docker run -it -v $(pwd):/workspace debian:12 bash

# Rocky Linux 9
docker run -it -v $(pwd):/workspace rockylinux:9 bash
```

## CI Integration

Integration tests are run in the CI pipeline on a matrix of supported distributions.

See `.github/workflows/integration.yml` for the CI configuration.
