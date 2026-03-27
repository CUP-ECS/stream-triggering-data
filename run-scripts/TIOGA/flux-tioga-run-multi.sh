#!/bin/bash
#flux: --gpus-per-slot=1
#flux: --exclusive
#flux: --env=FLUX_TEST={{nnodes}}

#ulimit -c unlimited

NODES=$FLUX_TEST

SYSTEM=TIOGA
export HSA_XNACK=1
module load rocm craype-accel-amd-gfx90a libfabric/2.1

TEST="/usr/workspace/$USER/apps/tioga/CabanaGhost/bin/gol"

START_EXP=0
END_EXP=3
ITERS=1000

run_test()
{
    echo "Test: ${2} $NODES $PPN $SIZE" >> $CBG_OUT
    if [[ "$1" == "mpich" ]]; then
        flux run -x -N$NODES --tasks-per-node=$PPN       \
                 --output=$CBG_OUT -o output.mode=append \
                 $TEST -n $SIZE -c mpi -t $ITERS
    else
        flux run -x -N$NODES --tasks-per-node=$PPN       \
                 --output=$CBG_OUT -o output.mode=append \
                 $TEST -n $SIZE -c mpi-advance -t $ITERS
    fi
}

# Add hostnames to file
srun --nodes=$NODES --ntasks-per-node=1 --output=$CBG_OUT hostname
# Save modules
VAR_MOD_FILE=$CBG_OUT
module list >> $VAR_MOD_FILE 2>&1

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
    done
done
