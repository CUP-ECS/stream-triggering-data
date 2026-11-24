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
# Diagnostic backends (Phase 6, aCG's setup crash; knowledge/phase6-plan.md in ST-project-testing):
# each is `mpi` with one change, so an A/B against `mpi` isolates it.
#   mpi-eager-off   FI_CXI_RDZV_THRESHOLD=0 FI_CXI_RDZV_EAGER_SIZE=0 (mpi-no-ipc's eager half)
#   mpi-ipc-off     MPICH_GPU_IPC_ENABLED=0 (mpi-no-ipc's IPC half)
#   mpi-mrcache-off FI_MR_CACHE_MAX_COUNT=0: libfabric's memory-registration cache off. On
#                   Tuolumne's CXI, MPI_Init then fails (fi_open domain: Invalid argument)
#   mpi-omp1        OMP_NUM_THREADS=1: aCG's host setup without OpenMP threads
#   mpi-xnack0      HSA_XNACK=0 (the system environment sets 1; the paper-era aCG script didn't)
#   mpi-uffd        FI_MR_CACHE_MONITOR=userfaultfd: libfabric watches registered memory with
#                   userfaultfd instead of its default (the setting the paper-era rccl runs used)
# mpi-omp1 and mpi-xnack0 change a value without changing its length, so the environment's size,
# and with it the processes' memory layout, stays the same as mpi's.
#
# Modifiers, appended to any backend with '+' (e.g. mpi-ipc-off+pad7+gdb):
#   +pad<N>   adds ACG_PAD=<N x's> to the environment: shifts the processes' memory layout by N bytes
#             and changes nothing else (does a crash follow layout rather than MPI settings?)
#   +gdb      runs every rank under gdb -batch (rocgdb if there's no gdb) and prints a backtrace
#             where it stops (e.g. glibc's abort). No shell in between, and gdb's LINES/COLUMNS are
#             unset, so the program's environment is the same as without gdb
#   +asan     runs <prefix>/acg/bin/acg-hip-asan (build-scripts/build.sh acg-asan) instead, with
#             ASAN_OPTIONS for a GPU runtime (no shadow-gap protection, no leak check); a report
#             stops the rank and names the bad access and where its memory came from
#   +alt      runs ACG_ALT_EXE (another acg-hip build, e.g. an older one) instead, same environment
#   +g        runs <prefix>/acg/bin/acg-hip-g (build-scripts/build.sh acg-g): the same code with debug
#             information, so backtraces from cores name functions and lines
#   +mcheck   MALLOC_CHECK_=3: glibc's checking malloc, which checks each block when it's freed and
#             aborts at the first damaged one (glibc 2.28 has it built in)
#   +perturb  MALLOC_PERTURB_=165: glibc fills new and freed blocks with a pattern, so reading
#             uninitialised or freed heap memory gives the same wrong value every time
#
# Diagnostics (all off by default):
#   ACG_CORE_DIR=<dir>  core files on (ulimit -c unlimited; without it, ulimit -c 0). Each run starts
#                       in <dir>/run-NNNN, where the kernel writes <host>-<program>-<pid>.core. <dir>
#                       must be absolute and outside $HOME (a core can be GBs). After the run, gdb
#                       reads up to ACG_CORE_BT_MAX (2) cores per run, ACG_CORE_BT_TOTAL (24) per job,
#                       into <run dir>/cores/run-NNNN-<core>.txt (backtraces of every thread, the
#                       rank and its environment's size, the memory map), with the crashing
#                       thread's top frames as "# core" lines in the output. The first
#                       ACG_CORE_KEEP (4) cores gdb read are kept for a closer look; the rest are
#                       deleted. Once ACG_CORE_BT_TOTAL runs have left cores, later runs get
#                       ulimit -c 0 (still run in their own run-NNNN, so the layout is unchanged):
#                       cores nobody reads aren't written.
#   ACG_HANG_SECONDS=<s> a run still going after <s> seconds gets SIGABRT on every rank (flux exec
#                       pkill on every node), so with ACG_CORE_DIR set a hang leaves cores showing
#                       where each rank was
#   ACG_FOLLOWUP="<backends>"  after each configuration's runs, every backend run with +pad<N> that
#                       didn't finish setup (no "setting up initial guess") is followed up: each of
#                       these backends runs with that +pad<N>, for the first ACG_FOLLOWUP_MAX (4)
#                       such pads. A crash found by a padding sweep is then tested where it happens.
#                       ACG_FOLLOWUP_FROM=<backend> counts only that backend's crashes (e.g. mpi+g
#                       for mpi+g+pad<N>), so a diagnostic arm in the sweep doesn't start follow-ups
#
# ACG_TRIALS (default 1) runs every configuration that many times in this allocation, the backends
# interleaved within each trial. ACG_MAX_ITERATIONS (default 100000) caps the solver; a run that
# stops at the cap exits 1 ("not converged"), so a small cap is only for testing setup.
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
ACG_TRIALS="${ACG_TRIALS:-1}"
ACG_MAX_ITERATIONS="${ACG_MAX_ITERATIONS:-100000}"
GDB="$(command -v gdb || command -v rocgdb || true)"
ACG_CORE_DIR="${ACG_CORE_DIR:-}"
ACG_HANG_SECONDS="${ACG_HANG_SECONDS:-0}"
ACG_FOLLOWUP="${ACG_FOLLOWUP:-}"
CORE_TXT_DIR="${SD_RUN_DIR}/cores"
RUN_SEQ=0 CORE_BTS=0 CORE_RUNS=0 CORES_KEPT=0 SETUP_OK=1
CRASHED_PADS=()

