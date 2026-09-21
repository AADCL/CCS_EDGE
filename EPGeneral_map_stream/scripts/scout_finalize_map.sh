#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'scout_finalize_map: %s\n' "$*" >&2; exit 1; }

check_tools() {
  local package_name="$1" executable="$2" map_root="$3" package_dir
  command -v rosrun >/dev/null 2>&1 || fail "rosrun is unavailable"
  command -v rospack >/dev/null 2>&1 || fail "rospack is unavailable"
  package_dir=$(rospack find "${package_name}") || fail "ROS package is unavailable: ${package_name}"
  [[ -x "${package_dir}/scripts/${executable}" || -x "${package_dir}/${executable}" ]] \
    || fail "ROS executable is unavailable: ${package_name}/${executable}"
  [[ -d "${map_root}" && -w "${map_root}" ]] || fail "map root is unavailable or not writable"
}

if [[ "${1:-}" == "--check" ]]; then
  [[ "$#" -eq 4 ]] || fail "usage: $0 --check PACKAGE EXECUTABLE MAP_ROOT"
  check_tools "$2" "$3" "$4"
  exit 0
fi

[[ "$#" -eq 9 ]] || fail "usage: $0 PACKAGE EXECUTABLE MAP_NAME MAP_ROOT TARGET_PCD TARGET_PGM TARGET_YAML LOG TIMEOUT"
PACKAGE_NAME="$1" EXECUTABLE="$2" MAP_NAME="$3" MAP_ROOT="$4"
TARGET_PCD="$5" TARGET_PGM="$6" TARGET_YAML="$7" LOG_FILE="$8" TIMEOUT="$9"
[[ "${MAP_NAME}" =~ ^[0-9]{8}_[0-9]{6}$ ]] || fail "map_name must use YYYYMMDD_HHMMSS"
check_tools "${PACKAGE_NAME}" "${EXECUTABLE}" "${MAP_ROOT}"
MAP_DIR="${MAP_ROOT}/${MAP_NAME}"
SOURCE_OT="${CCS_SOURCE_OT:-${MAP_DIR}/map.ot}"
TARGET_OT="${CCS_TARGET_OT:-$(dirname "${TARGET_PCD}")/map.ot}"
FILTERED_PCD="${MAP_DIR}/filtered_camera_init.pcd"
[[ -d "${MAP_DIR}" ]] || fail "map directory is missing: ${MAP_DIR}"
[[ -s "${FILTERED_PCD}" ]] || fail "filtered PCD is missing or empty: ${FILTERED_PCD}"
mkdir -p "$(dirname "${LOG_FILE}")" "$(dirname "${TARGET_PCD}")"
timeout --signal=INT --kill-after=5 "${TIMEOUT}" \
  rosrun "${PACKAGE_NAME}" "${EXECUTABLE}" "${MAP_NAME}" --replace-raw \
  >"${LOG_FILE}" 2>&1 \
  || fail "finalize_map failed; see ${LOG_FILE}"
for path in "${FILTERED_PCD}" "${MAP_DIR}/raw_camera_init.pcd" \
    "${MAP_DIR}/public_map.pcd" \
    "${MAP_DIR}/map_metadata.yaml"; do
  [[ -s "${path}" ]] || fail "finalized artifact is missing or empty: ${path}"
done
grep -Eq "^map_name:[[:space:]]*['\"]?${MAP_NAME}['\"]?[[:space:]]*$" \
  "${MAP_DIR}/map_metadata.yaml" || fail "map metadata does not match map_name: ${MAP_NAME}"
cp -p -- "${MAP_DIR}/public_map.pcd" "${TARGET_PCD}.tmp"
mv -f -- "${TARGET_PCD}.tmp" "${TARGET_PCD}"
if [[ -e "${MAP_DIR}/map.pgm" || -e "${MAP_DIR}/map.yaml" ]]; then
  [[ -s "${MAP_DIR}/map.pgm" && -s "${MAP_DIR}/map.yaml" ]] || fail "incomplete PGM/YAML pair"
  cp -p -- "${MAP_DIR}/map.pgm" "${TARGET_PGM}"
  cp -p -- "${MAP_DIR}/map.yaml" "${TARGET_YAML}"
fi
if [[ -s "${SOURCE_OT}" ]]; then cp -p -- "${SOURCE_OT}" "${TARGET_OT}"; fi
[[ "${CCS_OCCUPANCY_EXTERNAL:-0}" == 1 || -s "${TARGET_OT}" || ( -s "${TARGET_PGM}" && -s "${TARGET_YAML}" ) ]] || fail "missing occupancy outputs"
printf 'Scout map finalized: %s\n' "${MAP_DIR}"
