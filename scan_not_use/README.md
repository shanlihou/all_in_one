# Find Unused Python Functions

A Python script to identify and report Python functions that are defined in a specific file but are not used anywhere within a larger workspace. It is a useful tool for code cleanup and refactoring.

## Features

- **Accurate Function Parsing:** Uses Python's `ast` (Abstract Syntax Tree) module to safely parse function definitions and their line ranges.
- **High-Speed Searching:** Leverages `ripgrep` (`rg`) for fast, workspace-wide code searching.
- **Intelligent Self-Reference Filtering:** Correctly identifies and ignores references within a function's own body (like recursive calls), preventing false positives.
- **Simple Configuration:** All paths are managed in a central `const.py` file.
- **Progress Indicator:** Displays real-time progress while scanning for function references.

## Requirements

- **Python 3.8+**
- **ripgrep (`rg`):** Must be installed and available in your system's PATH. You can download it from the [official ripgrep repository](https://github.com/BurntSushi/ripgrep#installation).

## How to Use

1.  **Configure Paths:**
    Open the `const.py` file and set the `workspace` and `target_file` variables.

    ```python
    # const.py

    # The absolute path to the workspace directory you want to search.
    workspace = '/path/to/your/project/src'

    # The path to the file you want to analyze, relative to the workspace.
    target_file = 'path/to/your/file.to.analyze.py'
    ```

2.  **Run the Script:**
    Execute the script from your terminal:
    ```bash
    python find_unused_functions.py
    ```

The script will output a list of functions from the `target_file` that have no external references within the `workspace`.
