#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR" || exit 1 # Change to the script's directory

ENV_FILE=".env"
EXAMPLE_ENV_FILE=".env.example"

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "'.env' file not found."
    if [ -f "$EXAMPLE_ENV_FILE" ]; then
        echo "Copying '.env.example' to '.env'..."
        if cp "$EXAMPLE_ENV_FILE" "$ENV_FILE"; then
            echo ""
            echo "IMPORTANT: Please edit the '.env' file with your actual API keys, tokens, and URLs."
            echo "Then, run this script again (you might need to run 'chmod +x start.sh' first)."
        else
            echo "ERROR: Failed to copy '.env.example'." >&2
            exit 1
        fi
    else
        echo "ERROR: '.env.example' not found either. Cannot create '.env'. Please create it manually." >&2
    fi
    exit 1
fi

# Load environment variables from .env file
echo "Loading environment variables from '.env'..."
# Use 'set -a' to export all variables defined subsequently
# Use 'source' to execute the .env file in the current shell context
# Filter out comments and empty lines before sourcing
set -a
if [ -f "$ENV_FILE" ]; then
    # Use grep to filter out comments and empty lines before sourcing
    # This prevents errors if the .env file contains invalid shell commands
    source <(grep -vE '^\s*#|^\s*$' "$ENV_FILE")
fi
set +a # Stop exporting automatically

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