#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-check}"
PACKAGE_DIR="${2:-/home/nrc19/livox_fastlio/src/turn_on_wheeltec_robot}"
WORKSPACE="${3:-/home/nrc19/livox_fastlio}"
PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_ROOT="${CCS_DRIVER_BACKUP_ROOT:-${HOME}/.deployment_backups}"
BACKUP_ARCHIVE="${4:-}"

verify_manifest() {
  local manifest="$1"
  (
    cd "${PACKAGE_DIR}"
    sha256sum -c "${PATCH_DIR}/${manifest}"
  )
}

driver_is_running() {
  source /opt/ros/noetic/setup.bash
  source "${WORKSPACE}/devel/setup.bash" --extend
  rosnode list 2>/dev/null | grep -Fxq /wheeltec_robot
}

build_driver() {
  source /opt/ros/noetic/setup.bash
  cd "${WORKSPACE}"
  catkin_make -j1 --pkg turn_on_wheeltec_robot
}

case "${ACTION}" in
  check)
    if verify_manifest patched.sha256 >/dev/null 2>&1; then
      echo "PATCHED"
    elif verify_manifest baseline.sha256 >/dev/null 2>&1; then
      echo "BASELINE"
    else
      echo "UNKNOWN: source hashes do not match baseline or patched manifests" >&2
      exit 1
    fi
    ;;
  apply)
    if verify_manifest patched.sha256 >/dev/null 2>&1; then
      echo "ALREADY_PATCHED"
      exit 0
    fi
    verify_manifest baseline.sha256
    if driver_is_running; then
      echo "refusing to patch while /wheeltec_robot is running" >&2
      exit 1
    fi
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    backup_dir="${BACKUP_ROOT}/${stamp}_ugv003_control_authority"
    mkdir -p "${backup_dir}"
    tar -C "$(dirname "${PACKAGE_DIR}")" -czf "${backup_dir}/turn_on_wheeltec_robot.tar.gz" \
      "$(basename "${PACKAGE_DIR}")"
    sha256sum "${backup_dir}/turn_on_wheeltec_robot.tar.gz" \
      >"${backup_dir}/turn_on_wheeltec_robot.tar.gz.sha256"
    patch --dry-run -d "${PACKAGE_DIR}" -p4 \
      <"${PATCH_DIR}/turn_on_wheeltec_robot_control_authority.patch"
    patch -d "${PACKAGE_DIR}" -p4 \
      <"${PATCH_DIR}/turn_on_wheeltec_robot_control_authority.patch"
    verify_manifest patched.sha256
    build_driver
    echo "PATCHED backup=${backup_dir}/turn_on_wheeltec_robot.tar.gz"
    ;;
  rollback)
    [[ -n "${BACKUP_ARCHIVE}" && -r "${BACKUP_ARCHIVE}" ]] || {
      echo "rollback requires a readable backup archive as argument 4" >&2
      exit 2
    }
    if driver_is_running; then
      echo "refusing to roll back while /wheeltec_robot is running" >&2
      exit 1
    fi
    [[ -r "${BACKUP_ARCHIVE}.sha256" ]] && (
      cd "$(dirname "${BACKUP_ARCHIVE}")"
      sha256sum -c "$(basename "${BACKUP_ARCHIVE}").sha256"
    )
    tar -C "$(dirname "${PACKAGE_DIR}")" -xzf "${BACKUP_ARCHIVE}"
    verify_manifest baseline.sha256
    build_driver
    echo "ROLLED_BACK"
    ;;
  *)
    echo "usage: $0 {check|apply|rollback} [package_dir] [workspace] [backup_archive]" >&2
    exit 2
    ;;
esac
