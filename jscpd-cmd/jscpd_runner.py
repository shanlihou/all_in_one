import json
import subprocess
import os
import sys

def run_jscpd(config_path='config.json'):
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found.")
        return

    with open(config_path, 'r') as f:
        config = json.load(f)

    file1 = config.get('file1')
    file2 = config.get('file2')
    output_dir = config.get('output_dir', '.jscpd-temp')
    min_lines = config.get('min_lines', 1)
    max_lines = config.get('max_lines', 99999)
    min_tokens = config.get('min_tokens', 30)
    max_size = config.get('max_size', '50mb')

    if not file1 or not file2:
        print("Error: file1 or file2 not specified in config.")
        return

    # Ensure output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Construct the jscpd command
    command = [
        "jscpd",
        "--reporters", "json",
        "--output", output_dir,
        "--min-lines", str(min_lines),
        "--max-lines", str(max_lines),
        "--min-tokens", str(min_tokens),
        "--max-size", max_size,
        file1, file2
    ]

    print(f"Executing: {' '.join(command)}")

    try:
        # Run the command
        result = subprocess.run(command, capture_output=True, text=True)
        
        # jscpd might exit with non-zero if duplicates are found, so we don't necessarily check check=True
        # but we should check if the command itself failed to execute.
        if result.returncode != 0 and not result.stdout and result.stderr:
            print(f"Error executing jscpd: {result.stderr}")
            return

        # Path to the JSON report
        report_path = os.path.join(output_dir, 'jscpd-report.json')
        
        if os.path.exists(report_path):
            with open(report_path, 'r') as rf:
                report_data = json.load(rf)
                
                # Basic summary output
                statistics = report_data.get('statistics', {})
                total = statistics.get('total', {})
                
                print("\n--- Detection Summary ---")
                print(f"Duplicates found: {total.get('percentage')}%")
                print(f"Total lines: {total.get('lines')}")
                print(f"Duplicated lines: {total.get('duplicatedLines')}")
                print(f"Total tokens: {total.get('tokens')}")
                print(f"Duplicated tokens: {total.get('duplicatedTokens')}")
                
                duplicates = report_data.get('duplicates', [])
                if duplicates:
                    print(f"\nFound {len(duplicates)} duplicate blocks.")
                else:
                    print("\nNo duplicates found.")
        else:
            print(f"Report not found at {report_path}. stdout might contain info.")
            print(result.stdout)

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    run_jscpd()
