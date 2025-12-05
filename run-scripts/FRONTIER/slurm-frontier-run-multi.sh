#!/bin/bash

NODES=$SLURM_NNODES

SYSTEM=FRONTIER
export HSA_XNACK=1
module load craype-accel-amd-gfx90a
module load rocm

COLLECTION_DIR=outputs
FILENAME_BASE="./$COLLECTION_DIR/$SYSTEM-$NODES-$(date +%m-%d)"
COUNT=1
TARGET="${FILENAME_BASE}-${COUNT}.out"

while [[ -e $TARGET ]]; do
    ((COUNT++))
    TARGET="${FILENAME_BASE}-${COUNT}.out"
done

pwd
touch "$TARGET"
echo $TARGET

HOSTNAMES_FILE="$COLLECTION_DIR/0-hostnames.tmp"
VAR_MOD_FILE="$COLLECTION_DIR/0-var-mod.tmp"
module list >> $VAR_MOD_FILE 2>&1
srun --nodes=$NODES --ntasks-per-node=1 --output=$HOSTNAMES_FILE hostname

TEST="/ccs/home/$USER/apps/CabanaGhost/bin/gol"

START_EXP=0
END_EXP=3
ITERS=1000

run_test()
{
    RUN_FILE="$COLLECTION_DIR/$1.tmp"
    STRING="Test: ${2} $NODES $PPN $SIZE"
    if [[ "$1" == "mpich" ]]; then
        srun -N$NODES --ntasks-per-node=$PPN --output="$RUN_FILE" $TEST -n $SIZE -c mpi -t $ITERS
    else
        TLES=$((1024 / $PPN))
        srun --network=single_node_vni,job_vni,def_tles=$TLES -N$NODES --ntasks-per-node=$PPN --output="$RUN_FILE" $TEST -n $SIZE -c mpi-advance -t $ITERS
    fi
    sed -i "1i$STRING" $RUN_FILE
}

matrix_sizes=(16384 61440)

for (( exp=START_EXP; exp<=END_EXP; exp++ )); do
    PPN=$((2 ** $exp))
    for j in "${matrix_sizes[@]}"; do
        SIZE=$j

        run_test "a-db" "MPI Advance Double Buffer"

        export MPI_ADVANCE_DOUBLE_BUFFERING=0
        run_test "a-sb" "MPI Advance Single Buffer"
        unset MPI_ADVANCE_DOUBLE_BUFFERING

        export MPI_ADVANCE_FINEGRAIN_MEMORY=1
        run_test "a-fg-db" "MPI Advance Double Fine-grained Buffer"
        export MPI_ADVANCE_DOUBLE_BUFFERING=0
        run_test "a-fg-sb" "MPI Advance Single Fine-grained Buffer"
        unset MPI_ADVANCE_DOUBLE_BUFFERING
        unset MPI_ADVANCE_FINEGRAIN_MEMORY

        export MPICH_GPU_SUPPORT_ENABLED=1
        # export MPICH_GPU_IPC_ENABLED=0
        run_test "mpich" "MPI Single Buffer"            
        unset MPICH_GPU_SUPPORT_ENABLED
        # unset MPICH_GPU_IPC_ENABLED

        cat $COLLECTION_DIR/*.tmp >> $TARGET
        rm -f $COLLECTION_DIR/*.tmp
    done
done
