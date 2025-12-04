#!/bin/bash

usage() {
    echo "Usage: $0 [-T] [-Q queue] [-E power] [-S power] [-I time]"
    echo " -E [power] The power of 2 number of nodes to stop at (inclusive, default 2 (4 nodes))"
    echo " -S [power] The power of 2 number of nodes to start at (inclusive, default 0 (1 node))"
    echo " -I [time] The time for the TOTAL job length, in slurm notation (Default \"00:10:00\")"
    echo " -R [number] How many times to repeat the sweep (in x,y,z,x,y,z order, not x,x,y,y,z,z) (default 1)"
}

while getopts ":E:S:I:R:" opt; do
    case $opt in
        E)
            END_EXP="$OPTARG"
            ;;
        S)
            START_EXP="$OPTARG"
            ;;
        I)
            TIME="$OPTARG"
            ;;
        R)
            REPEATS="$OPTARG"
            ;;
        *)
            usage
            exit
            ;;
    esac
done

# Setup for the specific clusters (this script is specific to Frontier)
echo "Running FRONTIER Script"
SCRIPT=slurm-frontier-run-multi.sh
cd FRONTIER

# Determine how many times to repeat
if [ -z $REPEATS ]; then
    REPEATS=1
fi

if [ $REPEATS -lt 1 ]; then
    echo "Invalid number of times to run the tests, stopping."
    exit 1
fi

# Determine Node Limits
if [ -z $START_EXP ]; then
    START_EXP=0
fi

if [ -z $END_EXP ]; then
    END_EXP=2
fi

if [ $END_EXP -lt $START_EXP ]; then
    echo "The number nodes specified would result in no runs, stopping."
    exit 1
fi

# Determine total job time limit
if [ -z $TIME ]; then
    TIME=00:10:00
fi

echo "Job node range (powers of 2): $START_EXP:$END_EXP ( for $TIME, repeated $REPEATS time(s))"

prev_job_id=""

for (( i=0; i<$REPEATS; i++ )); do
    for (( exp=START_EXP; exp<=END_EXP; exp++ )); do
        NODES=$((2 ** $exp))
        if [ -z "$prev_job_id" ]; then
            set -x
            prev_job_id=$(sbatch --parsable --time=$TIME --partition=batch \
                                 --account=csc698  --nodes=$NODES          \
                                 --output=FRONTIER-$NODES-$i.out           \
                                 --exclusive ./$SCRIPT)
            set +x
        else
            set -x
            prev_job_id=$(sbatch --parsable --time=$TIME --partition=batch \
                                 --dependency=afterany:$prev_job_id        \
                                 --account=csc698  --nodes=$NODES          \
                                 --output=FRONTIER-$NODES-$i.out           \
                                 --exclusive ./$SCRIPT)
            set +x
        fi
    done
done
