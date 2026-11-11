#!/bin/bash
# Submit one experiment's batch jobs: one job per node count per repeat.
#
#   run-scripts/submit.sh -s <system> -x <experiment> -P <preset> [-p prefix] [-l label] [-o dir]
#
#   -s  tuolumne | frontier
#   -x  pingpong | cabana-ghost | acg
#   -P  smoke | full (see presets.sh; any preset variable can be overridden from the environment)
#   -p  install prefix that build-scripts/build.sh built (default: the system's default prefix).
#       Its manifest.txt is copied into the run directory, so every result traces to a build.
#   -l  label for this batch of runs (default: <date>-<preset>)
#   -o  run directory (default: outputs/<Experiment>/<SYSTEM>/<label> in this repository;
#       outputs/ is gitignored). It must not exist yet: a batch is never mixed into another.
#
# Each job appends its output to <run dir>/<SYSTEM>-<nodes>N-r<repeat>.out and its scheduler log
# to <run dir>/logs/. Turn a finished run directory into a CSV with the experiment's out-to-csv.py
# (see the README). SD_DRY_RUN=1 prints the submissions instead.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "${SCRIPT_DIR}/../systems/common.sh"
source "${SCRIPT_DIR}/presets.sh"

usage() {
    sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

SYSTEM="" EXPERIMENT="" PRESET="" PREFIX="" LABEL="" RUN_DIR=""
while getopts ":s:x:P:p:l:o:h" opt; do
    case $opt in
        s) SYSTEM="$OPTARG" ;;
        x) EXPERIMENT="$OPTARG" ;;
        P) PRESET="$OPTARG" ;;
        p) PREFIX="$OPTARG" ;;
        l) LABEL="$OPTARG" ;;
        o) RUN_DIR="$OPTARG" ;;
        h) usage 0 ;;
        *) usage 1 ;;
    esac
done
[ -n "$SYSTEM" ] && [ -n "$EXPERIMENT" ] && [ -n "$PRESET" ] || usage 1

EXP_DIR="$(sd_exp_dir "$EXPERIMENT")" || sd_die "unknown experiment '$EXPERIMENT' (pingpong, cabana-ghost or acg)"
JOB_SCRIPT="${SCRIPT_DIR}/${EXPERIMENT}-job.sh"

sd_load_system "$SYSTEM"
sd_preset "$EXPERIMENT" "$PRESET"

PREFIX="$(realpath -m "${PREFIX:-$(sd_default_prefix)}")"
MANIFEST="${PREFIX}/manifest.txt"
[ -f "$MANIFEST" ] || sd_dry || sd_die "no $MANIFEST: build the stack first (build-scripts/build.sh)"

LABEL="${LABEL:-$(date +%F)-${PRESET}}"
RUN_DIR="$(realpath -m "${RUN_DIR:-${SD_ROOT}/outputs/${EXP_DIR}/${SD_SYSTEM_LABEL}/${LABEL}}")"
[ -e "$RUN_DIR" ] && sd_die "$RUN_DIR already exists: pick another label (-l)"
mkdir -p "${RUN_DIR}/logs"

# Everything about this batch, in the run directory: the build it ran, and what was asked for.
if [ -f "$MANIFEST" ]; then
    cp "$MANIFEST" "${RUN_DIR}/manifest.txt"
else
    echo "(dry run: no manifest at $MANIFEST)" > "${RUN_DIR}/manifest.txt"
fi
{
    echo "experiment: $EXPERIMENT"
    echo "preset: $PRESET"
    echo "system: $SD_SYSTEM"
    echo "label: $LABEL"
    echo "prefix: $PREFIX"
    echo "submitted: $(date -Is) from $(hostname)"
    echo "scripts: $(sd_repo_line stream-triggering-data "$SD_ROOT")"
    echo "modules: $SD_MODULES"
    for v in SD_NODE_LIST SD_REPEATS SD_JOB_MINUTES SD_CHAIN $(sd_preset_vars "$EXPERIMENT"); do
        echo "$v: ${!v:-}"
    done
} > "${RUN_DIR}/run-info.txt"

sd_log "$EXPERIMENT ($PRESET) on $SD_SYSTEM: nodes [$SD_NODE_LIST] x $SD_REPEATS repeat(s)"
sd_log "run directory $RUN_DIR"

prev=""
for (( r=1; r<=SD_REPEATS; r++ )); do
    [ "$SD_CHAIN" = "repeat" ] && prev=""
    for nodes in $SD_NODE_LIST; do
        name="${EXPERIMENT}-${nodes}N-r${r}"
        after=""
        [ "$SD_CHAIN" != "none" ] && after="$prev"
        id="$(sd_submit "$nodes" "$SD_JOB_MINUTES" "$name" "${RUN_DIR}/logs/${name}.log" "$after" \
                "$JOB_SCRIPT" SD_ROOT="$SD_ROOT" SD_SYSTEM="$SD_SYSTEM" SD_PREFIX="$PREFIX" \
                SD_RUN_DIR="$RUN_DIR" SD_MANIFEST="${RUN_DIR}/manifest.txt" \
                SD_JOB_NODES="$nodes" SD_JOB_REPEAT="$r" ${MOD_FILE:+MOD_FILE="$MOD_FILE"})"
        echo "job: $name $id" >> "${RUN_DIR}/run-info.txt"
        echo "$name $id"
        prev="$id"
    done
done
