#!/bin/bash
# One packing ping-pong trial on two nodes: every size x test, with the pair on one node
# (ON-NODE: 1 node, 2 ranks) and on two (OFF-NODE: 2 nodes, 1 rank each). Submitted by submit.sh,
# which sets SD_* and the PP_* preset variables. Replaces stream-triggering's
# tests/benchmark/{bandwidth,f_bandwidth}_script.sh for the paper runs; the benchmarks are the
# ones build-scripts/build.sh put in <prefix>/pingpong.
#
# Tests (PP_TESTS):
#   st-cxi-coarse             ST Send (sb) and Rsend (db), on- and off-node
#   st-cxi-fine               the same, fine-grained memory
#   st-cxi-coarse-no-credit   ST Send off-node with MPIA_ST_DISABLE_CREDIT=1
#   st_raw-cxi-coarse         ST without packing kernels (sb)
#   mpi                       Cray MPICH Send (sb) and Rsend (db), on- and off-node
#   mpi_raw                   Cray MPICH without packing kernels (sb)
#   ipc                       direct HIP IPC, on-node only
# Output: "Test: <test> <sb|db> <ON-NODE|OFF-NODE> <iters> <ints>", the benchmark's output,
# then "Exit: <code>", per run. PingPong/out-to-csv.py reads it.

set -uo pipefail   # not -e: one failed run shouldn't end the trial

source "${SD_ROOT:?not set: submit with run-scripts/submit.sh}/systems/common.sh"
sd_load_system "$SD_SYSTEM"

OUT="${SD_RUN_DIR}/${SD_SYSTEM_LABEL}-${SD_JOB_NODES}N-r${SD_JOB_REPEAT}.out"
EXECS="${SD_PREFIX}/pingpong"
[ "$SD_JOB_NODES" -ge 2 ] || sd_die "ping-pong needs 2 nodes for its off-node pair"
[ -d "$EXECS" ] || sd_dry || sd_die "no $EXECS: build the pingpong component"

export MPICH_GPU_SUPPORT_ENABLED=1
# A hung exchange costs minutes, not the trial
export SD_STEP_MINUTES="${SD_STEP_MINUTES:-5}"

sd_run_header "$OUT" 2

# The paper's iteration counts (100k below 4 MB, 10k to 64 MB, 1k above), divided for smoke runs
iterations() {
    local items="$1" n
    if [ "$items" -ge 16777216 ]; then
        n=1000
    elif [ "$items" -ge 1048576 ]; then
        n=10000
    else
        n=100000
    fi
    n=$((n / PP_ITER_DIVISOR))
    [ "$n" -lt 10 ] && n=10
    echo "$n"
}

run_one() {
    local test="$1" exe="$2" mode="$3" topo="$4" st="$5" iters="$6" items="$7"
    local nodes=2 ppn=1
    [ "$topo" = "ON-NODE" ] && nodes=1 ppn=2
    if [ ! -x "$exe" ] && ! sd_dry; then
        echo "# missing $exe: $test $mode $topo skipped" >> "$OUT"
        return
    fi
    echo "Test: $test $mode $topo $iters $items" >> "$OUT"
    local rc=0
    sd_launch "$nodes" "$ppn" "$OUT" "$st" "$exe" "$iters" "$items" || rc=$?
    echo "Exit: $rc" >> "$OUT"
}

# run_test <test> <iters> <items>: every mode and placement that test runs in
run_test() {
    local test="$1" iters="$2" items="$3"
    local bench variant="" modes="sb db" topos="ON-NODE OFF-NODE" st=0
    case "$test" in
        st-cxi-coarse) bench=st variant=cxi-coarse st=1 ;;
        st-cxi-fine) bench=st variant=cxi-fine st=1 ;;
        st-cxi-coarse-no-credit) bench=st variant=cxi-coarse st=1 modes=sb topos=OFF-NODE ;;
        st_raw-cxi-coarse) bench=st_raw variant=cxi-coarse st=1 modes=sb ;;
        mpi) bench=mpi ;;
        mpi_raw) bench=mpi_raw modes=sb ;;
        ipc) bench=ipc modes=sb topos=ON-NODE ;;
        *) sd_warn "unknown test '$test'"; return ;;
    esac
    local mode topo exe
    for topo in $topos; do
        for mode in $modes; do
            exe="${EXECS}/pingpong_${bench}"
            [ "$mode" = db ] && exe+="_db"
            [ -n "$variant" ] && exe+="_${variant}"
            if [ "$test" = st-cxi-coarse-no-credit ]; then
                ( export MPIA_ST_DISABLE_CREDIT=1
                  run_one "$test" "$exe" "$mode" "$topo" "$st" "$iters" "$items" )
            else
                run_one "$test" "$exe" "$mode" "$topo" "$st" "$iters" "$items"
            fi
        done
    done
}

for (( exp=PP_START_EXP; exp<=PP_END_EXP; exp++ )); do
    items=$((2 ** exp))
    iters="$(iterations "$items")"
    echo "# round: $iters iterations of $items ints" >> "$OUT"
    for test in $PP_TESTS; do
        run_test "$test" "$iters" "$items"
    done
done
