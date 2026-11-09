#!/bin/bash
# What each experiment runs, per system and preset. Sourced by submit.sh; don't run it.
#
#   sd_preset <experiment> <preset>     experiment: pingpong | cabana-ghost | acg
#                                       preset:     smoke | full
#
# Every variable can be overridden from the environment (they're all ${VAR:-default}), so a
# one-off sweep doesn't need a new preset:  SD_NODE_LIST="4 8" submit.sh -x cabana-ghost -P full ...
#
# Common to all experiments:
#   SD_NODE_LIST   node counts; one batch job per node count per repeat
#   SD_REPEATS     independent trials (the paper used 5). Repeat r of every node count is its
#                  own job, so each trial gets its own allocation
#   SD_JOB_MINUTES wall-time limit of each job
#   SD_CHAIN       all: every job waits for the one before it; repeat: jobs within a repeat
#                  wait for each other, repeats run side by side; none: no dependencies

sd_preset() {
    local exp="$1" preset="$2" key="${SD_SYSTEM}:$1:$2"
    case "$key" in
        # --- Packing ping-pong (Fig. 5): 2 nodes, on-node and off-node pairs ---------------
        # Sizes are 2^exp ints (4 B to 1 GiB). The iteration counts are the paper's: 100k below
        # 4 MB, 10k up to 64 MB, 1k above, divided by PP_ITER_DIVISOR.
        *:pingpong:full)
            SD_NODE_LIST="${SD_NODE_LIST:-2}"
            SD_REPEATS="${SD_REPEATS:-5}"
            SD_JOB_MINUTES="${SD_JOB_MINUTES:-120}"
            PP_START_EXP="${PP_START_EXP:-0}"
            PP_END_EXP="${PP_END_EXP:-28}"
            PP_ITER_DIVISOR="${PP_ITER_DIVISOR:-1}"
            PP_TESTS="${PP_TESTS:-st-cxi-coarse mpi mpi_raw st_raw-cxi-coarse ipc}"
            ;;
        *:pingpong:smoke)
            SD_NODE_LIST="${SD_NODE_LIST:-2}"
            SD_REPEATS="${SD_REPEATS:-1}"
            SD_JOB_MINUTES="${SD_JOB_MINUTES:-30}"
            PP_START_EXP="${PP_START_EXP:-3}"
            PP_END_EXP="${PP_END_EXP:-22}"
            PP_ITER_DIVISOR="${PP_ITER_DIVISOR:-10}"
            PP_TESTS="${PP_TESTS:-st-cxi-coarse mpi ipc}"
            ;;

        # --- CabanaGhost Game of Life strong scaling (Figs. 6, 7, 9; Table III) ------------
        # Sizes: -n 61440 is the 30 GB problem, -n 16384 the 2 GB one. Fig. 9 (by halo edge
        # length) is computed from the same runs (1-2 GPUs per node), so it needs no sweep of
        # its own. Variants: <cxi|mpi>-<sb|db>-<coarse|fine>; cxi = ST (Send sb, Rsend db).
        tuolumne:cabana-ghost:full)
            SD_NODE_LIST="${SD_NODE_LIST:-1 2 4 8 16 32 64 128 256}"
            SD_REPEATS="${SD_REPEATS:-5}"
            SD_JOB_MINUTES="${SD_JOB_MINUTES:-30}"
            CBG_PPN="${CBG_PPN:-1 2 4}"
            ;;&
        frontier:cabana-ghost:full)
            SD_NODE_LIST="${SD_NODE_LIST:-1 2 4 8 16 32 64 128 256 512 1024}"
            SD_REPEATS="${SD_REPEATS:-5}"
            SD_JOB_MINUTES="${SD_JOB_MINUTES:-45}"   # five variants, not three
            CBG_PPN="${CBG_PPN:-1 2 4 8}"
            # Fine-grained memory too, as the paper's Frontier runs had: check it once against
            # coarse (CabanaGhost/scaling-analysis.py --memory-check), then pool (--pool-memory) or
            # drop it from later runs with CBG_VARIANTS
            CBG_VARIANTS="${CBG_VARIANTS:-cxi-db-coarse cxi-sb-coarse cxi-db-fine cxi-sb-fine mpi-sb-coarse}"
            ;;&
        *:cabana-ghost:full)
            CBG_SIZES="${CBG_SIZES:-16384 61440}"
            CBG_VARIANTS="${CBG_VARIANTS:-cxi-db-coarse cxi-sb-coarse mpi-sb-coarse}"
            CBG_ITERS="${CBG_ITERS:-1000}"
            CBG_PRINT_FREQ="${CBG_PRINT_FREQ:-200}"
            ;;
        *:cabana-ghost:smoke)
            SD_NODE_LIST="${SD_NODE_LIST:-1 2}"
            SD_REPEATS="${SD_REPEATS:-1}"
            SD_JOB_MINUTES="${SD_JOB_MINUTES:-15}"
            CBG_PPN="${CBG_PPN:-1 ${SD_GPUS_PER_NODE}}"
            CBG_SIZES="${CBG_SIZES:-16384}"
            CBG_VARIANTS="${CBG_VARIANTS:-cxi-db-coarse cxi-sb-coarse mpi-sb-coarse}"
            CBG_ITERS="${CBG_ITERS:-100}"
            CBG_PRINT_FREQ="${CBG_PRINT_FREQ:-50}"
            ;;

        # --- aCG CG solver strong scaling (Figs. 8, 10, 11; Table IV), Tuolumne only -------
        # Backends: mpi, st, rccl, and mpi-no-ipc (Cray MPICH with GPU IPC and the eager
        # protocol off: the Fig. 11 ablation).
        tuolumne:acg:full)
            SD_NODE_LIST="${SD_NODE_LIST:-1 2 4 8 16}"
            SD_REPEATS="${SD_REPEATS:-5}"
            SD_JOB_MINUTES="${SD_JOB_MINUTES:-60}"
            ACG_PPN="${ACG_PPN:-1 2 4}"
            ACG_MATRICES="${ACG_MATRICES:-Queen_4147 Bump_2911 audikw_1 Serena}"
            ACG_BACKENDS="${ACG_BACKENDS:-mpi st rccl mpi-no-ipc}"
            ;;&
        tuolumne:acg:smoke)
            SD_NODE_LIST="${SD_NODE_LIST:-1}"
            SD_REPEATS="${SD_REPEATS:-1}"
            SD_JOB_MINUTES="${SD_JOB_MINUTES:-30}"
            ACG_PPN="${ACG_PPN:-1 4}"
            ACG_MATRICES="${ACG_MATRICES:-Serena}"
            ACG_BACKENDS="${ACG_BACKENDS:-mpi st rccl}"
            ;;&
        tuolumne:acg:*)
            ACG_MATRIX_DIR="${ACG_MATRIX_DIR:-/usr/workspace/${USER}/aCG/input}"
            ACG_PARTITION_DIR="${ACG_PARTITION_DIR:-/usr/workspace/${USER}/aCG/partitions}"
            ;;

        *)
            sd_die "no preset '$preset' for experiment '$exp' on ${SD_SYSTEM}"
            ;;
    esac
    # Partition files are shared between jobs; aCG writes them atomically, but chaining keeps
    # jobs from computing the same one twice. The others only need separate allocations.
    case "$exp" in
        acg|pingpong) SD_CHAIN="${SD_CHAIN:-all}" ;;
        *) SD_CHAIN="${SD_CHAIN:-repeat}" ;;
    esac
    export SD_NODE_LIST SD_REPEATS SD_JOB_MINUTES SD_CHAIN
    export PP_START_EXP PP_END_EXP PP_ITER_DIVISOR PP_TESTS
    export CBG_PPN CBG_SIZES CBG_VARIANTS CBG_ITERS CBG_PRINT_FREQ
    export ACG_PPN ACG_MATRICES ACG_BACKENDS ACG_MATRIX_DIR ACG_PARTITION_DIR
}

# The variables a preset sets, for run-info.txt
sd_preset_vars() {
    case "$1" in
        pingpong) echo "PP_START_EXP PP_END_EXP PP_ITER_DIVISOR PP_TESTS" ;;
        cabana-ghost) echo "CBG_PPN CBG_SIZES CBG_VARIANTS CBG_ITERS CBG_PRINT_FREQ" ;;
        acg) echo "ACG_PPN ACG_MATRICES ACG_BACKENDS ACG_MATRIX_DIR ACG_PARTITION_DIR" ;;
    esac
}
