#!/usr/bin/env bats

# Test suite for mde_installer.sh

setup() {
    # Get the script directory
    SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../../linux/installation" && pwd)"
    SCRIPT_PATH="$SCRIPT_DIR/mde_installer.sh"
}

@test "script exists" {
    [ -f "$SCRIPT_PATH" ]
}

@test "script has valid bash syntax" {
    run bash -n "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

@test "script version is defined" {
    run grep -E 'SCRIPT_VERSION=' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
    [[ "$output" =~ SCRIPT_VERSION= ]]
}

@test "script has shebang" {
    first_line=$(head -n 1 "$SCRIPT_PATH")
    [[ "$first_line" == "#!/bin/bash" ]]
}

@test "help option works" {
    run timeout 5 bash "$SCRIPT_PATH" --help
    [ "$status" -eq 0 ]
    [[ "$output" =~ [Uu]sage ]] || [[ "$output" =~ [Hh]elp ]]
}

@test "version option works" {
    run timeout 5 bash "$SCRIPT_PATH" --version
    # Should contain a version number like X.Y.Z
    [[ "$output" =~ [0-9]+\.[0-9]+\.[0-9]+ ]]
}

@test "script defines error codes" {
    run grep -E '^ERR_' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
    [[ "$output" =~ ERR_ ]]
}

@test "script has log functions" {
    run grep -E 'log_info|log_error|log_warning' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

# SEC-002: Input validation tests
@test "SEC-002: validate_path function exists" {
    run grep -E '^validate_path\(\)' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

@test "SEC-002: validate_script_path function exists" {
    run grep -E '^validate_script_path\(\)' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

@test "SEC-002: validate_install_path function exists" {
    run grep -E '^validate_install_path\(\)' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

@test "SEC-002: path traversal check present" {
    run grep -E 'path traversal' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

# SEC-007: GPG key verification tests
@test "SEC-007: GPG fingerprint constant defined" {
    run grep -E '^MICROSOFT_GPG_FINGERPRINT=' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

@test "SEC-007: verify_gpg_key_fingerprint function exists" {
    run grep -E '^verify_gpg_key_fingerprint\(\)' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

@test "SEC-007: download_and_verify_gpg_key function exists" {
    run grep -E '^download_and_verify_gpg_key\(\)' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

# SEC-008: Modern apt key handling tests
@test "SEC-008: uses /usr/share/keyrings directory" {
    run grep -E '/usr/share/keyrings/' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

# REL-003: Error reporting tests
@test "REL-003: script_exit shows SUCCESS message" {
    run grep -E '\[SUCCESS\]' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

@test "REL-003: script_exit shows FAILED message" {
    run grep -E '\[FAILED\]' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

@test "REL-003: script_exit provides hints" {
    run grep -E '\[\*\] Hint:' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

# REL-006: Timeout handling tests
@test "REL-006: run_with_timeout function exists" {
    run grep -E '^run_with_timeout\(\)' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

@test "REL-006: timeout kills hung processes" {
    run grep -E 'kill -TERM|kill -KILL' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

# CQ-SH-001: Variable quoting tests
@test "CQ-SH-001: ONBOARDING_SCRIPT quoted in execution" {
    run grep -E '"\$ONBOARDING_SCRIPT"' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

@test "CQ-SH-001: OFFBOARDING_SCRIPT quoted in execution" {
    run grep -E '"\$OFFBOARDING_SCRIPT"' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

@test "CQ-SH-001: INSTALL_PATH quoted in mkdir" {
    run grep -E 'mkdir -p "\$INSTALL_PATH"' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}
