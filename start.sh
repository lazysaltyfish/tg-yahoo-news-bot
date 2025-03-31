#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR" || exit 1 # Change to the script's directory

CONFIG_FILE="config.yaml"
EXAMPLE_CONFIG_FILE="config.yaml.example"

# Check if .env file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "'$CONFIG_FILE' file not found."
    if [ -f "$EXAMPLE_CONFIG_FILE" ]; then
        echo "Copying '$EXAMPLE_CONFIG_FILE' to '$CONFIG_FILE'..."
        if cp "$EXAMPLE_CONFIG_FILE" "$CONFIG_FILE"; then
            echo ""
            echo "IMPORTANT: Please edit the '$CONFIG_FILE' file with your actual API keys, tokens, and URLs."
            echo "Then, run this script again."
        else
            echo "ERROR: Failed to copy '$EXAMPLE_CONFIG_FILE'." >&2
            exit 1
        fi
    else
        echo "ERROR: '$EXAMPLE_CONFIG_FILE' not found either. Cannot create '$CONFIG_FILE'. Please create it manually." >&2
    fi
    exit 1
fi

# Environment variables are no longer loaded from a file by this script.
# The Python application now reads configuration from config.yaml.

echo ""
echo "Starting the bot (app/main.py)..."
echo "------------------------------------"

# Execute the main Python script
# Ensure python3 (or python) is in the PATH
if command -v python3 &> /dev/null; then
    python3 -m app.main
elif command -v python &> /dev/null; then
    python -m app.main
else
    echo "ERROR: Neither 'python3' nor 'python' command found in PATH." >&2
    exit 1
fi

EXIT_CODE=$? # Capture the exit code of the python script

echo "------------------------------------"
if [ $EXIT_CODE -eq 0 ]; then
    echo "Script finished successfully."
else
    echo "Script finished with errors (Exit Code: $EXIT_CODE)."
fi

exit $EXIT_CODE