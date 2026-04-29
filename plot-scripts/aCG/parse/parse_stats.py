import argparse
import csv
import os
import re
from collections import defaultdict

def main():
    parser = argparse.ArgumentParser(description="Parse MPI stats from grep output.")
    parser.add_argument('--input', required=True, help='Input grep output file')
    parser.add_argument('--output', required=True, help='Output CSV file')
    args = parser.parse_args()

    # Dictionary to aggregate sends/receives for each unique rank setup
    data = defaultdict(lambda: {
        'msg_sent_it': 0, 'msg_recv_it': 0,
        'bytes_sent_it': 0, 'bytes_recv_it': 0,
        'total_bytes_sent': 0, 'total_bytes_recv': 0
    })

    # Captures: 1=dir, 2=file, 3=rank, 4=action, 5=total_bytes, 6=bytes/it, 7=msg/it
    line_pattern = re.compile(
        r'^(.+)/([^:]+):\s*rank\s+(\d+)\s+(sends|receives)\s+(\d+)\s+B\s+(\d+)\s+B/it.*?\s+(\d+)\s+msg/it'
    )

    with open(args.input, 'r') as f:
        for line in f:
            match = line_pattern.search(line)
            if not match: continue
            
            full_path, file_name, rank, action, total_bytes, bytes_per_it, msg_per_it = match.groups()
            # Get just the immediate parent folder name (e.g., SYSTEM-NODES-MONTH-DAY-RUN)
            dir_name = os.path.basename(os.path.normpath(full_path))
            system = dir_name.split('-')[0].capitalize()
            
            # Safely extract matrix, nodes, and ppn
            base = file_name.replace('.out', '')
            try:
                matrix, nodes, ppn = base.rsplit('_', 2)
            except ValueError:
                continue # Skip malformed files

            key = (system, nodes, ppn, matrix, rank)

            if action == 'sends':
                data[key]['msg_sent_it'] = msg_per_it
                data[key]['bytes_sent_it'] = bytes_per_it
                data[key]['total_bytes_sent'] = total_bytes
            else:
                data[key]['msg_recv_it'] = msg_per_it
                data[key]['bytes_recv_it'] = bytes_per_it
                data[key]['total_bytes_recv'] = total_bytes

    with open(args.output, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'system', 'nodes', 'ppn', 'matrix', 'rank', 
            'messages sent per iteration', 'messages received per iteration', 
            'bytes sent per iteration', 'bytes received per iteration', 
            'total bytes sent', 'total bytes received'
        ])
        
        for key, vals in data.items():
            system, nodes, ppn, matrix, rank = key
            writer.writerow([
                system, nodes, ppn, matrix, rank,
                vals['msg_sent_it'], vals['msg_recv_it'],
                vals['bytes_sent_it'], vals['bytes_recv_it'],
                vals['total_bytes_sent'], vals['total_bytes_recv']
            ])

if __name__ == '__main__':
    main()