#!/usr/bin/env bash
set -eo pipefail

ACTION="${1:-status}"
WORKSPACE="${CCS_EDGE_WORKSPACE:-/home/nrc19/ccs_edge_ws}"
LIVOX_SETUP="${CCS_LIVOX_SETUP:-/home/nrc19/livox_fastlio/devel/setup.bash}"
PROFILE_CONFIG_DIR="${CCS_EDGE_PROFILE_CONFIG_DIR:-${WORKSPACE}/config/wheeltec_r550p}"
STATE_DIR="${CCS_EDGE_STATE_DIR:-${HOME}/.ros/ccs_edge_dev_wheeltec_r550p}"
LOG_DIR="${STATE_DIR}/log"
PID_DIR="${STATE_DIR}/run/video"
COLOR_TOPIC="/camera/color/image_raw"

mkdir -p "${LOG_DIR}" "${PID_DIR}"
[[ -r /opt/ros/noetic/setup.bash ]] || { echo "ROS Noetic setup is missing" >&2; exit 1; }
[[ -r "${LIVOX_SETUP}" ]] || { echo "Wheeltec underlay setup is missing" >&2; exit 1; }
[[ -r "${WORKSPACE}/devel/setup.bash" ]] || { echo "CCS overlay setup is missing" >&2; exit 1; }
source /opt/ros/noetic/setup.bash
source "${LIVOX_SETUP}"
source "${WORKSPACE}/devel/setup.bash" --extend
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
export ROS_IP="${CCS_ROS_IP:-192.168.50.122}"

pid_running() {
  local file="$1" pid
  [[ -r "${file}" ]] || return 1
  read -r pid <"${file}" || return 1
  [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null
}

stop_process() {
  local name="$1" file="${PID_DIR}/$1.pid" pid attempt
  if ! pid_running "${file}"; then
    rm -f "${file}"
    return
  fi
  read -r pid <"${file}"
  kill "${pid}" 2>/dev/null || true
  for attempt in $(seq 1 30); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.2
  done
  kill -KILL "${pid}" 2>/dev/null || true
  rm -f "${file}"
  echo "STOPPED ${name}"
}

wait_for_camera_frame() {
  local topic="$1" attempt
  for attempt in $(seq 1 30); do
    rostopic type "${topic}" >/dev/null 2>&1 && break
    [[ "${attempt}" != 30 ]] || return 1
    sleep 1
  done
  timeout 20 rostopic echo -n 1 "${topic}/header" >/dev/null 2>&1
}

start_video() {
  local started=() camera_external=false video_external=false
  rosparam list >/dev/null 2>&1 || {
    echo "ROS master is not available" >&2
    return 1
  }

  if rosnode list 2>/dev/null | grep -Fxq /camera/camera &&
      rostopic type "${COLOR_TOPIC}" >/dev/null 2>&1; then
    camera_external=true
  elif ! pid_running "${PID_DIR}/camera.pid"; then
    setsid roslaunch wheeltec_system_bringup wheeltec_orbbec336l.launch \
      >"${LOG_DIR}/camera.log" 2>&1 </dev/null &
    printf '%s\n' "$!" >"${PID_DIR}/camera.pid"
    started+=(camera)
  fi
  if ! wait_for_camera_frame "${COLOR_TOPIC}"; then
    echo "Gemini 336L color stream did not become ready; log=${LOG_DIR}/camera.log" >&2
    [[ " ${started[*]} " != *" camera "* ]] || stop_process camera
    return 1
  fi

  if rosnode list 2>/dev/null | grep -Fxq /epgeneral_video_srt; then
    video_external=true
  elif ! pid_running "${PID_DIR}/video_srt.pid"; then
    setsid roslaunch epgeneral_video_srt epgeneral_video_srt.launch \
      device_config_file:="${PROFILE_CONFIG_DIR}/device.yaml" \
      video_config_file:="${PROFILE_CONFIG_DIR}/video.yaml" \
      >"${LOG_DIR}/video_srt.log" 2>&1 </dev/null &
    printf '%s\n' "$!" >"${PID_DIR}/video_srt.pid"
    started+=(video_srt)
  fi
  for attempt in $(seq 1 30); do
    rosnode list 2>/dev/null | grep -Fxq /epgeneral_video_srt && break
    [[ "${attempt}" != 30 ]] || {
      echo "SRT video node did not become ready; log=${LOG_DIR}/video_srt.log" >&2
      [[ " ${started[*]} " != *" video_srt "* ]] || stop_process video_srt
      [[ " ${started[*]} " != *" camera "* ]] || stop_process camera
      return 1
    }
    sleep 1
  done

  if (("${#started[@]}" > 0)); then
    echo "STARTED ${started[*]}"
  else
    echo "ALREADY_RUNNING camera_external=${camera_external} video_external=${video_external}"
  fi
}

case "${ACTION}" in
  start)
    start_video
    ;;
  restart)
    stop_process video_srt
    stop_process camera
    start_video
    ;;
  stop)
    stop_process video_srt
    stop_process camera
    ;;
  status)
    camera_status=stopped
    video_status=stopped
    if rosnode list 2>/dev/null | grep -Fxq /camera/camera &&
        rostopic type "${COLOR_TOPIC}" >/dev/null 2>&1; then
      camera_status=running
    fi
    rosnode list 2>/dev/null | grep -Fxq /epgeneral_video_srt && video_status=running
    echo "camera=${camera_status} video_srt=${video_status}"
    [[ "${camera_status}" == running && "${video_status}" == running ]]
    ;;
  *)
    echo "usage: $0 {start|restart|stop|status}" >&2
    exit 2
    ;;
esac
