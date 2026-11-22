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
#   mpi_nosdma-sb-coarse  the same with HSA_ENABLE_SDMA=0 (GPU copies by kernels, not the SDMA
#                  engines); not in any preset: add it with CBG_VARIANTS
# CBG_WARMUP=1 (the presets' default) runs gol -w: two untimed halo exchanges and a barrier before
# the timed solve, and a barrier after it, so one-time communication costs (Cray MPICH's first GPU
# IPC copy sets up an SDMA queue: ~0.1 s per run) stay out of the solve time. Needs CabanaGhost
# dc029f9 or later. CBG_WARMUP=0 times the solve as the paper era did.
# Output: a "Test: <backend> <buffering> <memory> <nodes> <ppn> <size> <iters>" line, gol's
# output, then "Exit: <code>", per run. CabanaGhost/out-to-csv.py reads it.

set -uo pipefail   # not -e: one failed run shouldn't end the allocation

source "${SD_ROOT:?not set: submit with run-scripts/submit.sh}/systems/common.sh"
sd_load_system "$SD_SYSTEM"

NODES="$SD_JOB_NODES"
OUT="${SD_RUN_DIR}/${SD_SYSTEM_LABEL}-${NODES}N-r${SD_JOB_REPEAT}.out"
GOL="${SD_PREFIX}/cabanaghost/bin/gol"
[ -x "$GOL" ] || sd_dry || sd_die "no $GOL"
WARMUP_ARG=()
if [ "${CBG_WARMUP:-1}" = 1 ]; then
    WARMUP_ARG=(-w)
    sd_dry || grep -q 'Untimed warm-up' "$GOL" \
        || sd_die "CBG_WARMUP=1 but $GOL has no -w: rebuild CabanaGhost (dc029f9 or later), or set CBG_WARMUP=0"
fi

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
        mpi|mpi_nosdma)
            [ "$buffering-$memory" = "sb-coarse" ] || { sd_warn "Cray MPICH runs only as $backend-sb-coarse, not '$variant'"; return; }
            comm=mpi
            env+=(MPICH_GPU_SUPPORT_ENABLED=1)
            [ "$backend" = mpi_nosdma ] && env+=(HSA_ENABLE_SDMA=0)
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
          -t "$CBG_ITERS" -p "$CBG_PRINT_FREQ" "${WARMUP_ARG[@]}" ) || rc=$?
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
