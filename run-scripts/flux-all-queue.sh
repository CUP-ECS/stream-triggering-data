#!/bin/bash

usage() {
    echo "Usage: $0 [-T] [-Q queue] [-E power] [-S power] [-I time]"
    echo " -T Run TUO version (default TIOGA version)"
    echo " -Q [queue] The flux queue to run the jobs in (default pdebug)"
    echo " -E [power] The power of 2 number of nodes to stop at (inclusive, default 2 (4 nodes))"
    echo " -S [power] The power of 2 number of nodes to start at (inclusive, default 0 (1 node))"
    echo " -I [time] The time for the TOTAL job length, in flux notation (Default \"10m\")"
}

while getopts ":TQ:E:S:I:" opt; do
    case $opt in
        T)
            VERSION=TUO
            ;;
        Q)
            QUEUE="$OPTARG"
            ;;
        E)
            END_EXP="$OPTARG"
            ;;
        S)
            START_EXP="$OPTARG"
            ;;
        I)
            TIME="$OPTARG"
            ;;
        *)
            usage
            exit
            ;;
    esac
done

# Setup for the specific clusters
if [ -z $VERSION ]; then
    echo "Running TIOGA Script"
    SCRIPT=flux-tioga-run-multi.sh
    cd TIOGA
else
    echo "Running TUO Script"
    SCRIPT=flux-tuo-run-multi.sh
    cd TUOLUMNE
fi

# Determine Queue
if [ -z $QUEUE ]; then
    QUEUE=pdebug
fi
echo "Running in Queue: $QUEUE" 

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

echo "Job node range (powers of 2): $START_EXP:$END_EXP"

# Determine total job time limit
if [ -z $TIME ]; then
    TIME=10m
fi
echo "Time Limit: $TIME"

prev_job_id=""

for (( exp=START_EXP; exp<=END_EXP; exp++ )); do
    NODES=$((2 ** $exp))
    SLOTS=$((4 * $NODES))
    if [ -z "$prev_job_id" ]; then
        set -x
        prev_job_id=$(flux batch --time-limit=$TIME --queue=$QUEUE \
                                 --nodes=$NODES --nslots=$SLOTS \
                                 ./$SCRIPT)
        set +x
    else
        set -x
        prev_job_id=$(flux batch --time-limit=$TIME --queue=$QUEUE \
                                 --dependency=afterany:$prev_job_id \
                                 --nodes=$NODES --nslots=$SLOTS \
                                 ./$SCRIPT)
        set +x
    fi
done