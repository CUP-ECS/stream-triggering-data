#!/bin/bash
# Shared helpers for the build and run scripts. Source it; don't run it.
#
#   source systems/common.sh
#   sd_load_system tuolumne        # system settings + modules + runtime environment
#
# Environment knobs every script honours:
#   MOD_FILE     Module list to load instead of systems/<system>.modules
#   SD_DRY_RUN=1 Print scheduler, launcher, build and module commands instead of running them
#                (for checking the scripts on a laptop)

SD_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)"
source "${SD_ROOT}/systems/versions.sh"

SD_RED='\033[1;31m'
SD_CYAN='\033[0;36m'
SD_RESET='\033[0m'

sd_log()  { echo -e "${SD_CYAN}==${SD_RESET} $*" >&2; }
sd_warn() { echo -e "${SD_RED}warning:${SD_RESET} $*" >&2; }
sd_die()  { echo -e "${SD_RED}error:${SD_RESET} $*" >&2; exit 1; }

sd_dry() { [ "${SD_DRY_RUN:-0}" = "1" ]; }

# Run a command, or print it in a dry run.
sd_run() {
    if sd_dry; then
        echo "+ $*" >&2
    else
        "$@"
    fi
}

# The lines of a module file, without comments or blank lines, on one line.
sd_modules_from() {
    grep -v '^\s*#' "$1" | grep -v '^\s*$' | tr '\n' ' ' | sed 's/ *$//'
}

# Load a module file (or print what would load, in a dry run). Exports SD_MODULE_FILE and
# SD_MODULES, which the manifest and the run headers record.
sd_load_modules() {
    local file="$1"
    [ -f "$file" ] || sd_die "module file '$file' not found"
    SD_MODULE_FILE="$(realpath "$file")"
    SD_MODULES="$(sd_modules_from "$file")"
    export SD_MODULE_FILE SD_MODULES
    if sd_dry; then
        echo "+ module load $SD_MODULES" >&2
        return 0
    fi
    type module &> /dev/null || sd_die "no 'module' command: can't load $file"
    # shellcheck disable=SC2086 # one word per module
    sd_module load $SD_MODULES || sd_die "module load failed for $file"
}

# `module`, with nounset off while it runs: Lmod's generated shell code isn't set -u clean.
sd_module() {
    local had_u=0 rc=0
    [[ $- == *u* ]] && had_u=1
    set +u
    module "$@" || rc=$?
    [ "$had_u" = 1 ] && set -u
    return "$rc"
}

# Set up everything for one system: its settings (systems/<system>.sh), its modules, and the
# runtime environment its jobs need. Usage: sd_load_system <tuolumne|frontier>
sd_load_system() {
    local system="${1:-}"
    case "$system" in
        tuolumne|frontier) ;;
        *) sd_die "unknown system '$system' (expected tuolumne or frontier)" ;;
    esac
    # shellcheck source=/dev/null
    source "${SD_ROOT}/systems/${system}.sh"
    sd_load_modules "${MOD_FILE:-${SD_ROOT}/systems/${system}.modules}"
    sd_system_env
}

# The default install prefix of this system's stack: <SD_PREFIX_ROOT>/<SD_STACK_TAG>
sd_default_prefix() {
    echo "${SD_PREFIX_ROOT}/${SD_STACK_TAG}"
}

