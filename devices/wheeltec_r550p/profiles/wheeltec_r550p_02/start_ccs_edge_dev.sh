#!/usr/bin/env bash
set -eo pipefail
export PYTHONDONTWRITEBYTECODE=1

WORKSPACE="${CCS_EDGE_WORKSPACE:-/home/nrc15/ccs_edge_ws}"
NATIVE_WORKSPACE="${CCS_LIVOX_SETUP:-/home/nrc15/livox_fastlio/devel/setup.bash}"
NATIVE_WORKSPACE="$(dirname "$(dirname "${NATIVE_WORKSPACE}")")"
PROFILE_CONFIG_DIR="${CCS_EDGE_PROFILE_CONFIG_DIR:-${WORKSPACE}/config/wheeltec_r550p_02}"
GROUND_STATION_IP="${CCS_GROUND_STATION_IP:-192.168.50.101}"
NTP_SERVER="${CCS_NTP_SERVER:-${GROUND_STATION_IP}}"
ROS_IP_VALUE="${CCS_ROS_IP:-192.168.50.123}"
STATE_DIR="${WORKSPACE}/run/managed"
LOG_ROOT="${CCS_EDGE_LOG_ROOT:-${WORKSPACE}/logs}"
LOG_DIR="${LOG_ROOT}/__preflight__"
STARTUP_LOG=""
PREFLIGHT="${WORKSPACE}/scripts/ccs_wheeltec_preflight.py"
READINESS="${WORKSPACE}/scripts/ccs_wheeltec_readiness.py"
CHECK_ONLY=false
SHUTDOWN_STARTED=false
ROSCORE_PID=""
CAMERA_PID=""
CAMERA_REPORTED=false
LAUNCH_NAMES=(base mqtav udp_telemetry map_stream relocalization task_control)
NODE_NAMES=(/wheeltec_robot /epgeneral_mqtav /epgeneral_udp_telemetry /epgeneral_map_stream /epgeneral_relocalization /epgeneral_task_control)
PIDS=("" "" "" "" "" "")

case "${1:-}" in
  "") ;;
  --check|--preflight) CHECK_ONLY=true ;;
  *) printf 'Usage: %s [--check|--preflight]\n' "$0" >&2; exit 2 ;;
