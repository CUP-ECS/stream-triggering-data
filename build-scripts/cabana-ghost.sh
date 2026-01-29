#!/bin/bash
set -e

RED='\033[1;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
RESET='\033[0m'

# Long term -- use spack instead of this script!
usage() {
    echo "Usage: $0 [-T value] [-SK] [-Q queue] [-E power] [-S power] [-I time]"
    echo " -T Integer that specifies build system: 0 (Tioga), 1 (Tuoloumne), 2 (Frontier) (default TIOGA version)"
    echo " -S Skip Silo build"
    echo " -K Skip Kokkos build"
    echo " -F [path] Where the script should attempt to install all libraries (optional, default depends on system)"
    echo " -B [path] Base directory where all the git repos are cloned to (optional, default = \"$HOME/git\")"
}

clone_repo() {
	local GIT_REPO_NAME=$1
	local GIT_URL=$2
	if [ ! -d $GIT_REPO_NAME ]; then
		git clone $GIT_URL
        if [[ -n "$3" ]]; then
            cd $GIT_REPO_NAME
            git checkout $3
            cd ..
        fi
	else
		echo -e " -> ${BLUE}Skipping git clone of:${RESET} $GIT_REPO_NAME"
        echo -e " -> ${RED} Be sure to manually check branches and versions!${RESET}"
	fi
}

build_build_dir() {
	local DIR_TO_BUILD=build
	if [ -d $DIR_TO_BUILD ]; then
		rm -rf $DIR_TO_BUILD
	fi
	mkdir $DIR_TO_BUILD && cd $DIR_TO_BUILD
}

while getopts ":T:SKF:B:" opt; do
    case $opt in
        T)
            VERSION="$OPTARG"
            ;;
        S)
            SKIP_SILO=1
            ;;
        K)
            SKIP_KOKKOS=1
            ;;
        F)
            BUILD_PATH="$OPTARG"
            ;;
        B)
            GIT_PATH="$OPTARG"
            ;;
        *)
            usage
            exit
            ;;
    esac
done

if [ -z $VERSION ]; then
    VERSION=0
fi

if [ "$VERSION" -eq 0 ]; then
    SYSTEM=tioga
    GPU_ARCH=gfx90a
    KOKKOS_FLAG="-DKokkos_ARCH_AMD_GFX90A=ON"
    LIBFABRIC=/opt/cray/libfabric/2.1/
    if [ -z $BUILD_PATH ]; then
        BUILD_PATH=/usr/workspace/$USER/apps/$SYSTEM
    fi
elif [ "$VERSION" -eq 1 ]; then
    SYSTEM=tuolumne
    GPU_ARCH=gfx942
    KOKKOS_FLAG="-DKokkos_ARCH_AMD_GFX942_APU=ON"
    LIBFABRIC=/opt/cray/libfabric/2.1/
    if [ -z $BUILD_PATH ]; then
        BUILD_PATH=/usr/workspace/$USER/apps/$SYSTEM
    fi
elif [ "$VERSION" -eq 2 ]; then
    SYSTEM=frontier
    GPU_ARCH=gfx90a
    KOKKOS_FLAG="-DKokkos_ARCH_AMD_GFX90A=ON"
    LIBFABRIC=/opt/cray/libfabric/1.22.0/
else
    echo "Invalid system specified, stopping."
    exit 1
fi

echo -e "Running ${CYAN}$SYSTEM${RESET} version:"
module load rocm "craype-accel-amd-${GPU_ARCH}"
module list

# Setup location for where to install everything (technically everything is build in the git folders)
if [ -z $BUILD_PATH ]; then
    BUILD_PATH=$HOME/apps/
fi
echo "Will build to: $BUILD_PATH" 
if [ ! -d $BUILD_PATH ]; then
    echo -e " -> ${BLUE}Build path does not exist, creating${RESET}"
    mkdir $BUILD_PATH
fi

