#!/bin/bash

NODES=$SLURM_NNODES

SYSTEM=FRONTIER
export HSA_XNACK=1
module load cce/20.0.0 rocm/6.4.2 craype-accel-amd-gfx90a

# Add hostnames to file
srun --nodes=$NODES --ntasks-per-node=1 --output=$CBG_OUT hostname
# Save modules
module list >> $CBG_OUT 2>&1

TEST="/ccs/home/$USER/apps/CabanaGhost/bin/gol"

START_EXP=0
END_EXP=3
ITERS=1000
PRINT_FREQ=200

run_test()
{
    echo "Test: ${2} $NODES $PPN $SIZE" >> $CBG_OUT
    if [[ "$1" == "mpich" ]]; then
        BACKEND="mpi"
        NETWORK_OPS=""
    else
        BACKEND="mpi-advance"
        TLES=$((1024 / PPN))
        NETWORK_OPS="--network=single_node_vni,job_vni,def_tles=$TLES"
    fi

    srun $NETWORK_OPS -N"$NODES" --ntasks-per-node="$PPN" --output="$CBG_OUT" \
         "$TEST" -n "$SIZE" -c "$BACKEND" -t "$ITERS" -p "$PRINT_FREQ"
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
    done
done
