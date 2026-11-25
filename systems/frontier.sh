#!/bin/bash
# shellcheck disable=SC2034 # settings: read by the scripts that source this file
# ORNL Frontier: 4x MI250X (8 GCDs) per node, Slurm. Sourced by sd_load_system in common.sh.
# Phase 7 (the Frontier port): modules pinned from the login-node probe; launch flags from the
# meta repo's pre-flight job (knowledge/frontier/preflight-5994066). The compilers and link flags
# are the ones the old build-scripts/cabana-ghost.sh -T 2 used.

SD_SYSTEM=frontier
SD_SYSTEM_LABEL=FRONTIER
SD_GPU_NAME=MI250
SD_GPU_ARCH=gfx90a
SD_KOKKOS_ARCH=AMD_GFX90A
SD_GPUS_PER_NODE=8

SD_STACK_TAG="${SD_STACK_TAG:-rocm7.14-mpich9.1.0}"
# On Orion, not $HOME: home is writable from compute nodes (pre-flight 5994066), but it's NFS with
# a 50 GB quota, and Lustre serves 1024-node launches better. Member work is purged after 90 days
# unused.
SD_PREFIX_ROOT="${SD_PREFIX_ROOT:-${MEMBERWORK:-${HOME}}/csc698/st-project/frontier}"

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
    # aCG's METIS comes from the metis module (frontier.modules), not <prefix>/metis: it exports
    # OLCF_METIS_ROOT (probe, 2026-11-25). An explicit METIS_DIR wins.
    if [ -z "${METIS_DIR:-}" ] && [ -n "${OLCF_METIS_ROOT:-}" ]; then
        export METIS_DIR="$OLCF_METIS_ROOT"
    fi
    export LD_LIBRARY_PATH="${CRAY_LD_LIBRARY_PATH:+${CRAY_LD_LIBRARY_PATH}:}${LD_LIBRARY_PATH:-}"
    # Cray MPICH's NIC: the one on the rank's NUMA node, which --gpu-bind=closest makes its GPU's
    # NIC too, the NIC ST picks (pre-flight 5994066). That is already Frontier's default ("NIC
    # Mapping", OLCF Frontier user guide); set explicitly so runs don't depend on it.
    # SD_MPICH_NIC_POLICY=default leaves Cray MPICH's own default.
    if [ "${SD_MPICH_NIC_POLICY:-NUMA}" = default ]; then
        unset MPICH_OFI_NIC_POLICY
    else
        export MPICH_OFI_NIC_POLICY="${SD_MPICH_NIC_POLICY:-NUMA}"
    fi
    # OLCF's GPU-aware Cray MPICH settings ("GPU-Aware MPI", OLCF Frontier user guide): the HSA
    # IPC signal cache (Cray MPICH 9.1.0 on, "optional, but recommended") and AMD's legacy IPC mode
    # (the dma-buf mode "is not natively supported by Cray MPICH"). SD_OLCF_IPC_ENV=0 leaves both
    # unset, as every run before 2026-11-25's on-node check had them.
    if [ "${SD_OLCF_IPC_ENV:-1}" = 1 ]; then
        export GTL_ENABLE_HSA_IPC_SIGNAL_CACHE=1 HSA_ENABLE_IPC_MODE_LEGACY=1
    else
        unset GTL_ENABLE_HSA_IPC_SIGNAL_CACHE HSA_ENABLE_IPC_MODE_LEGACY
    fi
    if [ -z "${ROCM_PATH:-}" ] && command -v hipconfig &> /dev/null; then
        ROCM_PATH="$(hipconfig --rocmpath)"
        export ROCM_PATH
    fi
}

# Also a health check of the allocation, limited to SD_HOSTNAME_MINUTES (default 2), as on Tuolumne.
sd_hostnames() {
    sd_run srun -N "$1" --ntasks-per-node=1 --time="${SD_HOSTNAME_MINUTES:-2}" \
        --output="$2" --open-mode=append hostname
}

# sd_launch <nodes> <ppn> <outfile> <st: 0|1> <command...>
# Placement (pre-flight 5994066): one CCD's 7 cores and the closest GCD per rank, so each rank's
# CPU, GPU and NIC share a NUMA node. Without --gpus-per-task every rank sees all 8 GCDs, and ST
# (no hipSetDevice) puts them all on GCD 0 and cxi0. SD_CPUS_PER_TASK changes -c;
# SD_GPU_BIND=none drops the GPU binding (the paper-era launch, with SD_CPUS_PER_TASK=1).
# ST runs need a VNI on one node too (single_node_vni: fi_domain fails with ENOSYS without it)
# and reserved trigger-list entries (without them FI_QUEUE_WORK fails with EAGAIN). res_tles is
# per node; def_tles is per CPU, so def_tles=128 with -c7 asks for more than Slurm can give
# ("Error configuring interconnect").
sd_launch() {
    local nodes="$1" ppn="$2" out="$3" st="$4"
    shift 4
    local net=() gpu=()
    [ "$st" = "1" ] && net=(--network="${SD_ST_NETWORK:-single_node_vni,job_vni,res_tles=1024}")
    case "${SD_GPU_BIND:-closest}" in
        none) ;;
        *) gpu=(--gpus-per-task=1 --gpu-bind="${SD_GPU_BIND:-closest}") ;;
    esac
    # shellcheck disable=SC2086 # SD_LAUNCH_ARGS is a list of words
    sd_run srun "${net[@]}" -N "$nodes" --ntasks-per-node="$ppn" \
        -c "${SD_CPUS_PER_TASK:-7}" "${gpu[@]}" \
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
