#!/bin/bash
# Build the software for every experiment in this repository, on one system, into one prefix.
#
#   build-scripts/build.sh -s tuolumne [-p prefix] [-g git-dir] [-M mode] [-j N] [component...]
#
# Components, always built in this order (default: all except ofi-nccl):
#   silo kokkos st cabana cabanaghost   CabanaGhost and its dependencies
#   ofi-nccl                            aws-ofi-nccl, for aCG's rccl backend (optional, opt-in)
#   acg                                 aCG's acg-hip and mtxpartition (needs METIS, see below)
#   pingpong                            stream-triggering's packing ping-pong benchmarks
#
# Where things go (<prefix> defaults to <SD_PREFIX_ROOT>/<SD_STACK_TAG> from systems/<system>.sh):
#   <prefix>/src/<name>        pinned third-party clones (Silo, Kokkos, aws-ofi-nccl)
#   <prefix>/build/<comp>      build trees, started fresh every time, with <comp>.log beside them
#   <prefix>/<comp>            installs: silo kokkos stream-triggering cabana cabanaghost ofi-nccl
#                              acg/bin pingpong
#   <prefix>/manifest.txt      what every installed component was built from (git commits,
#                              modules, compilers, options). Run scripts record its path.
#
# Our own repositories (stream-triggering, Cabana, CabanaGhost, aCG) are built in place from
# <git-dir>/<name> (default $HOME/git; the meta repo passes its repos/). A missing one is cloned at
# the ref in systems/versions.sh; an existing one is used as it is, never checked out or reset.
#
# METIS: aCG needs METIS_DIR (default <prefix>/metis). On Tuolumne install it there with Spack
# (steps in systems/metis-spack.yaml); on Frontier it's the metis module in systems/frontier.modules,
# and systems/frontier.sh sets METIS_DIR from it.
#
# Other knobs: MOD_FILE (module list), SD_DRY_RUN=1 (print the commands), KOKKOS_VIEW_LEGACY
# (default ON; Cabana's CHANGELOG asks for it with Kokkos newer than 4.6), SD_HIP_COMPILER (the
# CMake HIP compiler for ST and aCG, default SD_CXX; see HIP_COMPILER below).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "${SCRIPT_DIR}/../systems/common.sh"

ALL_COMPONENTS=(silo kokkos st cabana cabanaghost ofi-nccl acg pingpong)
DEFAULT_COMPONENTS=(silo kokkos st cabana cabanaghost acg pingpong)

usage() {
    sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

SYSTEM=""
PREFIX=""
GIT_DIR="${HOME}/git"
MODE=Release
JOBS=8
while getopts ":s:p:g:M:j:h" opt; do
    case $opt in
        s) SYSTEM="$OPTARG" ;;
        p) PREFIX="$OPTARG" ;;
        g) GIT_DIR="$OPTARG" ;;
        M) MODE="$OPTARG" ;;
        j) JOBS="$OPTARG" ;;
        h) usage 0 ;;
        *) usage 1 ;;
    esac
done
shift $((OPTIND - 1))
[ -n "$SYSTEM" ] || usage 1

