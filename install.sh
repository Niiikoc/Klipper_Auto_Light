#!/bin/bash
# Install script for Klipper Auto Light
# Symlinks auto_light.py into Klipper's extras directory so the module
# can be managed (and updated) via Moonraker's Update Manager, and links the
# optional UI macros file into the printer config folder.
set -e

KLIPPER_PATH="${KLIPPER_PATH:-${HOME}/klipper}"
CONFIG_PATH="${CONFIG_PATH:-${HOME}/printer_data/config}"
MODULE_NAME="auto_light.py"
MACROS_NAME="auto_light_macros.cfg"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Verify Klipper is installed where we expect
if [ ! -d "${KLIPPER_PATH}/klippy/extras" ]; then
    echo "ERROR: Could not find Klipper extras dir at ${KLIPPER_PATH}/klippy/extras"
    echo "       Set KLIPPER_PATH if your Klipper install lives elsewhere."
    exit 1
fi

echo "Linking ${MODULE_NAME} into Klipper extras..."
ln -sf "${REPO_DIR}/${MODULE_NAME}" "${KLIPPER_PATH}/klippy/extras/${MODULE_NAME}"

if [ -d "${CONFIG_PATH}" ]; then
    echo "Linking ${MACROS_NAME} into ${CONFIG_PATH}..."
    ln -sf "${REPO_DIR}/${MACROS_NAME}" "${CONFIG_PATH}/${MACROS_NAME}"
    echo "Add '[include ${MACROS_NAME}]' to printer.cfg for the UI buttons."
else
    echo "Config folder ${CONFIG_PATH} not found - skipping UI macros"
    echo "(set CONFIG_PATH to link them)."
fi

echo "Done. Restart Klipper to load the module (Moonraker does this"
echo "automatically when updating via the Update Manager)."
