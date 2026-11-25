#!/bin/sh
# Hook launcher for the config-history plugin.
# Finds a Python 3.9 or later and runs the stdlib-only bootstrap with it.
# Usage: config-history-hook.sh start|end
# Uses only shell builtins apart from the Python it finds, plus date and mkdir
# for the "needs Python" notice, and always exits 0.

hook_event="${1:-start}"

case "$0" in
    */*) script_dir="${0%/*}" ;;
    *) script_dir="." ;;
esac

python_is_supported() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1
}

# On macOS, /usr/bin/python3 is a stub that opens an installer dialog when the
# command line tools are missing. Skip it in that case.
# Collapse repeated slashes: a PATH entry such as /usr/bin/ makes some shells
# report /usr/bin//python3.
normalized_path() {
    normalized="$1"
    while :; do
        case "$normalized" in
            *//*) normalized="${normalized%%//*}/${normalized#*//}" ;;
            *) break ;;
        esac
    done
    printf '%s\n' "$normalized"
}

python_stub_without_tools() {
    [ "$(normalized_path "$1")" = "/usr/bin/python3" ] || return 1
    command -v xcode-select >/dev/null 2>&1 || return 1
    xcode-select -p >/dev/null 2>&1 && return 1
    return 0
}

find_python() {
    for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
        candidate_path=$(command -v "$candidate" 2>/dev/null) || continue
        [ -n "$candidate_path" ] || continue
        python_stub_without_tools "$candidate_path" && continue
        if python_is_supported "$candidate_path"; then
            printf '%s\n' "$candidate_path"
            return 0
        fi
    done
    return 1
}

# The "needs Python" notice shows at most once per calendar day. The day it
# was last shown is kept in a stamp file in the plugin data folder.
report_missing_python() {
    today=$(date +%Y-%m-%d 2>/dev/null) || today=""
    stamp_file=""
    if [ -n "$CLAUDE_PLUGIN_DATA" ]; then
        stamp_file="$CLAUDE_PLUGIN_DATA/python-missing-notice"
    fi
    if [ -n "$today" ] && [ -n "$stamp_file" ] && [ -r "$stamp_file" ]; then
        IFS= read -r last_day < "$stamp_file" || true
        [ "$last_day" = "$today" ] && return 0
    fi
    printf '%s\n' '{"systemMessage": "config-history needs Python 3.9 or later and is inactive. Install Python 3.9 or later, then start a new Claude Code session."}'
    if [ -n "$today" ] && [ -n "$stamp_file" ]; then
        mkdir -p "$CLAUDE_PLUGIN_DATA" 2>/dev/null
        printf '%s\n' "$today" > "$stamp_file" 2>/dev/null
    fi
    return 0
}

if ! python_path=$(find_python); then
    if [ "$hook_event" = "start" ]; then
        report_missing_python
    fi
    exit 0
fi

# -E -s: ignore PYTHONPATH and user site-packages. -B: write no bytecode into
# the plugin folder.
"$python_path" -B -E -s "$script_dir/config_history_bootstrap.py" "$hook_event"
exit 0
