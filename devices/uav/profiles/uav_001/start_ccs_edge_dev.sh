#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_DIR="$SCRIPT_DIR"
if [[ ! -r "$PROFILE_DIR/scripts/supervisor.py" ]]; then
  PROFILE_DIR="$SCRIPT_DIR/deploy/uav_001"
fi
if [[ ! -r "$PROFILE_DIR/scripts/supervisor.py" ]]; then
  printf '[ERROR] UAV_001 supervisor is unavailable under: %s\n' "$SCRIPT_DIR" >&2
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
for setup in /opt/ros/noetic/setup.bash \
  /home/nrc/mavros_catkin_ws/devel/setup.bash \
  /home/nrc/ws_livox/devel/setup.bash \
  /home/nrc/catkin_ws/devel/setup.bash \
  /home/nrc/ccs_edge_ws/devel/setup.bash; do
  [[ -r "$setup" ]] || { printf '[ERROR] Workspace is not built: %s\n' "$setup" >&2; exit 1; }
  source "$setup" --extend
done
export ROS_MASTER_URI=http://127.0.0.1:11311
export ROS_IP=192.168.50.140
unset ROS_HOSTNAME
exec python3 "$PROFILE_DIR/scripts/supervisor.py" "$@"
