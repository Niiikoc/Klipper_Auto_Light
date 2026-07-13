#!/bin/bash
# Install script for Klipper Auto Light
# Symlinks auto_light.py into Klipper's extras directory so the module
# can be managed (and updated) via Moonraker's Update Manager.
set -e

KLIPPER_PATH="${HOME}/klipper"
MODULE_NAME="auto_light.py"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Verify Klipper is installed where we expect
if [ ! -d "${KLIPPER_PATH}/klippy/extras" ]; then
    echo "ERROR: Could not find Klipper extras dir at ${KLIPPER_PATH}/klippy/extras"
    echo "       Set KLIPPER_PATH if your Klipper install lives elsewhere."
    exit 1
fi

echo "Linking ${MODULE_NAME} into Klipper extras..."
ln -sf "${REPO_DIR}/${MODULE_NAME}" "${KLIPPER_PATH}/klippy/extras/${MODULE_NAME}"

echo "Done. Restart Klipper to load the module (Moonraker does this"
echo "automatically when updating via the Update Manager)."