# Which components, in build order
REQUESTED=("$@")
[ ${#REQUESTED[@]} -eq 0 ] && REQUESTED=("${DEFAULT_COMPONENTS[@]}")
[ "${REQUESTED[*]}" = "all" ] && REQUESTED=("${DEFAULT_COMPONENTS[@]}")
for c in "${REQUESTED[@]}"; do
    [[ " ${ALL_COMPONENTS[*]} " == *" $c "* ]] || sd_die "unknown component '$c' (known: ${ALL_COMPONENTS[*]})"
done
COMPONENTS=()
for c in "${ALL_COMPONENTS[@]}"; do
    [[ " ${REQUESTED[*]} " == *" $c "* ]] && COMPONENTS+=("$c")
done

sd_load_system "$SYSTEM"
PREFIX="${PREFIX:-$(sd_default_prefix)}"
GIT_DIR="$(realpath -m "$GIT_DIR")"
mkdir -p "$PREFIX"/{src,build,manifests}
PREFIX="$(realpath "$PREFIX")"

sd_log "system ${SD_SYSTEM}, stack ${SD_STACK_TAG}, $MODE build"
sd_log "prefix $PREFIX"
sd_log "sources $GIT_DIR"
sd_log "components ${COMPONENTS[*]}"

# Directory of one of our repositories, cloned if it's missing. Usage: repo_dir "$ST_REPO"
repo_dir() {
    local name url ref
    read -r name url ref <<< "$1"
    sd_clone "${GIT_DIR}/${name}" "$url" "$ref"
    echo "${GIT_DIR}/${name}"
}

compiler_line() {
    local v
    v="$("$1" --version 2> /dev/null | head -1 || true)"
    echo "$1 -> $(command -v "$1" || echo 'NOT ON PATH') (${v:-version unknown})"
}

# Record what a component was built from: manifests/<comp>.txt
#   write_manifest <comp> <source name> <source dir> <options...>
write_manifest() {
    local comp="$1" src_name="$2" src_dir="$3"
    shift 3
    {
        echo "== $comp"
        echo "built: $(date -Is) on $(hostname)$(sd_dry && echo ' (DRY RUN: nothing was built)')"
        echo "source: $(sd_repo_line "$src_name" "$src_dir")"
        echo "scripts: $(sd_repo_line stream-triggering-data "$SD_ROOT")"
        echo "modules: $SD_MODULES"
        echo "module file: $SD_MODULE_FILE"
        echo "cc: $(compiler_line "$SD_CC")"
        echo "cxx: $(compiler_line "$SD_CXX")"
        echo "build type: $MODE"
        echo "options: $*"
    } > "${PREFIX}/manifests/${comp}.txt"
}

# Fresh build tree for a component; prints its path. Its log is <prefix>/build/<comp>.log
fresh_build() {
    local dir="${PREFIX}/build/$1"
    rm -rf "$dir" "${dir}.log"
    mkdir -p "$dir"
    echo "$dir"
}

# configure + build + install with CMake, logging to <prefix>/build/<comp>.log
cmake_component() {
    local comp="$1" src="$2"
    shift 2
    local bld log
    bld="$(fresh_build "$comp")"
    log="${bld}.log"
    sd_log "building $comp ($src)"
    sd_step "$log" cmake -S "$src" -B "$bld" -DCMAKE_BUILD_TYPE="$MODE" "$@"
    sd_step "$log" cmake --build "$bld" -j "$JOBS"
    sd_step "$log" cmake --install "$bld"
}

ST_PREFIX="${PREFIX}/stream-triggering"

# The HIP-language compiler for the projects that enable HIP in CMake (ST and aCG); the others
# compile HIP code as CXX. Left alone, CMake picks ROCm's bare clang++ for HIP. With an MPI
# wrapper as SD_CXX (Tuolumne's mpiamdclang++), FindMPI then gives MPI::MPI_CXX no include
# directory (the wrapper's -I counts as the compiler's implicit include, so FindMPI drops it),
# and every .hip file that includes mpi.h fails (Tuolumne, 2026-11-09). Compiling HIP through
# the same wrapper fixes that, as ST's tests/compile.py does (mpiamdclang++ -x hip).
HIP_COMPILER="${SD_HIP_COMPILER:-$SD_CXX}"

build_silo() {
    local src="${PREFIX}/src/Silo"
    sd_clone "$src" "$SILO_URL" "$SILO_REF" "$SILO_SHA"
    local opts=(-DCMAKE_INSTALL_PREFIX="${PREFIX}/silo" -DCMAKE_C_COMPILER="$SD_CC"
                -DCMAKE_CXX_COMPILER="$SD_CXX" -DSILO_ENABLE_HDF5=OFF -DSILO_ENABLE_FORTRAN=OFF)
    cmake_component silo "$src" "${opts[@]}"
    write_manifest silo Silo "$src" "${opts[@]}"
}

build_kokkos() {
    local src="${PREFIX}/src/kokkos"
    sd_clone "$src" "$KOKKOS_URL" "$KOKKOS_REF" "$KOKKOS_SHA"
    local opts=(-DCMAKE_INSTALL_PREFIX="${PREFIX}/kokkos" -DCMAKE_CXX_COMPILER="$SD_CXX"
                -DKokkos_ENABLE_HIP=ON -DKokkos_ARCH_"${SD_KOKKOS_ARCH}"=ON
                -DKokkos_ENABLE_IMPL_VIEW_LEGACY="${KOKKOS_VIEW_LEGACY:-ON}" -DBUILD_SHARED_LIBS=ON)
    cmake_component kokkos "$src" "${opts[@]}"
    write_manifest kokkos kokkos "$src" "${opts[@]}"
}

build_st() {
    local src
    src="$(repo_dir "$ST_REPO")"
    local opts=(-DCMAKE_INSTALL_PREFIX="$ST_PREFIX" -DCMAKE_C_COMPILER="$SD_CC"
                -DCMAKE_CXX_COMPILER="$SD_CXX" -DCMAKE_HIP_COMPILER="$HIP_COMPILER"
                -DUSE_HIP_BACKEND=ON -DUSE_CXI_BACKEND=ON
                -DLIBFABRIC_PREFIX="$SD_LIBFABRIC_DIR" -DCMAKE_HIP_ARCHITECTURES="$SD_GPU_ARCH"
                -DBUILD_TESTS=ON)
    [ -n "${SD_SHARED_LINK_FLAGS// /}" ] && opts+=(-DCMAKE_SHARED_LINKER_FLAGS="$SD_SHARED_LINK_FLAGS")
    cmake_component stream-triggering "$src" "${opts[@]}"
    # Let ST's own test runners (tests/run_<system>.sh) find this build's modules, as install.sh does
    echo "$SD_MODULE_FILE" > "${PREFIX}/build/stream-triggering/st_modules.path"
    write_manifest st stream-triggering "$src" "${opts[@]}"
}

build_cabana() {
    local src
    src="$(repo_dir "$CABANA_REPO")"
    local opts=(-DCMAKE_INSTALL_PREFIX="${PREFIX}/cabana" -DCMAKE_CXX_COMPILER="$SD_CXX"
                -DCMAKE_PREFIX_PATH="${PREFIX}/kokkos;${ST_PREFIX}"
                -DCabana_ENABLE_MPI=ON -DCabana_BUILD_STREAM_HALO=ON
                -DCabana_REQUIRE_STREAM-TRIGGERING=ON)
    cmake_component cabana "$src" "${opts[@]}"
    write_manifest cabana Cabana "$src" "${opts[@]}"
}

build_cabanaghost() {
    local src
    src="$(repo_dir "$CABANAGHOST_REPO")"
    local opts=(-DCMAKE_INSTALL_PREFIX="${PREFIX}/cabanaghost" -DCMAKE_C_COMPILER="$SD_CC"
                -DCMAKE_CXX_COMPILER="$SD_CXX" -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=TRUE
                -DCMAKE_PREFIX_PATH="${PREFIX}/kokkos;${ST_PREFIX};${PREFIX}/silo;${PREFIX}/cabana")
    [ -n "${SD_EXE_LINK_FLAGS// /}" ] && opts+=(-DCMAKE_EXE_LINKER_FLAGS="$SD_EXE_LINK_FLAGS")
    cmake_component cabanaghost "$src" "${opts[@]}"
    if ! sd_dry; then
        local gol="${PREFIX}/cabanaghost/bin/gol"
        [ -x "$gol" ] || sd_die "no $gol after the install"
        ldd "$gol" | grep -q libstream-triggering \
            || sd_warn "$gol doesn't link stream-triggering: its mpi-advance backend is missing"
    fi
    write_manifest cabanaghost CabanaGhost "$src" "${opts[@]}"
}

build_ofi_nccl() {
    local src="${PREFIX}/src/aws-ofi-nccl"
    sd_clone "$src" "$OFI_NCCL_URL" "$OFI_NCCL_REF" "$OFI_NCCL_SHA"
    local bld log
    bld="$(fresh_build ofi-nccl)"
    log="${bld}.log"
    [ -n "${ROCM_PATH:-}" ] || sd_dry || sd_die "ROCM_PATH isn't set: the rocm module didn't load"
    [ -n "${MPICH_DIR:-}" ] || sd_dry || sd_die "MPICH_DIR isn't set: cray-mpich didn't load"
    # configure wants libfabric's prefix, not its lib directory
    local fabric="${SD_LIBFABRIC_DIR%/lib64}"
    local opts=(--prefix="${PREFIX}/ofi-nccl" --with-rocm="${ROCM_PATH:-}"
                --with-mpi="${MPICH_DIR:-}" --with-libfabric="$fabric")
    sd_log "building ofi-nccl ($src)"
    (cd "$src" && sd_step "$log" ./autogen.sh)
    (cd "$bld" && sd_step "$log" env CC="$SD_CC" CXX="$SD_CXX" "$src/configure" "${opts[@]}" \
        && sd_step "$log" make -j "$JOBS" && sd_step "$log" make install)
    write_manifest ofi-nccl aws-ofi-nccl "$src" "${opts[@]}"
}

build_acg() {
    local src
    src="$(repo_dir "$ACG_REPO")"
    local metis="${METIS_DIR:-${PREFIX}/metis}"
    [ -d "$metis" ] || sd_dry || sd_die "no METIS at $metis: install it (systems/metis-spack.yaml; on Frontier, the metis module) or set METIS_DIR"
    local common=(-DCMAKE_C_COMPILER="$SD_CC" -DCMAKE_CXX_COMPILER="$SD_CXX" -DMETIS_DIR="$metis")
    [ -n "${SD_EXE_LINK_FLAGS// /}" ] && common+=(-DCMAKE_EXE_LINKER_FLAGS="$SD_EXE_LINK_FLAGS")
    local opts=("${common[@]}" -DCMAKE_HIP_COMPILER="$HIP_COMPILER" -DCMAKE_HIP_ARCHITECTURES="$SD_GPU_ARCH"
                -DCMAKE_PREFIX_PATH="${ST_PREFIX};${ROCM_PATH:-/opt/rocm}"
                -DACG_REQUIRE_STREAM_TRIGGERING=ON)
    local bld log
    # aCG has no install rules: build each tool, then copy the binary.
    for tool in hip mtxpartition; do
        bld="$(fresh_build "acg-$tool")"
        log="${bld}.log"
        sd_log "building aCG's $tool ($src/$tool)"
        if [ "$tool" = hip ]; then
            sd_step "$log" cmake -S "$src/hip" -B "$bld" -DCMAKE_BUILD_TYPE="$MODE" "${opts[@]}"
        else
            sd_step "$log" cmake -S "$src/mtxpartition" -B "$bld" -DCMAKE_BUILD_TYPE="$MODE" "${common[@]}"
        fi
        sd_step "$log" cmake --build "$bld" -j "$JOBS"
    done
    sd_run mkdir -p "${PREFIX}/acg/bin"
    sd_run cp "${PREFIX}/build/acg-hip/acg-hip" "${PREFIX}/build/acg-mtxpartition/mtxpartition" "${PREFIX}/acg/bin/"
    if ! sd_dry && grep -q '^RCCL_DIR:PATH=.*NOTFOUND' "${PREFIX}/build/acg-hip/CMakeCache.txt"; then
        sd_warn "aCG didn't find RCCL: its rccl backend is disabled"
    fi
    write_manifest acg aCG "$src" "${opts[@]}" "(mtxpartition: ${common[*]})"
}

# ST's tests/compile.py, run once per benchmark from a scratch directory (it writes
# scratch/execs/ under the current directory). A benchmark that fails to compile is reported and
# skipped, so one broken benchmark doesn't stop the rest; its error is in the log.
build_pingpong() {
    local src
    src="$(repo_dir "$ST_REPO")"
    local bld log cluster
    bld="$(fresh_build pingpong)"
    log="${bld}.log"
    cluster="${LCSCHEDCLUSTER:-${LMOD_SYSTEM_NAME:-$SD_SYSTEM}}"
    local st_flags=(-C -H -T -S "$ST_PREFIX")
    local failed=()
    sd_log "building the ping-pong benchmarks ($src/tests/benchmark)"
    for b in st st_db st_raw mpi mpi_db mpi_raw ipc; do
        local flags=()
        [[ "$b" == st* ]] && flags=("${st_flags[@]}")
        if ! (cd "$bld" && LCSCHEDCLUSTER="$cluster" sd_step "$log" python3 "$src/tests/compile.py" \
                -f "$src/tests/benchmark/pingpong_${b}.cpp" "${flags[@]}" -m "$SD_MODULE_FILE"); then
            failed+=("$b")
        fi
    done
    # pingpong_<name>_<cluster>[_<variant>] -> <prefix>/pingpong/pingpong_<name>[_<variant>]
    sd_run mkdir -p "${PREFIX}/pingpong"
    if ! sd_dry; then
        local f
        for f in "$bld"/scratch/execs/pingpong_*; do
            [ -e "$f" ] || continue
            local base
            base="$(basename "$f")"
            cp "$f" "${PREFIX}/pingpong/${base/_${cluster}/}"
        done
    fi
    write_manifest pingpong stream-triggering "$src" "compile.py ${st_flags[*]} (st*), -m $SD_MODULE_FILE" \
        "${failed[@]:+FAILED: ${failed[*]}}"
    [ ${#failed[@]} -eq 0 ] || sd_warn "ping-pong benchmarks that didn't compile: ${failed[*]} (see $log)"
}

for c in "${COMPONENTS[@]}"; do
    "build_${c//-/_}"
done

sd_assemble_manifest "$PREFIX"
sd_log "done: ${PREFIX}/manifest.txt"
