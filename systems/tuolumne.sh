#!/bin/bash
# shellcheck disable=SC2034 # settings: read by the scripts that source this file
# LLNL Tuolumne: 4x MI300A per node, flux. Sourced by sd_load_system in common.sh; don't run it.
# Settings can be overridden from the environment where they're written ${VAR:-default}.

SD_SYSTEM=tuolumne
SD_SYSTEM_LABEL=TUOLUMNE           # directory name under data/ and outputs/
SD_GPU_NAME=MI300                  # GPU column of the CSVs (matches the existing PingPong CSVs)
SD_GPU_ARCH=gfx942
SD_KOKKOS_ARCH=AMD_GFX942_APU
SD_GPUS_PER_NODE=4

# The stack is named by what decides ABI and performance; it names the install prefix.
SD_STACK_TAG="${SD_STACK_TAG:-rocm7.14-mpich9.1.0}"
SD_PREFIX_ROOT="${SD_PREFIX_ROOT:-/usr/workspace/${USER}/st-project/tuolumne}"

# Compilers for the whole stack: rocmcc's wrappers (ROCm clang + Cray MPICH). With the
# accelerator module loaded they link the GPU transport layer, so no extra link flags.
SD_CC="${SD_CC:-mpiamdclang}"
SD_CXX="${SD_CXX:-mpiamdclang++}"
SD_EXE_LINK_FLAGS="${SD_EXE_LINK_FLAGS:-}"
SD_SHARED_LINK_FLAGS="${SD_SHARED_LINK_FLAGS:-}"

# Tuolumne's libfabric is the system one (no libfabric module), as ST's install.sh and
# Resonance both found.
SD_LIBFABRIC_DIR="${SD_LIBFABRIC_DIR:-/usr/lib64}"

# Scheduler
SD_SCHEDULER=flux
SD_QUEUE="${SD_QUEUE:-pbatch}"
SD_BANK="${SD_BANK:-}"             # flux --bank, when your default bank isn't the right one

# Runtime environment for builds and jobs.
sd_system_env() {
    export HSA_XNACK=1
    # Cray MPICH's own libraries first: otherwise the loader can take the default MPICH's GTL
    # from /opt/cray/pe/lib64, which links ROCm 6's HIP (Resonance, Tuolumne 2026-09-29).
    export LD_LIBRARY_PATH="${CRAY_LD_LIBRARY_PATH:+${CRAY_LD_LIBRARY_PATH}:}${LD_LIBRARY_PATH:-}"
    if [ -z "${ROCM_PATH:-}" ] && command -v hipconfig &> /dev/null; then
        ROCM_PATH="$(hipconfig --rocmpath)"
        export ROCM_PATH
    fi
}

# Write one line per node into <outfile>.   sd_hostnames <nodes> <outfile>
sd_hostnames() {
    sd_run flux run -N "$1" --tasks-per-node=1 --output="$2" -o output.mode=append hostname
}

# Launch one step inside an allocation, appending its output (stdout and stderr) to <outfile>.
#   sd_launch <nodes> <ppn> <outfile> <st: 0|1> <command...>
# SD_STEP_MINUTES limits each step (a hung run then costs minutes, not the job); SD_LAUNCH_ARGS goes before the command
# (a profiler, for example). <st> is unused here: Tuolumne needs no extra flags for ST runs.
sd_launch() {
    local nodes="$1" ppn="$2" out="$3"
    shift 4
    # shellcheck disable=SC2086 # SD_LAUNCH_ARGS is a list of words
    sd_run flux run -x -N "$nodes" --tasks-per-node="$ppn" \
        ${SD_STEP_MINUTES:+--time-limit="${SD_STEP_MINUTES}m"} \
        --output="$out" -o output.mode=append ${SD_LAUNCH_ARGS:-} "$@"
}

# Submit a batch job and print its job id.
#   sd_submit <nodes> <minutes> <name> <log> <after-job-id or ""> <script> [VAR=value...]
# The job gets the submitting environment plus the VAR=value pairs.
sd_submit() {
    local nodes="$1" minutes="$2" name="$3" log="$4" after="$5" script="$6"
    shift 6
    local args=(--nodes="$nodes" --exclusive --time-limit="${minutes}m" --queue="$SD_QUEUE"
                --job-name="$name" --output="$log")
    [ -n "$SD_BANK" ] && args+=(--bank="$SD_BANK")
    [ -n "$after" ] && args+=(--dependency=afterany:"$after")
    local kv
    for kv in "$@"; do
        args+=(--env="$kv")
    done
    if sd_dry; then
        echo "+ flux batch ${args[*]} $script" >&2
        echo "dry-${name}"
    else
        flux batch "${args[@]}" "$script"
    fi
}
