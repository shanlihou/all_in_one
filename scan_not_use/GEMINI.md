# GEMINI.md - Project Context

## Project Overview

This project consists of a Python script, `find_unused_functions.py`, designed to identify and report Python functions that are defined in a specific file but are not used anywhere within a larger workspace.

The script's logic is robust, accounting for modern development needs:
- **Static Analysis:** It uses Python's `ast` (Abstract Syntax Tree) module to safely and accurately parse a target Python file, extracting a list of all function definitions along with their start and end line numbers.
- **High-Speed Search:** It leverages an external command-line tool, `ripgrep` (`rg`), to perform fast, workspace-wide searches for potential function calls. This is executed via the `subprocess` module.
- **Self-Reference Exclusion:** A key feature is its ability to intelligently filter out self-references. By comparing the line numbers of a search result with the function's own definition range, it avoids incorrectly marking a function as "used" by its own internal recursive calls or references.
- **Configuration:** Project paths are managed in a separate `const.py` file, allowing for easy modification without altering the core logic. The script expects `target_file` to be a path relative to the `workspace`.
- **User-Friendly Output:** The script provides progress updates during the search and presents a clear, final list of all identified unused functions. It also includes a standalone test function for debugging specific cases.

## Building and Running

### Dependencies

- **Python 3.8+:** Required for `end_lineno` support in the `ast` module.
- **ripgrep (`rg`):** This command-line tool is essential for the script's search functionality. It must be installed and available in the system's PATH. It can be installed from [here](https://github.com/BurntSushi/ripgrep#installation).

### Configuration

Before running, you must configure the paths in `const.py`:

```python
# const.py

# The path to the file you want to analyze, relative to the workspace.
target_file = 'path/to/your/file.py' 

# The absolute path to the workspace directory you want to search for references.
workspace = '/path/to/your/project/src'
```

### Running the Script

1.  Ensure the dependencies are installed and `const.py` is configured.
2.  Execute the script from your terminal:

```bash
python find_unused_functions.py
```

The script will then run using the paths defined in `const.py` and print the results to the console.

## Development Conventions

- **Separation of Concerns:** Configuration (`const.py`) is kept separate from application logic (`find_unused_functions.py`).
- **Function-Level Documentation:** All functions include docstrings explaining their purpose, parameters, and return values.
- **Error Handling:** The script includes checks for missing files/directories and handles the case where `ripgrep` is not installed.
- **Debugging:** A `test_single_function` is included in the script. You can uncomment the example call at the end of the file to test its behavior on a single, manually-defined function and its line range.