if [ -z $GIT_PATH ]; then
    GIT_PATH=$HOME/git
fi

if [ ! -d $GIT_PATH ]; then
    echo -e "${RED}Unable to locate top level folder for repositories:${RESET} $GIT_PATH"
    exit 1
else
    echo -e "Git repository locations: $GIT_PATH" 
fi

cd $GIT_PATH
echo -e "Collecting repositories" 
# Very simple version -- be sure to check everything when running for first time!
clone_repo "Silo" "https://github.com/LLNL/Silo.git" 
clone_repo "kokkos" "https://github.com/kokkos/kokkos.git" "4.6.02" 
clone_repo "stream-triggering" "https://github.com/mpi-advance/stream-triggering.git" 
clone_repo "Cabana" "https://github.com/CUP-ECS/Cabana.git" "mpi-advance-stream-halo"
clone_repo "CabanaGhost" "https://github.com/CUP-ECS/CabanaGhost.git" "stream-halo"

echo "Building all projects:"
THREADS=8

cd Silo
if [ -z $SKIP_SILO ]; then
echo -e " -> ${CYAN}Building Silo${RESET}"
build_build_dir
cmake \
 -DCMAKE_INSTALL_PREFIX=$BUILD_PATH/silo \
 -DSILO_ENABLE_HDF5=OFF                  \
 -DCMAKE_BUILD_TYPE=Release              \
 -DCMAKE_CXX_COMPILER=CC ..

make -j$THREADS install
else
echo -e " -> ${BLUE}Skipping Silo build${RESET}"
cd build
fi

cd ../../kokkos
if [ -z $SKIP_KOKKOS ]; then
echo -e " -> ${CYAN}Building Kokkos${RESET}"
build_build_dir
cmake \
 -DCMAKE_INSTALL_PREFIX=$BUILD_PATH/kokkos \
 -DCMAKE_BUILD_TYPE=Release \
 -DKokkos_ENABLE_HIP=ON \
 $KOKKOS_FLAG \
 -DCMAKE_CXX_COMPILER=CC \
 -DBUILD_SHARED_LIBS=ON ..

make -j$THREADS install
else
echo -e " -> ${BLUE}Skipping Kokkos build${RESET}"
cd build
fi

cd ../../stream-triggering
echo -e " -> ${CYAN}Building stream-triggering${RESET}"
build_build_dir
cmake \
 -DCMAKE_INSTALL_PREFIX=$BUILD_PATH/stream_trigger \
 -DUSE_HIP_BACKEND=ON \
 -DUSE_CXI_BACKEND=ON \
 -DLIBFABRIC_PREFIX=$LIBFABRIC \
 -DCMAKE_HIP_ARCHITECTURES=$GPU_ARCH \
 -DCMAKE_BUILD_TYPE=Release ..

make -j$THREADS install

cd ../../Cabana
echo -e " -> ${CYAN}Building Cabana${RESET}"
build_build_dir
cmake \
 -DCMAKE_INSTALL_PREFIX=$BUILD_PATH/cabana \
 -DCMAKE_BUILD_TYPE=Release \
 -DCMAKE_PREFIX_PATH="$BUILD_PATH/kokkos;$BUILD_PATH/stream_trigger/" \
 -DCabana_ENABLE_MPI=ON \
 -DCabana_BUILD_STREAM_HALO=ON ..

make -j$THREADS install

cd ../../CabanaGhost
echo -e " -> ${CYAN}Building CabanaGhost${RESET}"
build_build_dir
cmake \
 -DCMAKE_INSTALL_PREFIX=$BUILD_PATH/CabanaGhost \
 -DCMAKE_BUILD_TYPE=Release \
 -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=TRUE \
 -DCMAKE_PREFIX_PATH="$BUILD_PATH/kokkos;$BUILD_PATH/stream_trigger/;$BUILD_PATH/silo;$BUILD_PATH/cabana" ..

make install

echo -e "${BLUE}Done.${RESET}"
