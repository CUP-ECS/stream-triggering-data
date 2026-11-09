#!/bin/bash
# One aCG allocation: every GPUs-per-node count x matrix x backend, at the allocation's node
# count. Submitted by submit.sh, which sets SD_* and the ACG_* preset variables; the scheduler
# runs a copy of this file, so the repository is found through SD_ROOT.
#
# Backends:
#   mpi         Cray MPICH, GPU-aware (--comm mpi)
#   mpi-no-ipc  the same with GPU IPC and the eager protocol off: the paper's Fig. 11 ablation
#               (MPICH_GPU_IPC_ENABLED=0 FI_CXI_RDZV_THRESHOLD=0 FI_CXI_RDZV_EAGER_SIZE=0)
#   st          stream-triggered sends for the halo exchange (--comm st)
#   rccl        RCCL (--comm rccl), with aws-ofi-nccl from <prefix>/ofi-nccl when it was built
#
# Matrices are <ACG_MATRIX_DIR>/<name>.mtx. A missing partition file
# (<ACG_PARTITION_DIR>/<name>_<parts>_parts.mtx) is made with mtxpartition first.
# Output: a "Test: <backend> <nodes> <ppn> <matrix>" line, aCG's output, then "Exit: <code>",
# per run. aCG/out-to-csv.py reads it.

set -uo pipefail   # not -e: one failed run shouldn't end the allocation

source "${SD_ROOT:?not set: submit with run-scripts/submit.sh}/systems/common.sh"
sd_load_system "$SD_SYSTEM"

NODES="$SD_JOB_NODES"
OUT="${SD_RUN_DIR}/${SD_SYSTEM_LABEL}-${NODES}N-r${SD_JOB_REPEAT}.out"
ACG="${SD_PREFIX}/acg/bin/acg-hip"
MTXPARTITION="${SD_PREFIX}/acg/bin/mtxpartition"
OFI_NCCL_LIB="${SD_PREFIX}/ofi-nccl/lib"
for exe in "$ACG" "$MTXPARTITION"; do
    [ -x "$exe" ] || sd_dry || sd_die "no $exe"
done
mkdir -p "$ACG_PARTITION_DIR"

export MPICH_GPU_SUPPORT_ENABLED=1
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-7}"

sd_run_header "$OUT" "$NODES"
if [ -d "$OFI_NCCL_LIB" ]; then
    echo "# rccl: aws-ofi-nccl from $OFI_NCCL_LIB" >> "$OUT"
else
    echo "# rccl: no aws-ofi-nccl in this prefix (RCCL's own transport)" >> "$OUT"
fi

# Make <file> with mtxpartition unless it exists. Written to a temporary name and moved into
# place, so a job that dies (or a second job) never leaves a half-written partition behind.
make_partition() {
    local matrix_file="$1" parts="$2" file="$3"
    [ -s "$file" ] && return 0
    if sd_dry; then
        echo "+ $MTXPARTITION --parts=$parts $matrix_file > $file" >&2
        return 0
    fi
    echo "# making $file" >> "$OUT"
    local tmp="${file}.tmp.$$"
    if sd_run "$MTXPARTITION" --parts="$parts" "$matrix_file" > "$tmp" 2>> "$OUT"; then
        mv "$tmp" "$file"
    else
        rm -f "$tmp"
        return 1
    fi
}

run_backend() {
    local backend="$1" ppn="$2" matrix="$3" matrix_file="$4" partition="$5"
    local comm st=0
    local env=()
    case "$backend" in
        mpi) comm=mpi ;;
        mpi-no-ipc)
            comm=mpi
            env+=(MPICH_GPU_IPC_ENABLED=0 FI_CXI_RDZV_THRESHOLD=0 FI_CXI_RDZV_EAGER_SIZE=0)
            ;;
        st) comm=st; st=1 ;;
        rccl)
            comm=rccl
            # The settings Derek's earlier runs used with aws-ofi-nccl
            env+=(NCCL_NET_GDR_LEVEL=PHB NCCL_CROSS_NIC=1 HSA_FORCE_FINE_GRAIN_PCIE=1
                  FI_MR_CACHE_MONITOR=userfaultfd FI_CXI_DISABLE_HOST_REGISTER=1
                  FI_CXI_DEFAULT_CQ_SIZE=131072 FI_CXI_RDZV_PROTO=alt_read
                  FI_CXI_RX_MATCH_MODE=hybrid FI_CXI_RDZV_EAGER_SIZE=0 FI_CXI_DEFAULT_TX_SIZE=2048)
            [ -d "$OFI_NCCL_LIB" ] && env+=(LD_LIBRARY_PATH="${OFI_NCCL_LIB}:${LD_LIBRARY_PATH:-}")
            ;;
        *) sd_warn "unknown backend '$backend'"; return ;;
    esac
    echo "Test: $backend $NODES $ppn $matrix" >> "$OUT"
    local rc=0
    ( [ ${#env[@]} -gt 0 ] && export "${env[@]}"
      sd_launch "$NODES" "$ppn" "$OUT" "$st" "$ACG" "$matrix_file" --partition="$partition" \
          --seed 101 --residual-atol 0 --residual-rtol 1e-6 --max-iterations 100000 \
          --solver acg --comm "$comm" --manufactured-solution --verbose -q ) || rc=$?
    echo "Exit: $rc" >> "$OUT"
}

for ppn in $ACG_PPN; do
    if [ "$ppn" -gt "$SD_GPUS_PER_NODE" ]; then
        sd_warn "skipping $ppn GPUs per node: ${SD_SYSTEM} has $SD_GPUS_PER_NODE"
        continue
    fi
    parts=$((NODES * ppn))
    for matrix in $ACG_MATRICES; do
        matrix_file="${ACG_MATRIX_DIR}/${matrix}.mtx"
        if [ ! -f "$matrix_file" ] && ! sd_dry; then
            echo "# missing matrix $matrix_file: skipped" >> "$OUT"
            continue
        fi
        partition="${ACG_PARTITION_DIR}/${matrix}_${parts}_parts.mtx"
        if ! make_partition "$matrix_file" "$parts" "$partition"; then
            echo "# mtxpartition failed for $matrix ($parts parts): skipped" >> "$OUT"
            continue
        fi
        for backend in $ACG_BACKENDS; do
            run_backend "$backend" "$ppn" "$matrix" "$matrix_file" "$partition"
        done
    done
done
