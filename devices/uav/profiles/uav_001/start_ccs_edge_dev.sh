#!/usr/bin/env bash
set -eo pipefail

WORKSPACE="${CCS_EDGE_WORKSPACE:-/home/nrc/ccs_edge_ws}"
PROFILE_CONFIG_DIR="${CCS_EDGE_PROFILE_CONFIG_DIR:-${WORKSPACE}/config/uav_001}"
PROFILE_LAUNCH_DIR="${CCS_EDGE_PROFILE_LAUNCH_DIR:-${WORKSPACE}/launch}"
PROFILE_SCRIPT_DIR="${CCS_EDGE_PROFILE_SCRIPT_DIR:-${WORKSPACE}/scripts}"
ROS_IP_VALUE="${CCS_ROS_IP:-192.168.50.140}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# A source-tree profile remains directly testable, while an installed profile
# always uses the same flat workspace layout as UGV_004.
if [[ "$SCRIPT_DIR" != "$WORKSPACE" ]]; then
  PROFILE_CONFIG_DIR="${CCS_EDGE_PROFILE_CONFIG_DIR:-${SCRIPT_DIR}/config}"
  PROFILE_LAUNCH_DIR="${CCS_EDGE_PROFILE_LAUNCH_DIR:-${SCRIPT_DIR}/launch}"
  PROFILE_SCRIPT_DIR="${CCS_EDGE_PROFILE_SCRIPT_DIR:-${SCRIPT_DIR}/scripts}"
fi
SUPERVISOR="${PROFILE_SCRIPT_DIR}/supervisor.py"
[[ -r "$SUPERVISOR" ]] || {
  printf '[ERROR] UAV_001 supervisor is unavailable: %s\n' "$SUPERVISOR" >&2
  exit 1
}

export PYTHONDONTWRITEBYTECODE=1
for setup in /opt/ros/noetic/setup.bash \
  /home/nrc/mavros_catkin_ws/devel/setup.bash \
  /home/nrc/ws_livox/devel/setup.bash \
  /home/nrc/catkin_ws/devel/setup.bash \
  "${WORKSPACE}/devel/setup.bash"; do
  [[ -r "$setup" ]] || { printf '[ERROR] Workspace is not built: %s\n' "$setup" >&2; exit 1; }
  source "$setup" --extend
done
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
export ROS_IP="$ROS_IP_VALUE"
unset ROS_HOSTNAME
export CCS_EDGE_WORKSPACE="$WORKSPACE"
export CCS_EDGE_PROFILE_CONFIG_DIR="$PROFILE_CONFIG_DIR"
export CCS_EDGE_PROFILE_LAUNCH_DIR="$PROFILE_LAUNCH_DIR"
exec python3 "$SUPERVISOR" "$@"
