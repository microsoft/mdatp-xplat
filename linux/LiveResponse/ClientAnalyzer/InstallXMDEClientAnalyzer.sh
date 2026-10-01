#!/bin/sh
set -eu

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077

state_parent=/var/tmp
workspace_prefix=mde-client-analyzer-binary-
download_url=https://go.microsoft.com/fwlink/?linkid=2336125
outer_sha256=5f906591d33d675f14d73d5b658a796cec7480b023b18d45c5d687713a4d4fbb
amd64_inner_name=SupportToolLinuxamd64Binary.zip
amd64_inner_sha256=a500c00fe0dc2bb5b23ec9c771fd40694d111fa78d095d6ff77e4f0b36a23903
amd64_entry_sha256=b6b21fbc12b6d37be331a5e27a9741b43d35876645e02b26c8cafc4e623ed5e1
arm64_inner_name=SupportToolLinuxarm64Binary.zip
arm64_inner_sha256=ba8cc0c9766f5c937a90db00af6ed936ecdbfbba88049a383df814203af5066a
arm64_entry_sha256=a3b60a11eea093f9ec7b9bd7ea86a0e8bbc6f481116311dd678d69def49b5169

fail() {
    echo "ERROR: $1" >&2
    cleanup_incomplete_workspace || :
    exit 1
}

cleanup_incomplete_workspace() {
    if [ "${completed:-0}" != 1 ] && [ -n "${workspace:-}" ] && [ -d "$workspace" ]; then
        if [ -n "${member_list:-}" ] && [ -f "$member_list" ] && [ -n "${payload:-}" ]; then
            directory_list="$workspace/archive-directories"
            : > "$directory_list"
            while IFS= read -r member; do
                case "$member" in
                    */)
                        member=${member%/}
                        printf '%s\n' "$member" >> "$directory_list"
                        ;;
                    *) rm -f "$payload/$member" ;;
                esac
                while [ "${member#*/}" != "$member" ]; do
                    member=${member%/*}
                    printf '%s\n' "$member" >> "$directory_list"
                done
            done < "$member_list"
            awk '{ depth = gsub(/\//, "/"); print depth "\t" $0 }' "$directory_list" |
                sort -rn -k1,1 |
                cut -f2- |
                uniq |
                while IFS= read -r directory; do
                rmdir "$payload/$directory" 2>/dev/null || :
            done
            rm -f "$directory_list"
            rm -f "$member_list"
            rmdir "$payload" 2>/dev/null || :
        elif [ -n "${member_list:-}" ] && [ -f "$member_list" ]; then
            rm -f "$member_list"
        fi
        rm -f "$workspace/client-analyzer.zip" "$workspace/$inner_name" "$workspace/complete"
        rmdir "$workspace" 2>/dev/null || :
    fi
}

file_metadata() {
    stat -c '%F:%u:%a:%h' "$1"
}

validate_private_directory() {
    metadata=$(file_metadata "$1") || fail "Directory is not private: $1"
    expected="directory:$(id -u):700:"
    case "$metadata" in
        "$expected"*) ;;
        *) fail "Directory is not private: $1" ;;
    esac
}

validate_private_file() {
    metadata=$(file_metadata "$1") || fail "File is not private and regular: $1"
    expected="regular file:$(id -u):$2:1"
    [ "$metadata" = "$expected" ] || fail "File is not private and regular: $1"
}

validate_state_parent() {
    metadata=$(stat -c '%F:%u:%a' "$state_parent") || fail "State parent is unavailable."
    case "$metadata" in
        "directory:0:1777"|"directory:$(id -u):700") ;;
        *) fail "State parent is not trusted: $state_parent" ;;
    esac
}

sha256() {
    sha256sum "$1" | awk '{print $1}'
}

verify_sha256() {
    [ "$(sha256 "$1")" = "$2" ] || fail "$3 failed integrity verification."
}

validate_archive_members() {
    unzip -Z1 "$1" > "$2" || fail "Archive member listing failed."
    while IFS= read -r member; do
        case "$member" in
            ""|/*|*\\*|.|..|../*|*/../*|*/..|*/./*|*/.|*//*)
                fail "Archive contains an unsafe member."
                ;;
        esac
    done < "$2"
    if sort "$2" | uniq -d | grep -q .; then
        fail "Archive contains duplicate members."
    fi
}

create_workspace() {
    attempts=0
    while [ "$attempts" -lt 10 ]; do
        token=$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n') || fail "Failed to allocate workspace."
        workspace="$state_parent/$workspace_prefix$token"
        if mkdir -m 700 "$workspace" 2>/dev/null; then
            validate_private_directory "$workspace"
            return
        fi
        attempts=$((attempts + 1))
    done
    fail "Failed to allocate a unique private directory."
}