# Cores: off unless ACG_CORE_DIR is set, and then only there. flux run passes this script's limits
# on to every rank. (The default soft limit, 32 KiB, would leave truncated cores in the directory
# the job was submitted from.)
if [ -n "$ACG_CORE_DIR" ]; then
    case "$ACG_CORE_DIR" in
        /*) ;;
        *) sd_die "ACG_CORE_DIR must be an absolute path: $ACG_CORE_DIR" ;;
    esac
    case "$(realpath -m "$ACG_CORE_DIR")/" in
        "$(realpath -m "$HOME")"/*) sd_die "ACG_CORE_DIR is under \$HOME ($HOME): a core can be GBs" ;;
    esac
    ulimit -c unlimited
    if ! sd_dry; then
        mkdir -p "$ACG_CORE_DIR" "$CORE_TXT_DIR"
        # Three files: gdb stops a command file at its first error, so a command the core can't
        # answer only loses its own section.
        cat > "$CORE_TXT_DIR/main.gdb" << 'GDB'
set pagination off
set width 0
set print frame-arguments scalars
printf "== crash\n"
bt 16
printf "== threads\n"
info threads
printf "== all threads\n"
thread apply all bt
printf "== crash, full\n"
bt full
GDB
        # The rank and the environment's size (the layout variable), from libc's environ (gdb's
        # plain `environ` is the loader's stale copy). Python reads the core's memory; nothing
        # else of the environment is written out.
        cat > "$CORE_TXT_DIR/env.gdb" << 'GDB'
printf "== environment\n"
python
import re
def _libc_environ():
    """Address of libc's environ. gdb's plain `environ` may be the dynamic loader's copy, which
    still points at the initial array; setenv() changes libc's."""
    cands = []
    for cmd in ("info variables ^environ$", "info variables ^__environ$"):
        try:
            cands += [int(a, 16) for a in re.findall(r"^(0x[0-9a-f]+)\s+_*environ\s*$",
                                                      gdb.execute(cmd, to_string=True), re.M)]
        except gdb.error:
            pass
    for expr in ("&environ", "&__environ", "&'libc.so.6'::environ"):
        try:
            cands.append(int(gdb.parse_and_eval("(long) " + expr)))
        except gdb.error:
            pass
    try:
        m = re.search(r"at address (0x[0-9a-f]+)", gdb.execute("info address environ", to_string=True))
        if m:
            cands.append(int(m.group(1), 16))
    except gdb.error:
        pass
    for a in cands:
        if "libc.so" in gdb.execute("info symbol 0x%x" % a, to_string=True):
            return a, True
    return cands[0], False
addr, ok = _libc_environ()
charpp = gdb.lookup_type("char").pointer().pointer()
env = gdb.Value(addr).cast(charpp.pointer()).dereference()
n = size = 0
while int(env[n]) != 0:
    s = env[n].string(errors="replace")
    if s.startswith("FLUX_TASK_RANK="):
        print("rank-env: " + s)
    size += len(s.encode(errors="replace")) + 1
    n += 1
print("rank-env: %d variables, %d bytes%s" % (n, size, "" if ok else " (maybe the loader's environ)"))
end
GDB
        cat > "$CORE_TXT_DIR/maps.gdb" << 'GDB'
printf "== mappings\n"
info proc mappings
GDB
    fi
else
    ulimit -c 0
fi

sd_run_header "$OUT" "$NODES"
if [ -d "$OFI_NCCL_LIB" ]; then
    echo "# rccl: aws-ofi-nccl from $OFI_NCCL_LIB" >> "$OUT"
else
    echo "# rccl: no aws-ofi-nccl in this prefix (RCCL's own transport)" >> "$OUT"
fi
echo "# trials per configuration: $ACG_TRIALS; max iterations: $ACG_MAX_ITERATIONS" >> "$OUT"
if [ -n "$ACG_CORE_DIR" ]; then
    echo "# cores: $ACG_CORE_DIR/run-NNNN (gdb: ${GDB:-none}), backtraces in cores/" >> "$OUT"
    # What a rank actually gets (flux run should pass this script's limit on)
    sd_dry || echo "# core limit in a rank: $(flux run -N1 -n1 sh -c 'ulimit -c' 2>&1 | tail -1)" >> "$OUT"
fi
[ "$ACG_HANG_SECONDS" -gt 0 ] && echo "# hang watchdog: SIGABRT after $ACG_HANG_SECONDS s" >> "$OUT"
[ -n "$ACG_FOLLOWUP" ] && echo "# follow-up at crashing pads: $ACG_FOLLOWUP (up to ${ACG_FOLLOWUP_MAX:-4} pads)" >> "$OUT"
# The runtime libraries acg-hip resolves (OpenMP, MPI, libfabric, CCE runtime, RCCL)
if ! sd_dry; then
    ldd "$ACG" 2>&1 | grep -Ei 'omp|mpi|fabric|cray|cce|rccl|amdhip' | sed 's/^[[:space:]]*/# ldd: /' >> "$OUT" || true
    if [ -n "${ACG_ALT_EXE:-}" ]; then
        echo "# +alt: $ACG_ALT_EXE ($(stat -c '%y' "$ACG_ALT_EXE" 2>&1))" >> "$OUT"
        ldd "$ACG_ALT_EXE" 2>&1 | grep -Ei 'omp|mpi|fabric|cray|cce|rccl|amdhip|stream|not found' \
            | sed 's/^[[:space:]]*/# ldd alt: /' >> "$OUT" || true
    fi
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
    local comm st=0 base="${backend%%+*}" mod exe="$ACG"
    local env=() wrap=() mods=()
    [ "$base" != "$backend" ] && IFS=+ read -ra mods <<< "${backend#*+}"
    for mod in "${mods[@]}"; do
        case "$mod" in
            pad[0-9]*)
                env+=(ACG_PAD="$(printf '%*s' "${mod#pad}" '' | tr ' ' x)") ;;
            asan)
                exe="${SD_PREFIX}/acg/bin/acg-hip-asan"
                if [ ! -x "$exe" ] && ! sd_dry; then sd_warn "no $exe: skipping $backend"; return; fi
                env+=(ASAN_OPTIONS="protect_shadow_gap=0:detect_leaks=0:abort_on_error=1:symbolize=1:print_legend=0"
                      ASAN_SYMBOLIZER_PATH="${ROCM_PATH:-/opt/rocm}/llvm/bin/llvm-symbolizer") ;;
            g)
                exe="${SD_PREFIX}/acg/bin/acg-hip-g"
                if [ ! -x "$exe" ] && ! sd_dry; then sd_warn "no $exe: skipping $backend"; return; fi ;;
            mcheck) env+=(MALLOC_CHECK_=3) ;;
            perturb) env+=(MALLOC_PERTURB_=165) ;;
            alt)
                exe="${ACG_ALT_EXE:-}"
                if [ ! -x "$exe" ] && ! sd_dry; then sd_warn "ACG_ALT_EXE '$exe' isn't executable: skipping $backend"; return; fi ;;
            gdb)
                if [ -z "$GDB" ]; then sd_warn "no gdb or rocgdb: skipping $backend"; return; fi
                wrap=("$GDB" -q -batch -ex "set pagination off" -ex "set startup-with-shell off"
                      -ex "unset environment LINES"
                      -ex "unset environment COLUMNS" -ex run -ex bt -ex quit --args) ;;
            *) sd_warn "unknown modifier '+$mod' in '$backend'"; return ;;
        esac
    done
    case "$base" in
        mpi) comm=mpi ;;
        mpi-no-ipc)
            comm=mpi
            env+=(MPICH_GPU_IPC_ENABLED=0 FI_CXI_RDZV_THRESHOLD=0 FI_CXI_RDZV_EAGER_SIZE=0)
            ;;
        st) comm=st; st=1 ;;
        mpi-eager-off) comm=mpi; env+=(FI_CXI_RDZV_THRESHOLD=0 FI_CXI_RDZV_EAGER_SIZE=0) ;;
        mpi-ipc-off) comm=mpi; env+=(MPICH_GPU_IPC_ENABLED=0) ;;
        mpi-mrcache-off) comm=mpi; env+=(FI_MR_CACHE_MAX_COUNT=0) ;;
        mpi-omp1) comm=mpi; env+=(OMP_NUM_THREADS=1) ;;
        mpi-xnack0) comm=mpi; env+=(HSA_XNACK=0) ;;
        mpi-uffd) comm=mpi; env+=(FI_MR_CACHE_MONITOR=userfaultfd) ;;
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
    RUN_SEQ=$((RUN_SEQ + 1))
    local rc=0 rundir="" watchdog="" before
    before="$(stat -c %s "$OUT" 2>/dev/null || echo 0)"
    if [ -n "$ACG_CORE_DIR" ]; then
        rundir="${ACG_CORE_DIR}/run-$(printf '%04d' "$RUN_SEQ")"   # fixed width: same size of PWD
        sd_dry || mkdir -p "$rundir"
    fi
    if [ "$ACG_HANG_SECONDS" -gt 0 ] && ! sd_dry; then
        local comm_name
        comm_name="$(basename "$exe" | cut -c1-15)"
        ( sleep "$ACG_HANG_SECONDS"
          echo "# hang: still running after $ACG_HANG_SECONDS s: SIGABRT to every $comm_name" >> "$OUT"
          flux exec -r all pkill -ABRT -u "$(id -un)" -x "$comm_name" ) &
        watchdog=$!
    fi
    local cores_off=0
    if [ -n "$rundir" ] && [ "$CORE_RUNS" -ge "${ACG_CORE_BT_TOTAL:-24}" ]; then
        cores_off=1
        echo "# cores: off for this run (${CORE_RUNS} runs have left cores)" >> "$OUT"
    fi
    ( if [ -n "$rundir" ] && ! sd_dry; then cd "$rundir" || exit 1; fi
      [ "$cores_off" = 1 ] && ulimit -c 0
      [ ${#env[@]} -gt 0 ] && export "${env[@]}"
      sd_launch "$NODES" "$ppn" "$OUT" "$st" "${wrap[@]}" "$exe" "$matrix_file" --partition="$partition" \
          --seed 101 --residual-atol 0 --residual-rtol 1e-6 --max-iterations "$ACG_MAX_ITERATIONS" \
          --solver acg --comm "$comm" --manufactured-solution --verbose -q ) || rc=$?
    if [ -n "$watchdog" ]; then
        kill "$watchdog" 2> /dev/null
        wait "$watchdog" 2> /dev/null
    fi
    [ -n "$rundir" ] && ! sd_dry && process_cores "$rundir" "$exe"
    echo "Exit: $rc" >> "$OUT"
    SETUP_OK=1
    if ! sd_dry && ! tail -c +"$((before + 1))" "$OUT" | grep -q 'setting up initial guess'; then
        SETUP_OK=0
    fi
}

# Backtraces from the cores of one run (see ACG_CORE_DIR above).   process_cores <run dir> <exe>
process_cores() {
    local dir="$1" exe="$2" core name txt n=0
    for core in "$dir"/*.core; do
        [ -e "$core" ] || break
        n=$((n + 1))
        name="$(basename "$core" .core)"
        if [ -n "$GDB" ] && [ "$n" -le "${ACG_CORE_BT_MAX:-2}" ] && [ "$CORE_BTS" -lt "${ACG_CORE_BT_TOTAL:-24}" ]; then
            CORE_BTS=$((CORE_BTS + 1))
            txt="${CORE_TXT_DIR}/$(basename "$dir")-${name}.txt"
            timeout 300 "$GDB" -q -batch -nx -x "$CORE_TXT_DIR/main.gdb" -x "$CORE_TXT_DIR/env.gdb" \
                -x "$CORE_TXT_DIR/maps.gdb" "$exe" "$core" > "$txt" 2>&1
            { grep '^rank-env:' "$txt"
              sed -n '/^== crash$/,/^== threads$/p' "$txt" | grep '^#' | head -10
            } | sed "s|^|# core ${name}: |" >> "$OUT"
            if [ "$CORES_KEPT" -lt "${ACG_CORE_KEEP:-4}" ]; then
                CORES_KEPT=$((CORES_KEPT + 1))
                echo "# core ${name}: kept, $(du -h "$core" | cut -f1) at $core" >> "$OUT"
                continue
            fi
        fi
        rm -f "$core"
    done
    if [ "$n" -gt 0 ]; then
        CORE_RUNS=$((CORE_RUNS + 1))
        echo "# cores: $n in $(basename "$dir")" >> "$OUT"
    fi
    rmdir "$dir" 2> /dev/null || true
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
        for (( trial=1; trial<=ACG_TRIALS; trial++ )); do
            CRASHED_PADS=()
            for backend in $ACG_BACKENDS; do
                run_backend "$backend" "$ppn" "$matrix" "$matrix_file" "$partition"
                if [ "$SETUP_OK" = 0 ] && [[ "$backend" =~ \+(pad[0-9]+) ]] \
                   && { [ -z "${ACG_FOLLOWUP_FROM:-}" ] || [ "${backend%+pad*}" = "$ACG_FOLLOWUP_FROM" ]; }; then
                    pad="${BASH_REMATCH[1]}"
                    [[ " ${CRASHED_PADS[*]} " == *" $pad "* ]] || CRASHED_PADS+=("$pad")
                fi
            done
            [ -n "$ACG_FOLLOWUP" ] || continue
            echo "# follow-up: setup failed at ${CRASHED_PADS[*]:-no pad}" >> "$OUT"
            for pad in "${CRASHED_PADS[@]:0:${ACG_FOLLOWUP_MAX:-4}}"; do
                for backend in $ACG_FOLLOWUP; do
                    run_backend "${backend}+${pad}" "$ppn" "$matrix" "$matrix_file" "$partition"
                done
            done
        done
    done
done
