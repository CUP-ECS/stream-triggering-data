#!/bin/bash
# shellcheck disable=SC2034 # settings: read by the scripts that source this file
# ORNL Frontier: 4x MI250X (8 GCDs) per node, Slurm. Sourced by sd_load_system in common.sh.
# DRAFT for Phase 5: nothing here has been run yet. The compilers and link flags are the ones the
# old build-scripts/cabana-ghost.sh -T 2 used, and the srun network flags the ones ST's Frontier
# scripts use.

SD_SYSTEM=frontier
SD_SYSTEM_LABEL=FRONTIER
SD_GPU_NAME=MI250
SD_GPU_ARCH=gfx90a
SD_KOKKOS_ARCH=AMD_GFX90A
SD_GPUS_PER_NODE=8

SD_STACK_TAG="${SD_STACK_TAG:-rocm7.13-cpe26.03}"
SD_PREFIX_ROOT="${SD_PREFIX_ROOT:-${HOME}/st-project/frontier}"

SD_CC="${SD_CC:-amdclang}"
SD_CXX="${SD_CXX:-amdclang++}"
# amdclang isn't a Cray wrapper, so the GPU transport layer is linked by hand.
SD_EXE_LINK_FLAGS="${SD_EXE_LINK_FLAGS:-${PE_MPICH_GTL_DIR_amd_gfx90a:-} ${PE_MPICH_GTL_LIBS_amd_gfx90a:-}}"
SD_SHARED_LINK_FLAGS="${SD_SHARED_LINK_FLAGS:-${SD_EXE_LINK_FLAGS}}"

SD_LIBFABRIC_DIR="${SD_LIBFABRIC_DIR:-/opt/cray/libfabric/2.3.1}"

SD_SCHEDULER=slurm
SD_ACCOUNT="${SD_ACCOUNT:-csc698}"
SD_PARTITION="${SD_PARTITION:-batch}"
SD_QOS="${SD_QOS:-}"

sd_system_env() {
    export HSA_XNACK=1
    export LD_LIBRARY_PATH="${CRAY_LD_LIBRARY_PATH:+${CRAY_LD_LIBRARY_PATH}:}${LD_LIBRARY_PATH:-}"
    if [ -z "${ROCM_PATH:-}" ] && command -v hipconfig &> /dev/null; then
        ROCM_PATH="$(hipconfig --rocmpath)"
        export ROCM_PATH
    fi
}

sd_hostnames() {
    sd_run srun -N "$1" --ntasks-per-node=1 --output="$2" --open-mode=append hostname
}

# sd_launch <nodes> <ppn> <outfile> <st: 0|1> <command...>
# ST runs get a VNI and their share of the node's 1024 trigger-list entries (TLEs).
sd_launch() {
    local nodes="$1" ppn="$2" out="$3" st="$4"
    shift 4
    local net=()
    [ "$st" = "1" ] && net=(--network="single_node_vni,job_vni,def_tles=$((1024 / ppn))")
    # shellcheck disable=SC2086 # SD_LAUNCH_ARGS is a list of words
    sd_run srun "${net[@]}" -N "$nodes" --ntasks-per-node="$ppn" \
        --gpus-per-task=1 --gpu-bind=closest \
        ${SD_STEP_MINUTES:+--time="$SD_STEP_MINUTES"} \
        --output="$out" --open-mode=append ${SD_LAUNCH_ARGS:-} "$@"
}

# sd_submit <nodes> <minutes> <name> <log> <after-job-id or ""> <script> [VAR=value...]
sd_submit() {
    local nodes="$1" minutes="$2" name="$3" log="$4" after="$5" script="$6"
    shift 6
    local export_list="ALL"
    local kv
    for kv in "$@"; do
        export_list+=",$kv"
    done
    local args=(--parsable --nodes="$nodes" --exclusive --time="$minutes"
                --account="$SD_ACCOUNT" --partition="$SD_PARTITION"
                --job-name="$name" --output="$log" --export="$export_list")
    [ -n "$SD_QOS" ] && args+=(--qos="$SD_QOS")
    [ -n "$after" ] && args+=(--dependency=afterany:"$after")
    if sd_dry; then
        echo "+ sbatch ${args[*]} $script" >&2
        echo "dry-${name}"
    else
        sbatch "${args[@]}" "$script"
    fi
}
