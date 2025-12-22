import os
import csv
import re
import argparse

def semicolon_parser(arr):
    if arr[-1] == ';':
        arr = [x for x in arr[:-1].split(';')]
    else:
        arr = [x for x in arr.split(';')]
    return arr

def int_parser(arr):
    return [int(x) for x in semicolon_parser(arr)]

def main():
    parser = argparse.ArgumentParser(description="Create scripts with internal specs")

    # make name node-stream.sh
    parser.add_argument("--nodes", type=str, default="1;2;4;8;16;32")
    parser.add_argument("--gol_file", type=str, default="./gol")
    parser.add_argument("--system", type=str, default="tioga")
    parser.add_argument("--backends", type=str, default="CXI")
    parser.add_argument("--finegrain", type=str, default="coarse;finegrain")
    parser.add_argument("--cycles", type=str, default="1000")

    args = parser.parse_args()
    nodes = args.nodes
    nodes = int_parser(nodes)
    gol_file = args.gol_file
    system = args.system
    backends = args.backends.split(";")
    finegrain = args.finegrain.split(";")
    print("finegrain array: ", finegrain)
    partition = "pdebug"
    cycles = args.cycles
    necessary_exports = []
    
    if system == "tioga":
        modules = "module load craype-accel-amd-gfx90a rocm\n"
        base_nums = [16384, 61440]
        ntasks = "for (( j=1; j<=8; j=j*2 )); do\n" #[1, 2, 4, 8]
        parition = "pdebug"
        nodes = [1, 2, 4, 8, 16]
    else:
        modules = "module load craype-accel-amd-gfx942 rocm\n"
        base_nums = [16384, 90112]
        ntasks = "for (( j=1; j<=4; j=j*2 )); do\n"#[1, 2, 4]
        necessary_exports = ["export HSA_XNACK=1\n"]
        partition = "pbatch"

    for i in nodes:
        outfile = str(i)+"-"+system+"-stream.sh"
        print(outfile)
        with open(outfile, 'w') as scriptfile:
            scriptfile.write(f"#!/bin/bash\n#SBATCH --nodes={i}\n#SBATCH --ntasks-per-node=8\n#SBATCH --time=01:30:00\n#SBATCH --partition={partition}\n#SBATCH --exclusive\n\n")
            for exp in necessary_exports:
                scriptfile.write(exp)
            scriptfile.write(modules)
            scriptfile.write(f"export MPI_ADVANCE_STREAM_BACKEND={backends[0]}\n")
            for mem_type in finegrain:
                if mem_type == "finegrain":
                    mem_index = 1
                else:
                    mem_index = 0
                for base in base_nums:
                    scriptfile.write(f'base={base}\n\n')
                    scriptfile.write("# Solver backend list: \n\n")
                    scriptfile.write(f'echo "Solver system: {system}"\n')
                    scriptfile.write(f'echo "Solver cycles: {cycles}"\n')
                    scriptfile.write(f'echo "Solver memory_type: {mem_type}"\n')
                    scriptfile.write(f'export MPI_ADVANCE_FINEGRAIN_MEMORY={mem_index}\n')
                    #scriptfile.write(f'export i = {nodes}\n')
                    #scriptfile.write(f'for (( j=1; j<={
                    #scriptfile.write(f'export i={i}\n')
                    scriptfile.write(ntasks)
                    scriptfile.write(f'\t\techo "Solver specs: n:{i} gpus:$j"\n')
                    #scriptfile.write("""\tfor k in {1..5}; do\n""")

                    # mpi advance
                    scriptfile.write("""\t\techo "Solver backend: MPIAdvance CXI Double Buffering"\n""")
                    scriptfile.write(f"""\t\techo "Solver size: $base"\n""")
                    scriptfile.write(f'\t\tsrun --nodes={i} --ntasks-per-node=$j {gol_file} -n {base} -c mpi-advance -t {cycles}\n')
                    scriptfile.write(f"""\t\techo "Solver send_type: Ready Send"\n\n""")
                    
                    # MPI Advance single buffering
                    scriptfile.write(f"""\t\texport MPI_ADVANCE_DOUBLE_BUFFERING=0\n\t\techo "Solver backend: MPIAdvance CXI Single Buffering"\n\t\techo "Solver size: $base"\n""")
                    scriptfile.write(f"""\t\tsrun --nodes={i} --ntasks-per-node=$j {gol_file} -n {base} -c mpi-advance -t {cycles}\n""")
                    scriptfile.write(f"""\t\techo "Solver send_type: Standard"\n\t\tunset MPI_ADVANCE_DOUBLE_BUFFERING\n\n""")

                    # MPICH with GPU
                    scriptfile.write(f"""\t\texport MPICH_GPU_SUPPORT_ENABLED=1\n\t\texport MPICH_GPU_IPC_ENABLED=1\n\t\techo "Solver backend: Cray MPICH CXI GPU Enabled"\n\t\techo "Solver size: $base"\n""")
                    scriptfile.write(f"""\t\tsrun --nodes={i} --ntasks-per-node=$j {gol_file} -n {base} -c mpi -t {cycles}\n""")
                    scriptfile.write(f"""\t\techo "Solver send_type: Standard"\n\t\tunset MPICH_GPU_SUPPORT_ENABLED \n\t\tunset MPICH_GPU_IPC_ENABLED\n\n""")

                    # end loops
                    #scriptfile.write("\tdone\n")
                    scriptfile.write("done\n\n")
                

if __name__ == "__main__":
        main() # Call the main function when the script is run directly
