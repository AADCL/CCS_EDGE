#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-check}"
PACKAGE_DIR="${2:-/home/nrc19/livox_fastlio/src/wheeltec_safety}"
WORKSPACE="${3:-/home/nrc19/livox_fastlio}"
PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_ROOT="${CCS_SAFETY_BACKUP_ROOT:-${HOME}/.deployment_backups}"
BACKUP_ARCHIVE="${4:-}"

verify_manifest() {
  local manifest="$1"
  (
    cd "${PACKAGE_DIR}"
    sha256sum -c "${PATCH_DIR}/${manifest}"
  )
}

safety_is_running() {
  source /opt/ros/noetic/setup.bash
  source "${WORKSPACE}/devel/setup.bash" --extend
  rosnode list 2>/dev/null | grep -Fxq /wheeltec_safety
}

test_safety() {
  PYTHONPATH="${PACKAGE_DIR}/src" python3 -m unittest discover \
    -s "${PACKAGE_DIR}/test" -p 'test_*.py'
}

build_safety() {
  source /opt/ros/noetic/setup.bash
  cd "${WORKSPACE}"
  catkin_make -j1 --pkg wheeltec_safety
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
    if safety_is_running; then
      echo "refusing to patch while /wheeltec_safety is running" >&2
      exit 1
    fi
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    backup_dir="${BACKUP_ROOT}/${stamp}_ugv003_safety"
    mkdir -p "${backup_dir}"
    tar -C "$(dirname "${PACKAGE_DIR}")" -czf \
      "${backup_dir}/wheeltec_safety.tar.gz" "$(basename "${PACKAGE_DIR}")"
    sha256sum "${backup_dir}/wheeltec_safety.tar.gz" \
      >"${backup_dir}/wheeltec_safety.tar.gz.sha256"
    patch --dry-run -d "${PACKAGE_DIR}" -p4 \
      <"${PATCH_DIR}/wheeltec_safety_snapshot_and_reverse.patch"
    patch -d "${PACKAGE_DIR}" -p4 \
      <"${PATCH_DIR}/wheeltec_safety_snapshot_and_reverse.patch"
    verify_manifest patched.sha256
    test_safety
    build_safety
    echo "PATCHED backup=${backup_dir}/wheeltec_safety.tar.gz"
    ;;
  rollback)
    [[ -n "${BACKUP_ARCHIVE}" && -r "${BACKUP_ARCHIVE}" ]] || {
      echo "rollback requires a readable backup archive as argument 4" >&2
      exit 2
    }
    if safety_is_running; then
      echo "refusing to roll back while /wheeltec_safety is running" >&2
      exit 1
    fi
    [[ -r "${BACKUP_ARCHIVE}.sha256" ]] && (
      cd "$(dirname "${BACKUP_ARCHIVE}")"
      sha256sum -c "$(basename "${BACKUP_ARCHIVE}").sha256"
    )
    tar -C "$(dirname "${PACKAGE_DIR}")" -xzf "${BACKUP_ARCHIVE}"
    verify_manifest baseline.sha256
    test_safety
    build_safety
    echo "ROLLED_BACK"
    ;;
  *)
    echo "usage: $0 {check|apply|rollback} [package_dir] [workspace] [backup_archive]" >&2
    exit 2
    ;;
esac
