#!/usr/bin/env bash
# Install yelp-data-extractor into a virtual environment selected by the user.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_TARGET="${INSTALL_TARGET:-.[dev]}"
COMMAND_NAME="yelp-data-extractor"
SYMLINK_PATH="${PROJECT_ROOT}/${COMMAND_NAME}"
INSTALL_DIR="${INSTALL_DIR:-}"
VENV_DIR=""

log() {
    printf '[setup] %s\n' "$1"
}

require_python() {
    # Fail early with a clear message before attempting to create the venv.
    if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
        printf 'Error: %s was not found on PATH.\n' "${PYTHON_BIN}" >&2
        printf 'Install Python 3.10+ or set PYTHON_BIN=/path/to/python.\n' >&2
        exit 1
    fi
}

default_install_dir() {
    # Print the per-user default install directory for this operating system.
    case "$(uname -s)" in
        Darwin)
            printf '%s\n' "${HOME}/Library/Application Support/yelp-data-extractor"
            ;;
        Linux)
            printf '%s\n' "${XDG_DATA_HOME:-${HOME}/.local/share}/yelp-data-extractor"
            ;;
        CYGWIN*|MINGW*|MSYS*)
            printf '%s\n' "${LOCALAPPDATA:-${HOME}/AppData/Local}/yelp-data-extractor"
            ;;
        *)
            printf '%s\n' "${HOME}/.yelp-data-extractor"
            ;;
    esac
}

expand_path() {
    # Expand a leading tilde in user-entered install paths.
    local path="$1"
    case "${path}" in
        "~")
            printf '%s\n' "${HOME}"
            ;;
        "~/"*)
            printf '%s\n' "${HOME}/${path#~/}"
            ;;
        *)
            printf '%s\n' "${path}"
            ;;
    esac
}

choose_from_menu() {
    # Prompt for the broad install-location strategy.
    local default_dir
    default_dir="$(default_install_dir)"

    printf '\nyelp-data-extractor install location\n'
    printf '1) Default OS location: %s\n' "${default_dir}"
    printf '2) Choose a different location\n'
    printf '3) Project-local install: %s\n' "${PROJECT_ROOT}/.venv"
    printf 'Select an option [1]: '

    local choice
    read -r choice
    case "${choice:-1}" in
        1)
            INSTALL_DIR="${default_dir}"
            ;;
        2)
            INSTALL_DIR="$(pick_directory)"
            ;;
        3)
            INSTALL_DIR="${PROJECT_ROOT}/.venv"
            ;;
        *)
            printf 'Error: invalid menu option: %s\n' "${choice}" >&2
            exit 1
            ;;
    esac
}

pick_directory() {
    # Open a simple terminal directory picker and print the selected path.
    local current_dir="${HOME}"

    while true; do
        printf '\nCurrent directory: %s\n' "${current_dir}" >&2
        printf '0) Use this directory\n' >&2
        printf '1) Go to parent directory\n' >&2
        printf '2) Enter path manually\n' >&2

        local index=3
        local directories=()
        local directory
        while IFS= read -r directory; do
            directories+=("${directory}")
            printf '%s) %s\n' "${index}" "$(basename "${directory}")" >&2
            index=$((index + 1))
        done < <(find "${current_dir}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort)

        printf 'Select a directory option: ' >&2
        local choice
        read -r choice

        if [ "${choice}" = "0" ]; then
            printf '%s\n' "${current_dir}"
            return
        elif [ "${choice}" = "1" ]; then
            current_dir="$(cd "${current_dir}/.." && pwd)"
        elif [ "${choice}" = "2" ]; then
            printf 'Enter install directory: ' >&2
            local manual_path
            read -r manual_path
            if [ -z "${manual_path}" ]; then
                printf 'Path cannot be empty.\n' >&2
                continue
            fi
            printf '%s\n' "$(expand_path "${manual_path}")"
            return
        elif [[ "${choice}" =~ ^[0-9]+$ ]] && [ "${choice}" -ge 3 ] && [ "${choice}" -lt "${index}" ]; then
            current_dir="${directories[$((choice - 3))]}"
        else
            printf 'Invalid option.\n' >&2
        fi
    done
}

prepare_install_location() {
    INSTALL_DIR="$(expand_path "${INSTALL_DIR}")"
    mkdir -p "${INSTALL_DIR}"

    if [ "${INSTALL_DIR}" = "${PROJECT_ROOT}/.venv" ]; then
        VENV_DIR="${INSTALL_DIR}"
    else
        VENV_DIR="${INSTALL_DIR}/.venv"
    fi

    log "Install directory: ${INSTALL_DIR}"
    log "Virtual environment: ${VENV_DIR}"
}

create_virtualenv() {
    if [ -d "${VENV_DIR}" ]; then
        log "Using existing virtual environment"
        return
    fi

    log "Creating virtual environment"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
}

install_project() {
    log "Upgrading pip"
    "${VENV_DIR}/bin/python" -m pip install --upgrade pip

    log "Installing yelp-data-extractor with dependencies"
    cd "${PROJECT_ROOT}"
    "${VENV_DIR}/bin/python" -m pip install -e "${INSTALL_TARGET}"
}

create_command_symlink() {
    local command_path="${VENV_DIR}/bin/${COMMAND_NAME}"

    if [ ! -x "${command_path}" ]; then
        printf 'Error: expected command was not installed: %s\n' "${command_path}" >&2
        exit 1
    fi

    # Replace an old symlink, but avoid overwriting a real user-created file.
    if [ -L "${SYMLINK_PATH}" ]; then
        rm "${SYMLINK_PATH}"
    elif [ -e "${SYMLINK_PATH}" ]; then
        printf 'Error: cannot create symlink because this path already exists: %s\n' "${SYMLINK_PATH}" >&2
        exit 1
    fi

    ln -s "${command_path}" "${SYMLINK_PATH}"
    log "Created symlink: ${SYMLINK_PATH} -> ${command_path}"
}

main() {
    log "Project root: ${PROJECT_ROOT}"
    require_python
    if [ -z "${INSTALL_DIR}" ]; then
        choose_from_menu
    fi
    prepare_install_location
    create_virtualenv
    install_project
    create_command_symlink
    log "Install complete. Run ./yelp-data-extractor --help"
}

main "$@"