select_architecture() {
    case "$(uname -m)" in
        x86_64|amd64)
            architecture=amd64
            inner_name=$amd64_inner_name
            inner_sha256=$amd64_inner_sha256
            entry_sha256=$amd64_entry_sha256
            ;;
        aarch64|arm64)
            architecture=arm64
            inner_name=$arm64_inner_name
            inner_sha256=$arm64_inner_sha256
            entry_sha256=$arm64_entry_sha256
            ;;
        *) fail "Unsupported architecture: $(uname -m)" ;;
    esac
}

normalize_payload() {
    find -P "$1" -type l -print -quit | grep -q . && fail "Archive contains a link."
    find -P "$1" ! -type d ! -type f -print -quit | grep -q . && fail "Archive contains a special file."
    find -P "$1" -type f -links +1 -print -quit | grep -q . && fail "Archive contains a linked file."
    find -P "$1" -type d -exec chmod 700 {} +
    find -P "$1" -type f -exec chmod 600 {} +
}

install() {
    [ "$#" -eq 0 ] || fail "Install actions do not accept parameters."
    validate_state_parent
    select_architecture
    create_workspace
    completed=0
    trap 'cleanup_incomplete_workspace || :' 0
    trap 'cleanup_incomplete_workspace || :; exit 1' HUP INT TERM
    archive="$workspace/client-analyzer.zip"
    payload="$workspace/payload"
    inner_archive="$workspace/$inner_name"

    curl -q --fail --silent --show-error --location --proto =https --proto-redir =https \
        --max-redirs 5 --connect-timeout 30 --max-time 180 --max-filesize 67108864 \
        --output "$archive" "$download_url" || fail "Client Analyzer download failed."
    validate_private_file "$archive" 600
    verify_sha256 "$archive" "$outer_sha256" "Client Analyzer archive"
    unzip -p "$archive" "$inner_name" > "$inner_archive" || fail "Architecture-specific archive extraction failed."
    validate_private_file "$inner_archive" 600
    verify_sha256 "$inner_archive" "$inner_sha256" "Architecture-specific archive"
    member_list="$workspace/archive-members"
    validate_archive_members "$inner_archive" "$member_list"
    unzip -tq "$inner_archive" >/dev/null || fail "Archive validation failed."
    mkdir -m 700 "$payload" || fail "Client Analyzer extraction failed."
    unzip -q "$inner_archive" -d "$payload" || fail "Client Analyzer extraction failed."
    normalize_payload "$payload"
    entrypoint="$payload/MDESupportTool"
    validate_private_file "$entrypoint" 600
    chmod 700 "$entrypoint"
    validate_private_file "$entrypoint" 700
    verify_sha256 "$entrypoint" "$entry_sha256" "Client Analyzer entrypoint"
    rm -f "$archive" "$inner_archive"

    completion="$workspace/complete"
    (set -C; : > "$completion") 2>/dev/null || fail "Client Analyzer completion record already exists."
    printf '1 binary %s %s %s %s %s\n' \
        "$architecture" "$outer_sha256" "$inner_sha256" "$entry_sha256" "$(basename "$workspace")" > "$completion"
    chmod 600 "$completion"
    validate_private_file "$completion" 600
    completed=1
    trap - 0 HUP INT TERM
    rm -f "$member_list"
    echo "Client Analyzer binary installed in private workspace: $(basename "$workspace")"
    echo "Run the matching support action with workspace ID: $(basename "$workspace")"
}

run() {
    [ "$#" -eq 1 ] || fail "Pass exactly one workspace ID from the installer."
    workspace_id=$1
    case "$workspace_id" in
        "$workspace_prefix"[0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef][0123456789abcdef]) ;;
        *) fail "Invalid Client Analyzer workspace ID." ;;
    esac
    validate_state_parent
    select_architecture
    workspace="$state_parent/$workspace_id"
    payload="$workspace/payload"
    completion="$workspace/complete"
    entrypoint="$payload/MDESupportTool"
    validate_private_directory "$workspace"
    validate_private_directory "$payload"
    validate_private_file "$completion" 600
    expected_record="1 binary $architecture $outer_sha256 $inner_sha256 $entry_sha256 $workspace_id"
    [ "$(cat "$completion")" = "$expected_record" ] || fail "Client Analyzer completion record failed validation."
    validate_private_file "$entrypoint" 700
    verify_sha256 "$entrypoint" "$entry_sha256" "Client Analyzer entrypoint"
    runs="$workspace/runs"
    if [ -e "$runs" ]; then
        validate_private_directory "$runs"
    else
        mkdir -m 700 "$runs" || fail "Failed to create Client Analyzer run directory."
    fi
    run_directory=$(mktemp -d "$runs/run-XXXXXXXXXXXXXXXX") || fail "Failed to create Client Analyzer run directory."
    validate_private_directory "$run_directory"
    echo "Client Analyzer run directory: $run_directory"
    cd "$payload"
    exec env -i HOME=/ LANG=C LC_ALL=C PATH="$PATH" TMPDIR="$run_directory" \
        "$entrypoint" --bypass-disclaimer -d
}


install "$@"