# Make sure a source tree exists, cloning it at <ref> if it doesn't.
#   sd_clone <dir> <url> <ref> [sha]
# With a sha (third-party pins), an existing checkout must be at exactly that commit
# (SD_ALLOW_UNPINNED=1 downgrades that to a warning). Without one (our own repositories), an
# existing checkout is used as it is, with a warning when it isn't on <ref>.
sd_clone() {
    local dir="$1" url="$2" ref="$3" sha="${4:-}"
    if [ ! -d "$dir/.git" ] && [ ! -f "$dir/.git" ]; then
        sd_log "cloning $url ($ref) into $dir"
        sd_run git -c advice.detachedHead=false clone --quiet --branch "$ref" "$url" "$dir" \
            || sd_die "clone of $url failed"
        sd_dry && return 0
    fi
    sd_dry && [ ! -d "$dir" ] && return 0
    local head branch
    head="$(git -C "$dir" rev-parse HEAD)"
    if [ -n "$sha" ]; then
        if [ "$head" != "$sha" ]; then
            if [ "${SD_ALLOW_UNPINNED:-0}" = "1" ]; then
                sd_warn "$dir is at $head, not the pinned $ref ($sha)"
            else
                sd_die "$dir is at $head, not the pinned $ref ($sha). Remove it to re-clone, or set SD_ALLOW_UNPINNED=1"
            fi
        fi
    else
        branch="$(git -C "$dir" branch --show-current)"
        if [ "$branch" != "$ref" ]; then
            sd_warn "$dir is on '${branch:-detached HEAD}', not '$ref'"
        fi
    fi
}

# One manifest line for a source tree: name, path, branch, commit, and whether it has
# uncommitted changes (a build of a dirty tree can't be reproduced from git).
sd_repo_line() {
    local name="$1" dir="$2"
    if [ ! -e "$dir/.git" ]; then
        echo "$name $dir (missing)"
        return
    fi
    local branch head state
    branch="$(git -C "$dir" branch --show-current)"
    head="$(git -C "$dir" rev-parse HEAD)"
    # Untracked files count: a new, uncommitted script is as unreproducible as an edited one.
    if [ -z "$(git -C "$dir" status --porcelain 2> /dev/null)" ]; then
        state=clean
    else
        state=DIRTY
    fi
    echo "$name $dir ${branch:-detached} $head $state"
}

# Run a step with its output in a log as well as on the terminal; fail with the log's name.
#   sd_step <log> <command...>
sd_step() {
    local log="$1"
    shift
    if sd_dry; then
        echo "+ $*" >&2
        return 0
    fi
    echo "+ $*" >> "$log"
    "$@" 2>&1 | tee -a "$log"
    local rc="${PIPESTATUS[0]}"
    [ "$rc" -eq 0 ] || sd_die "failed (exit $rc): $*  -- see $log"
}

# A file name under <dir> that doesn't exist yet: <dir>/<base>-<n><ext>, n counting from 1.
sd_unused_name() {
    local dir="$1" base="$2" ext="$3" n=1
    while [ -e "${dir}/${base}-${n}${ext}" ]; do
        n=$((n + 1))
    done
    echo "${dir}/${base}-${n}${ext}"
}

# The header every run's output file starts with: the manifest it ran from, the modules, and
# the nodes. The parsers skip it (they only read Test: lines and timings).
#   sd_run_header <outfile> <nodes>
sd_run_header() {
    local out="$1" nodes="$2"
    {
        echo "# Date: $(date -Is)"
        echo "# System: ${SD_SYSTEM}"
        echo "# Manifest: ${SD_MANIFEST:-unknown}"
        echo "# Modules: ${SD_MODULES:-unknown}"
    } >> "$out"
    if sd_dry; then
        echo "+ module list >> $out" >&2
    else
        sd_module list >> "$out" 2>&1
    fi
    sd_hostnames "$nodes" "$out"
}

# Put a prefix's component manifests (<prefix>/manifests/*.txt) together into <prefix>/manifest.txt,
# warning when its components were built under different modules.
sd_assemble_manifest() {
    local prefix="$1"
    {
        echo "# Build manifest for $prefix"
        echo "# Assembled $(date -Is) on $(hostname)"
        echo "system: $SD_SYSTEM"
        echo "stack: $SD_STACK_TAG"
        echo
        cat "${prefix}"/manifests/*.txt
    } > "${prefix}/manifest.txt"
    if [ "$(grep -h '^modules: ' "${prefix}"/manifests/*.txt | sort -u | wc -l)" -gt 1 ]; then
        sd_warn "components in $prefix were built with different modules: see ${prefix}/manifest.txt"
    fi
}
