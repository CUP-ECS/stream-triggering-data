#!/bin/bash

usage() {
    echo "Usage: $0 [-T] [-Q queue] [-E power] [-S power] [-I time]"
    echo " -T Run TUO version (default TIOGA version)"
    echo " -Q [queue] The flux queue to run the jobs in (default pdebug)"
    echo " -E [power] The power of 2 number of nodes to stop at (inclusive, default 2 (4 nodes))"
    echo " -S [power] The power of 2 number of nodes to start at (inclusive, default 0 (1 node))"
    echo " -I [time] The time for the TOTAL job length, in flux notation (Default \"10m\")"
    echo " -R [number] How many times to repeat the sweep (in x,y,z,x,y,z order, not x,x,y,y,z,z) (default 1)"
}

while getopts ":TQ:E:S:I:R:" opt; do
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
        R)
            REPEATS="$OPTARG"
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
    SYSTEM=TIOGA
    SCRIPT=flux-tioga-run-multi.sh
else
    echo "Running TUO Script"
    SYSTEM=TUOLUMNE
    SCRIPT=flux-tuo-run-multi.sh
fi
cd $SYSTEM

# Determine Queue
if [ -z $QUEUE ]; then
    QUEUE=pdebug
fi

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
    TIME=10m
fi

echo "Job node range (powers of 2): $START_EXP:$END_EXP ( for $TIME, on $QUEUE, repeated $REPEATS time(s))"

prev_job_id=""

for (( i=0; i<$REPEATS; i++ )); do
    for (( exp=START_EXP; exp<=END_EXP; exp++ )); do
        NODES=$((2 ** $exp))
        SLOTS=$((4 * $NODES))
        if [ -z "$prev_job_id" ]; then
            set -x
            prev_job_id=$(flux batch --time-limit=$TIME --queue=$QUEUE \
                                     --output=$SYSTEM-$NODES-$i.out    \
                                     --nodes=$NODES --nslots=$SLOTS    \
                                     ./$SCRIPT)
            set +x
        else
            set -x
            prev_job_id=$(flux batch --time-limit=$TIME --queue=$QUEUE  \
                                     --output=$SYSTEM-$NODES-$i.out     \
                                     --dependency=afterany:$prev_job_id \
                                     --nodes=$NODES --nslots=$SLOTS     \
                                     ./$SCRIPT)
            set +x
        fi
    done
done