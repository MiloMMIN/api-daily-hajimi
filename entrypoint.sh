#!/bin/sh

# Entrypoint script for api-daily scheduler
# This script manages the scheduling loop using lightweight shell commands
# to minimize memory footprint when idle.

echo "[Entrypoint] Starting api-daily scheduler..."

# First run check
FIRST_RUN=1

while true; do
    if [ "$FIRST_RUN" -eq 1 ]; then
        echo "[Entrypoint] Checking startup configuration..."
        # Check if we should run immediately on startup
        SLEEP_SEC=$(python main.py --next-run --startup)
        FIRST_RUN=0
    else
        # Calculate time until next run
        SLEEP_SEC=$(python main.py --next-run)
    fi

    # Ensure SLEEP_SEC is a valid number (fallback to 60s on error)
    if ! echo "$SLEEP_SEC" | grep -qE '^[0-9]+$'; then
        echo "[Entrypoint] Error calculating next run time. Retrying in 60s..."
        echo "[Debug] Output was: $SLEEP_SEC"
        sleep 60
        continue
    fi

    echo "[Entrypoint] Next run in $SLEEP_SEC seconds."

    if [ "$SLEEP_SEC" -le 0 ]; then
        echo "[Entrypoint] Running task immediately..."
    else
        # Sleep until the scheduled time
        # Using wait allows for signal handling if needed in future
        sleep "$SLEEP_SEC" &
        wait $!
    fi

    # Execute the worker task
    echo "[Entrypoint] Launching worker process..."
    python main.py --worker
    
    # Optional: small pause to prevent tight loops in case of errors
    sleep 2
done
