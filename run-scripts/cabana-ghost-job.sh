#!/bin/bash
# One CabanaGhost allocation: every GPUs-per-node count x problem size x variant, at the
# allocation's node count. Submitted by submit.sh, which sets SD_* and the CBG_* preset variables;
# the scheduler runs a copy of this file, so the repository is found through SD_ROOT.
#
# Variants are <backend>-<buffering>-<memory>:
#   cxi-db-coarse  ST ready sends (MPI_ADVANCE_DOUBLE_BUFFERING=1, Cabana's default)
#   cxi-sb-coarse  ST standard sends (MPI_ADVANCE_DOUBLE_BUFFERING=0)
#   cxi-*-fine     the same with fine-grained memory (MPI_ADVANCE_FINEGRAIN_MEMORY=1)
#   mpi-sb-coarse  Cray MPICH, GPU-aware (MPICH_GPU_SUPPORT_ENABLED=1)
# Output: a "Test: <backend> <buffering> <memory> <nodes> <ppn> <size> <iters>" line, gol's
# output, then "Exit: <code>", per run. CabanaGhost/out-to-csv.py reads it.

set -uo pipefail   # not -e: one failed run shouldn't end the allocation

source "${SD_ROOT:?not set: submit with run-scripts/submit.sh}/systems/common.sh"
sd_load_system "$SD_SYSTEM"

NODES="$SD_JOB_NODES"
OUT="${SD_RUN_DIR}/${SD_SYSTEM_LABEL}-${NODES}N-r${SD_JOB_REPEAT}.out"
GOL="${SD_PREFIX}/cabanaghost/bin/gol"
[ -x "$GOL" ] || sd_dry || sd_die "no $GOL"

sd_run_header "$OUT" "$NODES"

run_variant() {
    local variant="$1" ppn="$2" size="$3"
    local backend buffering memory
    IFS=- read -r backend buffering memory <<< "$variant"
    local comm st=0
    local env=()
    case "$backend" in
        cxi)
            comm=mpi-advance
            st=1
            env+=(MPI_ADVANCE_STREAM_BACKEND=CXI)
            case "$buffering" in
                db) env+=(MPI_ADVANCE_DOUBLE_BUFFERING=1) ;;
                sb) env+=(MPI_ADVANCE_DOUBLE_BUFFERING=0) ;;
                *) sd_warn "bad buffering in '$variant'"; return ;;
            esac
            case "$memory" in
                coarse) env+=(MPI_ADVANCE_FINEGRAIN_MEMORY=0) ;;
                fine) env+=(MPI_ADVANCE_FINEGRAIN_MEMORY=1) ;;
                *) sd_warn "bad memory type in '$variant'"; return ;;
            esac
            ;;
        mpi)
            [ "$variant" = "mpi-sb-coarse" ] || { sd_warn "Cray MPICH runs only as mpi-sb-coarse, not '$variant'"; return; }
            comm=mpi
            env+=(MPICH_GPU_SUPPORT_ENABLED=1)
            ;;
        *)
            sd_warn "unknown variant '$variant'"
            return
            ;;
    esac
    echo "Test: $backend $buffering $memory $NODES $ppn $size $CBG_ITERS" >> "$OUT"
    local rc=0
    ( export "${env[@]}"
      sd_launch "$NODES" "$ppn" "$OUT" "$st" "$GOL" -n "$size" -c "$comm" \
          -t "$CBG_ITERS" -p "$CBG_PRINT_FREQ" ) || rc=$?
    echo "Exit: $rc" >> "$OUT"
}

for ppn in $CBG_PPN; do
    if [ "$ppn" -gt "$SD_GPUS_PER_NODE" ]; then
        sd_warn "skipping $ppn GPUs per node: ${SD_SYSTEM} has $SD_GPUS_PER_NODE"
        continue
    fi
    for size in $CBG_SIZES; do
        for variant in $CBG_VARIANTS; do
            run_variant "$variant" "$ppn" "$size"
        done
    done
done
