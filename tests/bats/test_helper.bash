# Helper functions for BATS tests

# Load this file in your test with:
# load test_helper

# Get the project root directory
get_project_root() {
    cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd
}

# Check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Skip test if not running as root
skip_if_not_root() {
    if [[ $EUID -ne 0 ]]; then
        skip "This test requires root privileges"
    fi
}

# Skip test if a command is not available
skip_if_missing() {
    local cmd="$1"
    if ! command_exists "$cmd"; then
        skip "Required command not found: $cmd"
    fi
}

# Create a temporary directory for test files
setup_temp_dir() {
    TEST_TEMP_DIR=$(mktemp -d)
    export TEST_TEMP_DIR
}

# Clean up temporary directory
teardown_temp_dir() {
    if [[ -n "${TEST_TEMP_DIR:-}" ]] && [[ -d "$TEST_TEMP_DIR" ]]; then
        rm -rf "$TEST_TEMP_DIR"
    fi
}

# Assert that a file contains a pattern
assert_file_contains() {
    local file="$1"
    local pattern="$2"
    grep -q "$pattern" "$file" || {
        echo "File $file does not contain pattern: $pattern"
        return 1
    }
}

# Assert that output contains a pattern
assert_output_contains() {
    local pattern="$1"
    [[ "$output" =~ $pattern ]] || {
        echo "Output does not contain pattern: $pattern"
        echo "Actual output: $output"
        return 1
    }
}
