#!/bin/bash

# ==============================================================================
# Script Name: install_agent_tools.sh
# Description: Installs core system dependencies and tools for the agent environment.
# ==============================================================================

# Exit immediately if a command exits with a non-zero status (fails), 
# and treat unset variables as an error.
set -euo pipefail

# --- Dynamic Path Configuration ---
# TOOLS_DIR: Dynamically fetches the full absolute path of the directory where this script lives
TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ROOT_DIR: Gets the parent directory of TOOLS_DIR using bash parameter expansion
ROOT_DIR="${TOOLS_DIR%/*}"

# LOG_INSTALLER: Sets the log directory path inside the ROOT_DIR
LOG_INSTALLER="$ROOT_DIR/logs"

# Ensure the log directory exists before trying to write to it
mkdir -p "$LOG_INSTALLER"

# Define the full path for the log file
LOG_FILE="$LOG_INSTALLER/install_agent_tools.log"

# --- Logging Function ---
# Takes a message as an argument and prints it with a timestamp.
# It outputs to the terminal and appends to the log file.
log_message() {
    local TYPE="$1"
    local MESSAGE="$2"
    local TIMESTAMP
    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
    echo "[${TIMESTAMP}] [${TYPE}] ${MESSAGE}" | sudo tee -a "${LOG_FILE}"
}

# --- Pre-flight Checks ---
# Ensure the user has sudo privileges before starting the heavy lifting.
if ! sudo -v &> /dev/null; then
    echo "ERROR: This script requires sudo privileges. Please run as root or a sudoer."
    exit 1
fi

log_message "INFO" "Starting agent tools installation process..."
log_message "INFO" "Script Location: $TOOLS_DIR"
log_message "INFO" "Parent Directory: $ROOT_DIR"
log_message "INFO" "Log Directory: $LOG_INSTALLER"

# --- Step 1: Update Package Lists ---
log_message "INFO" "Updating APT package lists..."
# DEBIAN_FRONTEND=noninteractive prevents interactive prompts from freezing the script
sudo DEBIAN_FRONTEND=noninteractive apt-get update -y 2>&1 | sudo tee -a "${LOG_FILE}"

# --- Step 2: Install Packages ---
# Package Breakdown:
# - build-essential : GNU C/C++ compiler and essential build tools
# - git, curl, wget : Source control and HTTP/Network download utilities
# - texlive-full    : Comprehensive TeX document production system
# - python3-full    : Python 3 ecosystem (includes pip, venv, and dev headers)
# - poppler-utils   : PDF rendering and manipulation command-line utilities
# - pandoc          : Universal document format converter
log_message "INFO" "Installing required packages. This may take a while due to texlive-full..."

sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential \
    git \
    curl \
    wget \
    texlive-full \
    python3-full \
    poppler-utils \
    pandoc \
    2>&1 | sudo tee -a "${LOG_FILE}"

# --- Step 3: Cleanup ---
# Clean the local repository of retrieved package files to free up disk space.
log_message "INFO" "Cleaning up APT cache to save disk space..."
sudo apt-get clean -y 2>&1 | sudo tee -a "${LOG_FILE}"
sudo apt-get autoremove -y 2>&1 | sudo tee -a "${LOG_FILE}"

log_message "INFO" "Installation completed successfully! Logs are available at ${LOG_FILE}."