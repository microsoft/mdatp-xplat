#!/usr/bin/env bats

# Test suite for xplat_offline_updates_download.sh

setup() {
    SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../../linux/definition_downloader" && pwd)"
    SCRIPT_PATH="$SCRIPT_DIR/xplat_offline_updates_download.sh"
}

@test "script exists" {
    [ -f "$SCRIPT_PATH" ]
}

@test "script has valid bash syntax" {
    run bash -n "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}

@test "script has shebang" {
    first_line=$(head -n 1 "$SCRIPT_PATH")
    [[ "$first_line" =~ ^#! ]]
    [[ "$first_line" =~ bash ]]
}

@test "script version is defined" {
    run grep -E 'scriptVersion=' "$SCRIPT_PATH"
    [ "$status" -eq 0 ]
}