esac
[[ "$#" -le 1 ]] || { printf 'Unexpected arguments\n' >&2; exit 2; }
record() { [[ -z "${STARTUP_LOG}" ]] || printf '%s %s\n' "$(date -Is)" "$*" >>"${STARTUP_LOG}"; }
report() { printf '[%s] %s\n' "$1" "$2"; record "[$1] $2"; }
fail() { report ERROR "$*" >&2; exit 1; }
run_quiet() {
  local output status
  if output="$("$@" 2>&1)"; then return 0; else
    status=$?; record "${output}"; printf '%s\n' "${output}" >&2; return "${status}"
  fi
}
master_exists() { timeout 5 rosparam list >/dev/null 2>&1; }
ros_node_exists() { local nodes; nodes="$(timeout 5 rosnode list 2>/dev/null)" && grep -Fxq -- "$1" <<<"${nodes}"; }
owned_process_alive() {
  local info
  [[ "$1" =~ ^[0-9]+$ ]] || return 1
  info="$(ps -o ppid=,pgid=,sid=,stat= -p "$1")" || return 1
  read -r parent group session status <<<"${info}"
  [[ "${parent}" == "$$" && "${group}" == "$1" && "${session}" == "$1" && "${status}" != Z* ]]
}
stop_process() {
  local pid="$1" attempt
  kill -0 "${pid}" 2>/dev/null || { wait "${pid}" 2>/dev/null || true; return 0; }
  owned_process_alive "${pid}" || { report ERROR "PID ${pid} ownership changed; not signaling it."; return 1; }
  kill -INT "${pid}" 2>/dev/null || true
  for attempt in $(seq 1 120); do
    kill -0 "${pid}" 2>/dev/null || { wait "${pid}" 2>/dev/null || true; return 0; }
    sleep .25
  done
  owned_process_alive "${pid}" || return 1
  kill -TERM "${pid}" 2>/dev/null || true
  for attempt in $(seq 1 40); do
    kill -0 "${pid}" 2>/dev/null || { wait "${pid}" 2>/dev/null || true; return 0; }
    sleep .25
  done
  report ERROR "Owned PID ${pid} did not exit; inspect logs before restarting."
  return 1
}
publish_zero_velocity() {
  # No Go2 enable/disable RPC exists on this serial chassis.
  # rostopic -1 includes three seconds of latching after Python/ROS startup.
  run_quiet timeout 10 rostopic pub -1 /cmd_vel geometry_msgs/Twist \
    '{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}'
}
shutdown_all() {
  local exit_code="${1:-0}" index
  [[ "${SHUTDOWN_STARTED}" == true ]] && return
  SHUTDOWN_STARTED=true; trap - INT TERM EXIT; set +e
  record "shutdown started exit_code=${exit_code}"
  if [[ -n "${CAMERA_PID}" ]]; then stop_process "${CAMERA_PID}" || true; fi
  # Task adapter cancels its own goals/navigation before drivers and master stop.
  if [[ -n "${PIDS[5]}" ]]; then
    if stop_process "${PIDS[5]}"; then PIDS[5]=""; rm -f "${STATE_DIR}/task_control.pid"; else exit_code=1; fi
  fi
  if [[ -n "${PIDS[0]}" ]] && owned_process_alive "${PIDS[0]}" && master_exists; then
    publish_zero_velocity || { report ERROR "Zero velocity publication failed."; exit_code=1; }
    run_quiet python3 "${READINESS}" stopped --timeout 10 || { report ERROR "Fresh zero wheel speed not confirmed."; exit_code=1; }
  fi
  for ((index=${#PIDS[@]}-1; index>=0; index--)); do
    [[ -n "${PIDS[index]}" ]] || continue
    if stop_process "${PIDS[index]}"; then rm -f "${STATE_DIR}/${LAUNCH_NAMES[index]}.pid"; else exit_code=1; fi
  done
  if [[ -n "${ROSCORE_PID}" ]]; then
    if stop_process "${ROSCORE_PID}"; then rm -f "${STATE_DIR}/roscore.pid"; else exit_code=1; fi
  fi
  rm -f "${STATE_DIR}/startup.pid"
  report OK "WheelTech workflow stopped; exit_code=${exit_code}."
  exit "${exit_code}"
}
for setup in /opt/ros/noetic/setup.bash "${NATIVE_WORKSPACE}/devel/setup.bash" "${WORKSPACE}/devel/setup.bash"; do
  [[ -r "${setup}" ]] || fail "Workspace is not built: ${setup}"
done
source /opt/ros/noetic/setup.bash
source "${NATIVE_WORKSPACE}/devel/setup.bash" --extend
source "${WORKSPACE}/devel/setup.bash" --extend
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
export ROS_IP="${ROS_IP_VALUE}" PYTHONDONTWRITEBYTECODE=1
export ROS_HOME="${WORKSPACE}/run/ros_home"
mkdir -p "${ROS_HOME}"
command -v setsid >/dev/null && command -v flock >/dev/null || fail "setsid/flock are required."
if [[ "${CHECK_ONLY}" != true ]]; then
  mkdir -p "${STATE_DIR}"
  exec 9>"${STATE_DIR}/startup.lock"
  flock -n 9 || fail "The UGV_004 workflow is already running."
fi
run_quiet python3 "${PREFLIGHT}" --profile "${PROFILE_CONFIG_DIR}" --workspace "${WORKSPACE}" \
  --native-workspace "${NATIVE_WORKSPACE}" --device-ip "${ROS_IP_VALUE}" --station-ip "${GROUND_STATION_IP}" || fail "Profile preflight failed."
[[ -r /dev/wheeltec_controller && -w /dev/wheeltec_controller ]] || fail "Wheeltec controller is unavailable or not accessible."
ip -o -4 addr show dev wlan0 | awk '{print $4}' | grep -Fxq "${ROS_IP_VALUE}/24" || fail "Wheeltec LAN address is missing."
ip -o -4 addr show dev eth0 | awk '{print $4}' | grep -Fxq '192.168.123.5/24' || fail "Livox host address is missing."
ping -I eth0 -c 1 -W 2 192.168.123.124 >/dev/null || fail "MID360 is unreachable."
# timesyncd adjusts the clock; availability alone also succeeds with a 1970 clock.
systemctl is-active --quiet systemd-timesyncd || fail "Time synchronization service is inactive. Run: sudo systemctl enable --now systemd-timesyncd"
report INFO "Waiting for clock synchronization with ${NTP_SERVER} (maximum 45 seconds)."
if time_sync_output="$(python3 "${WORKSPACE}/scripts/ccs_sntp_sync.py" --server "${NTP_SERVER}" --wait-sync 45 --max-offset 0.5 2>&1)"; then
  report OK "Clock synchronized: ${time_sync_output}"
else
  printf '%s\n' "${time_sync_output}" >&2
  fail "Clock is not synchronized with ${NTP_SERVER}; refusing to start ROS services."
fi
gst-inspect-1.0 srtsink >/dev/null 2>&1 && gst-inspect-1.0 x264enc >/dev/null 2>&1 || report WARN "Video dependencies incomplete; camera/video may be degraded."

launch() {
  local index="$1" name pid attempt; shift
  name="${LAUNCH_NAMES[index]}"
  run_quiet python3 "${PREFLIGHT}" --launch "$@" || fail "Invalid ${name} launch."
  [[ "${CHECK_ONLY}" == true ]] && return 0
  setsid roslaunch "$@" >"${LOG_DIR}/${name}.log" 2>&1 </dev/null &
  pid=$!; PIDS[index]="${pid}"; printf '%s\n' "${pid}" >"${STATE_DIR}/${name}.pid"
  for attempt in $(seq 1 30); do
    kill -0 "${pid}" 2>/dev/null || fail "${name} exited; inspect ${LOG_DIR}/${name}.log."
    if owned_process_alive "${pid}" && ros_node_exists "${NODE_NAMES[index]}"; then
      report OK "${name} node is ready."; return 0
    fi
    sleep 1
  done
  fail "${name} startup timed out; inspect ${LOG_DIR}/${name}.log."
}

if [[ "${CHECK_ONLY}" != true ]]; then
  if master_exists; then
    existing_nodes="$(timeout 5 rosnode list)"
    for node in "${NODE_NAMES[@]}" /livox_lidar_publisher2 /epgeneral_navigation_task_adapter \
      /laserMapping /wheeltec_pointcloud_mapper /wheeltec_tf_manager /wheeltec_pose_adapter \
      /wheeltec_global_localizer /ccs_wheeltec_localizer /wheeltec_cloud_adapter /move_base; do
      grep -Fxq -- "${node}" <<<"${existing_nodes}" && fail "Existing ${node}; stop its owner before starting CCS."
    done
  fi
  RUN_ID="$(date -u +%Y%m%dT%H%M%S.%NZ)_$$"
  LOG_DIR="${LOG_ROOT}/${RUN_ID}"; STARTUP_LOG="${LOG_DIR}/startup.log"
  mkdir -p "${LOG_DIR}/ros"
  ln -sfn -- "${RUN_ID}" "${LOG_ROOT}/latest"
  export ROS_LOG_DIR="${LOG_DIR}/ros"
  printf '%s\n' "$$" >"${STATE_DIR}/startup.pid"
  trap 'shutdown_all 130' INT
  trap 'shutdown_all 143' TERM
  trap 'shutdown_all $?' EXIT
  record "startup pid=$$ UGV_004 video=optional"
  record "time synchronization: ${time_sync_output}"
  if ! master_exists; then
    setsid roscore >"${LOG_DIR}/roscore.log" 2>&1 </dev/null &
    ROSCORE_PID=$!; printf '%s\n' "${ROSCORE_PID}" >"${STATE_DIR}/roscore.pid"
    for attempt in $(seq 1 20); do master_exists && break; sleep 1; done
    master_exists || fail "ROS master did not start."
  fi
fi
launch 0 "${WORKSPACE}/launch/wheeltec_r550p_02_base.launch"
if [[ "${CHECK_ONLY}" != true ]]; then
  run_quiet python3 "${READINESS}" inputs --timeout 30 || fail "Base sensor inputs are not fresh."
  publish_zero_velocity || fail "Initial zero velocity publication failed."
  run_quiet python3 "${READINESS}" stopped --timeout 10 || fail "Wheel speeds are not zero."
  report OK "Base sensors are fresh and wheel speeds are zero."
fi
launch 1 epgeneral_mqtav epgeneral_mqtav.launch config_file:="${PROFILE_CONFIG_DIR}/epgeneral_mqtav.yaml" \
  device_config_file:="${PROFILE_CONFIG_DIR}/device.yaml" log_dir:="${LOG_DIR}/mqtav"
launch 2 epgeneral_udp_telemetry epgeneral_udp_telemetry.launch telemetry_config_file:="${PROFILE_CONFIG_DIR}/udp_telemetry.yaml" \
  device_config_file:="${PROFILE_CONFIG_DIR}/device.yaml" destination_host:="${GROUND_STATION_IP}" destination_port:=14560 \
  link_status_topic:=/ugv/UGV_004/link/udp_tx diagnostics_topic:=/ugv/UGV_004/diagnostics
launch 3 epgeneral_map_stream epgeneral_map_stream.launch mapping_config_file:="${PROFILE_CONFIG_DIR}/map_stream.yaml" \
  device_config_file:="${PROFILE_CONFIG_DIR}/device.yaml" log_dir:="${LOG_DIR}/mapping"
launch 4 epgeneral_relocalization epgeneral_relocalization.launch config_file:="${PROFILE_CONFIG_DIR}/relocalization.yaml" \
  device_config_file:="${PROFILE_CONFIG_DIR}/device.yaml" log_dir:="${LOG_DIR}/relocalization"
launch 5 epgeneral_task_control navigation_task_control.launch task_config_file:="${PROFILE_CONFIG_DIR}/task_control.yaml" \
  device_config_file:="${PROFILE_CONFIG_DIR}/device.yaml"
if [[ "${CHECK_ONLY}" == true ]]; then
  report OK "UGV_004 configuration, dependencies and launches passed; no nodes were started."
  exit 0
fi
ros_node_exists /epgeneral_navigation_task_adapter || fail "Navigation task adapter is absent."
setsid python3 -u "${WORKSPACE}/scripts/ccs_camera_supervisor.py" --profile "${PROFILE_CONFIG_DIR}" --log-dir "${LOG_DIR}" --owner-pid "$$" >"${LOG_DIR}/camera_supervisor.log" 2>&1 </dev/null &
CAMERA_PID=$!
report OK "UGV_004 services running; optional RGBD/SRT startup is logged in camera_supervisor.log."
while true; do
  sleep 2
  if [[ "${CAMERA_REPORTED}" == false ]] && ! owned_process_alive "${CAMERA_PID}"; then
    report WARN "Camera/video degraded; inspect ${LOG_DIR}/camera_supervisor.log. Other services continue."
    CAMERA_REPORTED=true
  fi
  for index in "${!PIDS[@]}"; do
    owned_process_alive "${PIDS[index]}" || fail "${LAUNCH_NAMES[index]} exited or ownership changed."
  done
  [[ -z "${ROSCORE_PID}" ]] || owned_process_alive "${ROSCORE_PID}" || fail "Owned master exited."
  for attempt in 1 2 3; do
    missing=true
    if nodes="$(timeout 5 rosnode list 2>>"${LOG_DIR}/runtime_monitor.log")"; then
      missing=false
      for node in "${NODE_NAMES[@]}" /livox_lidar_publisher2 /epgeneral_navigation_task_adapter; do
        grep -Fxq -- "${node}" <<<"${nodes}" || missing=true
      done
    fi
    [[ "${missing}" == false ]] && break
    record "ROS node check attempt=${attempt}/3 failed"; sleep 1
  done
  [[ "${missing}" == false ]] || fail "Required nodes absent after three checks."
done
