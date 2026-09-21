# 端侧使用手册

整理日期：2026-09-18；源码基线：CCS_dev dbe85904cdbae3d3b837f8816f29d1f030d7bd5a，配套 CCS 0.25.0。

以本仓库 README 和各机型部署指南为当前目录入口。配置无热重载，包内默认配置与设备运行目录配置必须区分。

<a id="documents-user-manual-md"></a>

<a id="documents-user-manual-md-端侧功能包使用手册"></a>
# 端侧功能包使用手册

配套 CCS 0.25.0 和 `epgeneral_task_control` 0.6.3，更新日期：2026-09-16。本手册面向部署和现场使用人员。参数定义见[接口参考](INTERFACE_REFERENCE.md#documents-interface-reference-md)，功能包和版本见[端侧 README](../README.md)。

新部署按[从零部署指南](USER_MANUAL.md#documents-deployment-guide-md)执行；填写 ROS 接口时逐项对照[配置话题清单](INTERFACE_REFERENCE.md#documents-config-topic-reference-md)。历史指南和日志统一在[设备 ID 索引](../README.md)，不把当时的运行状态当作本次实测。

<a id="documents-user-manual-md-1-选择设备与部署形式"></a>
## 1. 选择设备与部署形式

端侧 ZIP 是源码与部署资料集合，不是可在设备直接双击运行的安装器。Windows/Ubuntu 安装包用于地面站，不能代替 ROS 端侧构建。独立源码仓库从仓库根目录操作；主项目与 edge ZIP 从 edge_side_pkg 目录操作。

| profile | 示例 SSH 目标 | CCS 工作空间 | 操作入口 |
| --- | --- | --- | --- |
| go2_edu | nvidia@192.168.50.100 | /home/nvidia/ccs_edge_ws | 前台一键脚本 |
| go2_robot2 | unitree@192.168.50.111 | /home/unitree/ccs_edge_ws | 原生 Go2 前台一键脚本 |
| go2_robot3 | unitree@192.168.50.112 | /home/unitree/ccs_edge_ws | 原生 Go2 前台一键脚本 |
| scout_mini | nvidia@192.168.50.120 | /home/nvidia/ccs_edge_ws | 前台一键脚本 |
| wheeltec_r550p | nrc19@192.168.50.122 | /home/nrc19/ccs_edge_ws | 前台一键脚本 |
| ground_air_agv | bitcq@192.168.50.130 | /home/bitcq/ccs_edge_ws | 手动启动用户 systemd 服务 |

这些是仓库 profile 示例，现场 ID/IP、用户和路径不同时先修改配置，不能仅改 SSH 目标。legacy go2_edu 保持重定位禁用且脚本不启动任务；Go2 Robot2/Robot3 使用地面站 go2_native profile，根脚本确认真实禁用状态和输入新鲜度后启动任务协调器，建图与定位按需互斥运行。Ground-Air 启动地面任务协调器、适配器与急停桥接，导航和任务执行层按需启动。UGV_003 的 Wheeltec profile 启动 Gemini 336L/SRT、专用二维导航适配器和控制权协调器；Scout 仍使用其外部导航栈。

<a id="documents-user-manual-md-2-准备源码配置与依赖"></a>
## 2. 准备源码、配置与依赖

<a id="documents-user-manual-md-21-在指控端准备-staging"></a>
### 2.1 在指控端准备 staging

以下为 Bash 示例；先设置实际源码或已解压 edge ZIP 中的绝对路径。staging 是临时副本，不覆盖仓库 profile 原件。

~~~bash
EDGE_SRC=/path/to/CCS_EDGE
PROFILE=scout_mini
STAGING=$(mktemp -d)
python3 "$EDGE_SRC/scripts/prepare_profile.py" --profile "$PROFILE" --output "$STAGING"
~~~

发布归档有九包，普通设备选择七个公共包。Ground-Air 另加 EPGeneral_ground_air_control，需要外部 ground_air_msgs；Go2 Robot2/Robot3 另加 EPGeneral_go2_integration，需要原生 Go2 underlay。两类设备各构建八包，不应将全部设备适配包加入同一构建。默认配置加七个设备 profile 共八套，每套七份 YAML，共 56 份配置文件。deploy、documents 不进入 catkin src；设备脚本、launch 和系统配置按用途另行安装。

<a id="documents-user-manual-md-22-在设备准备-ros-依赖"></a>
### 2.2 在设备准备 ROS 依赖

使用 Ubuntu 20.04、ROS Noetic、系统 Python 3。以下为公共依赖补充，外部底盘、相机、Livox、算法和导航包按设备专项指南准备。

~~~bash
sudo apt update
sudo apt install python3-yaml python3-paho-mqtt python3-msgpack python3-numpy \
  python3-catkin-pkg python3-rospkg ros-noetic-mavros ros-noetic-mavros-extras \
  ros-noetic-cv-bridge ros-noetic-image-transport ros-noetic-sensor-msgs \
  ros-noetic-nav-msgs ros-noetic-geometry-msgs ros-noetic-diagnostic-msgs \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev gstreamer1.0-tools \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly gstreamer1.0-libav
~~~

先按[工作空间接口](INTERFACE_REFERENCE.md#documents-interface-reference-md)加载设备 underlay，再加载 CCS。Scout 顺序为 Noetic → RealSense → Scout navigation → livox_fastlio → CCS；Ground-Air 为 Noetic → 车辆 catkin_ws → CCS。不得将地面站的 Python 虚拟环境带入 ROS Noetic 构建。

<a id="documents-user-manual-md-23-安装和构建"></a>
### 2.3 安装和构建

通过 SSH/SCP/rsync 或其他现场文件传输方式，将 staging 的 src 下所选包放到设备 CCS 工作空间 src 中。已有同名包应先备份整个旧包，以免增量覆盖遗留已删除文件；不要覆盖外部算法工作空间。

设备上在正确 underlay 环境中执行，WORKSPACE 按所选设备设置：

~~~bash
WORKSPACE=/home/nvidia/ccs_edge_ws
mkdir -p "$WORKSPACE/src"
cd "$WORKSPACE"
rosdep install --from-paths src --ignore-src -r -y
catkin_make -j2 -DPYTHON_EXECUTABLE=/usr/bin/python3
source devel/setup.bash
rospack find epgeneral_device_config
rospack find epgeneral_task_control
rosmsg show epgeneral_task_control/TaskExecutionCommand
~~~

构建失败先检查缺少的 ROS 包是否来自 underlay，以及 rospack 的解析路径。Ground-Air 用 `rospack find ground_air_msgs` 检查消息包。源码中 Python 节点入口由 catkin 安装；ZIP 解压后的源文件可能没有执行权限，Ground-Air 启动预检还会检查源入口，按下节显式设置。不要混用 Python 2。

<a id="documents-user-manual-md-3-安装实际运行配置"></a>
## 3. 安装实际运行配置

<a id="documents-user-manual-md-31-两种入口"></a>
### 3.1 两种入口

| 使用方式 | 修改位置 | 启动方式 |
| --- | --- | --- |
| 单包 launch 默认值 | epgeneral_device_config/config | 不传配置路径时读取包内 YAML |
| 一键脚本 | 工作空间/config/profile | 脚本显式传入这些文件 |
| 单包调试指定文件 | 任意已核验的配置目录 | 显式传入两个配置路径，推荐沿用设备运行目录 |

若改了包内 YAML，但脚本仍读 config/profile，运行行为不会变化。仅 legacy go2_edu 会优先尝试脚本旁 config/device.yaml；Robot2/Robot3 默认直接读工作空间/config/go2_robot2 或 go2_robot3，显式设置 CCS_EDGE_PROFILE_CONFIG_DIR 可固定入口。

将所选 profile 的七份 YAML 传到设备运行目录。以已在设备临时目录取得 profile 文件为例：

~~~bash
PROFILE=scout_mini
WORKSPACE=/home/nvidia/ccs_edge_ws
PROFILE_SOURCE=/tmp/ccs-profile
install -d -m 0750 "$WORKSPACE/config/$PROFILE"
install -m 0640 "$PROFILE_SOURCE/config/"*.yaml "$WORKSPACE/config/$PROFILE/"
install -m 0750 "$PROFILE_SOURCE/start_ccs_edge_dev.sh" "$WORKSPACE/start_ccs_edge_dev.sh"
~~~

设备适配 launch 的安装位置以[专项指南](USER_MANUAL.md#documents-user-manual-md-9-%E8%AE%BE%E5%A4%87%E4%B8%93%E9%A1%B9%E6%93%8D%E4%BD%9C)为准。尤其 Scout 使用额外 base launch，Ground-Air 还需 CCS launch、局部 overrides 和用户服务，不能只复制 YAML 就启动。

<a id="documents-user-manual-md-原生-go2-首次安装补充"></a>
#### 原生 Go2 首次安装补充

Robot3 除八包和七份 YAML，还须安装 profile/scripts 下三个助手到工作空间/scripts，verify_ros_contract.py 用于隔离 ROS 契约测试；map_stream 包内须有 mapping_prerequisites_go2_robot3.launch。根脚本放工作空间根目录，LF 无 BOM 并可执行，所有间接建图 Shell 也要检查 LF。Noetic → go2_nav_ws → CCS 顺序和实体 src 必须成立。完整复制命令见[从零安装示例](USER_MANUAL.md#documents-deployment-guide-md-33-go2_3-%E9%A6%96%E6%AC%A1%E5%AE%89%E8%A3%85%E7%A4%BA%E4%BE%8B)。MAVROS 的消息/构建依赖不表示原生 Go2 必须运行飞控节点。

<a id="documents-user-manual-md-ground-air-首次安装补充"></a>
#### Ground-Air 首次安装补充

以下只适用于已经准备好车辆 underlay、完成八包构建的新 CCS 工作空间，以 bitcq 用户执行。PROFILE_SOURCE 必须包含完整的 deploy/ground_air_agv 目录内容，不能只上传 config。现有部署升级先按第 8 节备份并停止服务；不要用历史 deploy_stage_manager_update.sh 代替首次安装，它面向旧 underlay 阶段管理器且会启用服务。

~~~bash
WORKSPACE=/home/bitcq/ccs_edge_ws
PROFILE=ground_air_agv
PROFILE_SOURCE=/tmp/ccs-profile
source /opt/ros/noetic/setup.bash
source /home/bitcq/catkin_ws/devel/setup.bash --extend
source "$WORKSPACE/devel/setup.bash" --extend
CAR_BRINGUP=$(rospack find car_bringup)
test -r "$CAR_BRINGUP/launch/fastlio_pipeline.launch"
test -r "$CAR_BRINGUP/launch/manual_mapping.launch"
rospack find ground_air_msgs
install -d -m 0750 "$WORKSPACE/launch" "$WORKSPACE/overrides/car_bringup/launch" \
  "$WORKSPACE/run" "$WORKSPACE/log/ground_air_agv" \
  "$HOME/.ros/ccs_edge_dev_ground_air_agv/log" "$HOME/.config/systemd/user"
install -m 0644 "$PROFILE_SOURCE/launch/"*.launch "$WORKSPACE/launch/"
install -m 0644 "$PROFILE_SOURCE/overrides/car_bringup/package.xml" \
  "$WORKSPACE/overrides/car_bringup/package.xml"
install -m 0644 "$PROFILE_SOURCE/overrides/car_bringup/launch/"*.launch \
  "$WORKSPACE/overrides/car_bringup/launch/"
chmod 0755 "$WORKSPACE/src/EPGeneral_ground_air_control/scripts/"*.py \
  "$WORKSPACE/src/EPGeneral_relocalization/scripts/"*.py \
  "$WORKSPACE/src/EPGeneral_map_stream/scripts/"*.py \
  "$WORKSPACE/src/EPGeneral_map_stream/scripts/"*.sh
~~~

当前主脚本和阶段管理器仍通过 car_bringup 查找静态 TF 与建图入口，因此首次集成还要安装下面两个适配 launch 到车辆包。先确认 CAR_BRINGUP 是预期的 /home/bitcq/catkin_ws/src/car_bringup；已有同名文件必须备份后比较差异。这里不覆盖原 manual_mapping.launch，不复制旧 car_bringup_scripts 阶段管理器。

~~~bash
test "$CAR_BRINGUP" = /home/bitcq/catkin_ws/src/car_bringup
install -m 0644 "$PROFILE_SOURCE/launch/mapping_coordinate_transforms.launch" \
  "$PROFILE_SOURCE/launch/manual_mapping_control.launch" "$CAR_BRINGUP/launch/"
install -m 0644 "$PROFILE_SOURCE/ccs-edge-dev.service" \
  "$HOME/.config/systemd/user/ccs-edge-dev.service"
systemd-analyze --user verify "$HOME/.config/systemd/user/ccs-edge-dev.service"
systemctl --user daemon-reload
systemctl --user disable ccs-edge-dev.service
systemctl --user is-enabled ccs-edge-dev.service
~~~

最后一条输出应为 disabled，退出码非零是 systemctl 的正常语义。服务文件的 WorkingDirectory、ExecStart 和 StandardOutput/StandardError 都是 bitcq 的绝对路径；换用户或工作空间时，先编辑这些字段及脚本的 CCS_* 配置再执行 verify/daemon-reload。上述步骤不启动服务；完成配置、授时和外部接口核验后再按第 4.3 节手动启动。后续局部修复遵循专项指南的工作空间写入边界；这两个车辆适配 launch 的首次安装不能误作日常增量覆盖流程。

<a id="documents-user-manual-md-32-修改必检项"></a>
### 3.2 修改必检项

- device.yaml：设备唯一 ID 与自身 IP，和地面站设备表一致。
- epgeneral_mqtav.yaml：Broker 地址；UDP/map_stream/relocalization/task_control 的 network：上行目标与端口；不要将设备自身 IP 填成地面站 IP。
- 各包的 ROS topic/message_type/字段路径/frame 与真实外部包对应；descriptor 身份变更需同步地面站描述符。
- 建图外参必须来自设备标定，不能直接复制另一底盘的变换。
- 重定位 map_root/state_file、任务适配器及 UDP pgm_file 的对应路径保持一致。
- timesyncd-ccs.conf 与 CCS_NTP_SERVER 对齐。修改地面站地址时逐份检查 YAML 和脚本，不能仅设置一个环境变量。

修改前停止对应节点并备份实际运行配置：

~~~bash
CFG="$WORKSPACE/config/$PROFILE"
cp -a "$CFG" "$CFG.backup-$(date +%Y%m%d-%H%M%S)"
editor "$CFG/device.yaml"
editor "$CFG/epgeneral_mqtav.yaml"
~~~

将 editor 换成现场可用编辑器。YAML 使用空格缩进、真正的 bool/数字，字段约束逐项查接口参考。修改节点路径或配置后无需重新编译 Python 包，但修改 .msg/C++/catkin 清单后必须重新构建。

<a id="documents-user-manual-md-33-启动前校验"></a>
### 3.3 启动前校验

在 source CCS 后，使用真实加载器检查六类 Python 配置；此步骤不启动 ROS 节点或外部算法：

~~~bash
export CCS_CHECK_CONFIG="$CFG"
python3 - <<'PY'
import os
from pathlib import Path
from epgeneral_mqtav.config import load_config as mqtt
from epgeneral_udp_telemetry.config import load_config as telemetry
from epgeneral_map_stream.config import load_config as mapping
from epgeneral_relocalization.config import load_config as relocalization
from epgeneral_task_control.config import load_config as task
root = Path(os.environ["CCS_CHECK_CONFIG"])
for filename, loader in [
    ("epgeneral_mqtav.yaml", mqtt), ("udp_telemetry.yaml", telemetry),
    ("map_stream.yaml", mapping), ("relocalization.yaml", relocalization),
    ("task_control.yaml", task),
]:
    loader(str(root / filename), str(root / "device.yaml"))
    print("OK", filename)
PY
~~~

建图专有参数还在 prepare 的外部命令预检中验证。视频参数由 C++ 节点读取和检查，先执行 `gst-inspect-1.0 srtsink`、`gst-inspect-1.0 x264enc`，再按单包步骤启动验证。解析通过仅代表配置结构可读，不代表外部话题、地图、服务和 TF 已就绪。

<a id="documents-user-manual-md-4-授时网络及整机启停"></a>
## 4. 授时、网络及整机启停

<a id="documents-user-manual-md-41-授时与端口"></a>
### 4.1 授时与端口

按现场授时服务管理方式安装 profile 的 timesyncd 配置；使用本仓库 timesyncd 方案时：

~~~bash
sudo install -D -m 0644 "$PROFILE_SOURCE/config/timesyncd-ccs.conf" \
  /etc/systemd/timesyncd.conf.d/ccs.conf
sudo systemctl restart systemd-timesyncd
timedatectl timesync-status
timedatectl show -p NTPSynchronized
~~~

授时服务器应为地面站；执行 UTC 计划任务前系统时间应正确。GO2_3 根脚本只要求 SNTP 有效应答（--availability-only），不检测时间差、不设置时钟；任务配置的 utc_tolerance_seconds=2.0 保留。其他 profile 按各自授时预检策略判断，不能把 Robot3 可用性检查推广为已修改全部设备。

| 接收端 | 端口 |
| --- | --- |
| 地面站 | TCP 1883 MQTT；UDP 123 NTP；UDP 14560 遥测、14562 建图、14564 任务、14566 重定位 |
| 设备 | UDP 9000 SRT、14561 建图控制、14563 任务、14565 重定位；TCP 14600 建图下载 |
| ROS 通信 | ROS Master 及节点动态 TCPROS 端口，按部署网络放行 |
| 重定位地图下载 | 端侧访问地面站下发的 HTTP URL，地址和端口以地面站配置为准 |

通道运行于可信局域网；开放端口不等于部署认证或加密。不要将 UDP 控制和地图文件服务直接暴露到公网。

<a id="documents-user-manual-md-42-go2scoutwheeltec"></a>
### 4.2 Go2、Scout、Wheeltec

~~~bash
export CCS_EDGE_WORKSPACE="$WORKSPACE"
export CCS_EDGE_PROFILE_CONFIG_DIR="$WORKSPACE/config/$PROFILE"
"$WORKSPACE/start_ccs_edge_dev.sh"
~~~

保持前台终端；按 Ctrl+C 停止脚本管理的进程及由其自身创建的 ROS Master。已有 ROS Master 不应被当成本次新建进程清理。UGV_003 停止时通过控制权协调器停车并归还硬件遥控；Scout 对硬件话题等待实际消息，不能以 rostopic list 出现名称代替数据就绪。

| profile | 默认日志入口 |
| --- | --- |
| go2_edu | ~/.ros/ccs_edge_dev/log |
| go2_robot2 | /home/unitree/ccs_edge_ws/logs/managed |
| go2_robot3 | /home/unitree/.ros/ccs_edge_ws/latest → UTC启动时间_纳秒_PID 目录 |
| scout_mini | ~/.ros/ccs_edge_dev_scout_mini/log |
| wheeltec_r550p | ~/.ros/ccs_edge_dev_wheeltec_r550p/log |

legacy/Scout/Wheeltec 的 CCS_EDGE_STATE_DIR 可改变其脚本 PID/log 目录；Robot2 的 CCS_EDGE_STATE_DIR/CCS_EDGE_LOG_DIR 分别控制 PID 与组件日志；Robot3 使用 CCS_EDGE_LOG_ROOT，地图/任务/锁/急停文件不迁入日志目录。

<a id="documents-user-manual-md-ugv_003-gemini-336l-与控制权"></a>
#### UGV_003 Gemini 336L 与控制权

UGV_003 默认启动 Gemini 336L 和 SRT；需要只启动基础服务时设置 `CCS_ENABLE_VIDEO=0`。视频失败不会结束 MQTT、遥测、建图、重定位或任务服务，可独立检查和恢复：

~~~bash
cd /home/nrc19/ccs_edge_ws
./manage_ccs_video.sh status
./manage_ccs_video.sh restart
rostopic echo -n 1 /camera/color/image_raw/header
~~~

相机日志为 `~/.ros/ccs_edge_dev_wheeltec_r550p/log/camera.log`，SRT 日志为同目录 `video_srt.log`。视频输出固定为 640×360@30、2500 kbps、UDP 9000；重复启动复用外部相机/视频节点，不创建第二实例。

基础栈启动后 `/wheeltec_control/enabled` 和 `/wheeltec_robot/control_enabled` 应为 false，此时底盘驱动继续读取 `/odom`、`/imu` 和 `/PowerVoltage`，但不周期写入串口速度。任务执行前协调器用 `/fastlio_odom` 检查定位位姿和新鲜度；move_base/TEB 单独用 `/odom` 估计轮式底盘速度。协调器清除旧指令后依次取得驱动控制权并打开 `/wheeltec_safety`；任务完成、取消或卸载先停车再归还硬件遥控。任务期间 10 Hz 心跳超过 0.5 秒未更新会锁定停车，必须排查原因并人工复位，不能直接调用驱动使能绕过协调器。

<a id="documents-user-manual-md-ugv_003-振荡与人工急停复位"></a>
#### UGV_003 振荡与人工急停复位

`Robot is oscillating` 表示 move_base 在振荡超时内没有取得足够位移。0.6.1 修复了 UGV_003 将 `/fastlio_odom` 误作规划器速度里程计，以及 TEB `max_vel_x_backwards=0` 与 `penalty_epsilon=0.05` 的非法约束组合。0.6.2 的受控探针确认高频点云和代价地图会连续作废旧安全快照；安全门随后串行化完整检查和发布，并用 0.02 m/s 死区吸收实测最大 `-0.0067 m/s` 的 TEB 求解漂移。

快照问题消除后，第二次探针在速度真正到达驱动前触发 `obstacle_in_costmap_stop_region`。现场网格的值 99 已是 move_base 膨胀后的内切区，旧安全门又按完整车体扫掠；唯一值 100 单元的 5 cm 方格与实测车体边缘相交。安全门 0.1.2 只检查源致命值 100，并仅过滤与当前车体相交的已知致命单元；未知单元和两路实时点云仍保持阻断。任务控制 0.6.3 在底盘仍为手动状态时先调用 `/move_base/clear_costmaps`，等待 0.30 秒并重新校验定位和停用状态，任一步失败都不会使能底盘或发送目标。

先做只读检查，不发送目标或非零速度：

~~~bash
source /opt/ros/noetic/setup.bash
source /home/nrc19/livox_fastlio/devel/setup.bash --extend
source /home/nrc19/ccs_edge_ws/devel/setup.bash --extend
rostopic hz /fastlio_odom
rostopic hz /odom
rostopic info /nav_cmd_vel
rostopic info /wheeltec_driver/cmd_vel
rosservice info /move_base/clear_costmaps
rosparam get /move_base/TebLocalPlannerROS/max_vel_x_backwards
rosparam get /wheeltec_safety/allow_reverse
rosparam get /wheeltec_safety/linear_deadband
timeout 3 rostopic echo /wheeltec_safety/status
tail -n 120 /home/nrc19/.ros/ccs_edge_dev_wheeltec_r550p/log/task_control.log
~~~

预期两个 odom 都持续更新，`/nav_cmd_vel` 由 move_base 发布并由 `/wheeltec_safety` 订阅，安全门再发布到 `/wheeltec_driver/cmd_vel`；`/move_base/clear_costmaps` 类型为 `std_srvs/Empty`。TEB 后退边界为 `0.10`，安全门倒车开关为 `false`、线速度死区为 `0.02`、costmap 致命阈值为 `100`。有活动目标和新鲜计划时诊断应稳定进入 `PASS: healthy`。导航子进程日志位于 `/home/nrc19/.ros/ccs_edge_dev_wheeltec_r550p/log/navigation/`。若任一项不符，恢复 0.6.3 配置和安全门 0.1.2 后重启并重新定位，再按授权执行短距任务验收。

0.6.1 中规划失败、action ABORTED/拒绝/抢占及航点超时会正常停车、停用并归还硬件遥控，不再写入急停锁存；直接修复路径或环境后重新下发任务。显式急停、控制或定位失效、导航进程退出以及无法确认停车/停用仍会锁存。升级前由振荡误分类产生的旧锁存不会自动清除；确认没有准备或执行线程，且下列两个状态均持续为 false 后，操作人员调用一次复位服务：

~~~bash
rostopic echo -n 1 /wheeltec_control/enabled
rostopic echo -n 1 /wheeltec_robot/control_enabled
rosservice type /epgeneral_navigation_task_adapter/reset_emergency_stop
# 仅两个状态均为 false 时执行，预期类型 std_srvs/Trigger：
rosservice call /epgeneral_navigation_task_adapter/reset_emergency_stop "{}"
rostopic echo -n 1 /wheeltec_control/enabled
rostopic echo -n 1 /wheeltec_robot/control_enabled
~~~

必须看到 `success: true`，并再次确认两个状态仍为 false。复位只清除任务急停并复位控制链，不会使能底盘，也不会自动重跑旧任务。失败时保留服务响应及 task_control/navigation 日志继续排查；禁止删除 `task_emergency_stop.json`、直接调用 `/wheeltec_robot/set_autonomous` 或以重启绕过锁存。

<a id="documents-user-manual-md-go2_2-相机与急停增量"></a>
#### GO2_2 相机与急停增量

2026-09-11 的修复已安装到 QRD_002（192.168.50.111）。首次安装须同步 profile/scripts 中的 ccs_sntp_sync.py、ccs_ros_readiness.py 到工作空间/scripts。相机默认自动选择，CCS_D435_SERIAL 可原样指定实际序列号，不传 device_type；USB3 profile 保持 RGB 640×480@30，深度/红外/相机 IMU/TF 关闭。只有两帧以上、时间戳递增且年龄不超过3秒才显示相机就绪，最多等待30秒，之后才启动 SRT；失败查看 /home/unitree/ccs_edge_ws/logs/managed/camera.log。

正常启动的输入/disabled 门控在任务消费之前；自有 roscore/roslaunch 使用独立会话，退出先停任务，再确认底盘停用，最后停自建 master。日志仍为工作空间/logs/managed（新增 startup.log），SNTP 仍按 Robot2 原有时差策略检查。此处未同步 Robot3 的按次日志目录或 MQTT connection。

2026-09-11 按当时授权保留原生导航，仅安装、只读预检和隔离测试，未做生产复位；该历史边界见[当天记录](devices/go2/DEPLOYMENT_RECORD.md#deploy-records-qrd-002-deployment-md-camera-emergency-20260911)。2026-09-12 已按新授权完成两台退出竞态修复、服务复位及受控重启，联合 prepare/chunk/commit 通过，底盘持续 disabled。重启后定位 standby，导航准备反馈 LOCALIZATION_UNAVAILABLE；本轮未执行运动，正式执行前仍须完成定位。见 [QRD_002 最新记录](devices/go2/DEPLOYMENT_RECORD.md#deploy-records-qrd-002-deployment-md-joint-shutdown-20260912)、[QRD_003 最新记录](devices/go2/DEPLOYMENT_RECORD.md#deploy-records-qrd-003-deployment-md-joint-shutdown-20260912)。本轮 PR 审查随后修复普通卸载后新 PREPARE 的恢复，真实 close 或 ROS 退出仍阻止新任务；该后续修复只完成本地测试，尚未部署。重启或新任务不会清除锁存。

<a id="documents-user-manual-md-go2_3-预检相机与退出"></a>
#### GO2_3 预检、相机与退出

~~~bash
cd /home/unitree/ccs_edge_ws
./start_ccs_edge_dev.sh --check
./start_ccs_edge_dev.sh
# 多相机时先确认真实序列号，再选择：
# CCS_D435_SERIAL=339222070647 ./start_ccs_edge_dev.sh
~~~

--check 只读，不启停节点、不设时钟、不创建本次目录或更新 latest。正常启动先取得工作空间锁，再创建日志目录；重复启动失败不改变已运行实例的 latest。相机默认自动选择，不传 device_type，可选 serial_no 原样传入，不加下划线。RGB 640×480@15，关闭深度/红外/相机IMU/TF。节点注册后最多等30秒，至少两帧递增且年龄≤3秒才输出 camera is ready，SRT 在其后启动；缺图像返回非零并安全清理。

成功预检和最终启动分别只输出以下汇总，组件就绪统一 `[OK] <name> is ready.`，失败使用 [ERROR] 并回放直接原因：

~~~text
[OK] GO2 configuration, time, persistent and on-demand launch files passed preflight; no nodes were started.
[OK] GO2 CCS services are running. Mapping/localization remain task-managed. Ctrl+C stops only this workflow.
~~~

本次目录含 startup.log、camera.log、control.log、runtime_monitor.log、ros/、mqtav/、relocalization/、mapping/map_stream.log 及 `mapping/sessions/<session>/` 算法日志。ROS_LOG_DIR 由根脚本传给自身常驻和按需节点。排障可在另一个终端执行：

~~~bash
RUN_LOG=$(readlink -f /home/unitree/.ros/ccs_edge_ws/latest)
tail -n 80 "$RUN_LOG/startup.log"
tail -n 80 "$RUN_LOG/camera.log"
~~~

根脚本通过独立会话隔离终端 Ctrl+C。停止时先关任务消费/适配器，再确认底盘停用，逆序停止组件，最后仅停止自建 master。需要远程 TERM 时先由 ps/工作空间锁与日志确认根脚本 PID，再 kill -TERM 该 PID，不给整个 ROS 进程组发信号。退出码130/143是信号状态，不自动代表安全清理失败；检查日志、节点归属和新鲜 disabled 诊断。真实停用失败仍锁存，不通过删文件恢复。

<a id="documents-user-manual-md-43-ground-air"></a>
### 4.3 Ground-Air

完成专项部署后，以 bitcq 用户手动操作：

~~~bash
systemctl --user start ccs-edge-dev.service
systemctl --user status ccs-edge-dev.service --no-pager
journalctl --user -u ccs-edge-dev.service -n 80 --no-pager
systemctl --user stop ccs-edge-dev.service
systemctl --user is-enabled ccs-edge-dev.service
~~~

最后一项预期 disabled。不要执行 enable，也不要与前台一键脚本、旧整栈 launch 并行运行。组件日志在 /home/bitcq/ccs_edge_ws/log/ground_air_agv；服务 stdout/stderr 配置写入 ~/.ros/ccs_edge_dev_ground_air_agv/log/supervisor.log，journal 主要用于服务生命周期。

<a id="documents-user-manual-md-5-九个功能包的独立使用"></a>
## 5. 九个功能包的独立使用

以下单包命令仅在对应一键节点已停止、ROS 环境已 source、CFG 指向实际配置目录时执行。每个 roslaunch 保持前台，Ctrl+C 停止；无需同时启动所有包。

<a id="documents-user-manual-md-51-epgeneral_device_config"></a>
### 5.1 epgeneral_device_config

配置资源包没有节点。用 `rospack find epgeneral_device_config` 定位，检查七份 YAML。改变设备 ID 后同步地面站登记并重启 MQTT、UDP、视频、建图、重定位及任务相关节点，旧会话不能继续沿用。

<a id="documents-user-manual-md-52-epgeneral_mqtav"></a>
### 5.2 epgeneral_mqtav

~~~bash
roslaunch epgeneral_mqtav epgeneral_mqtav.launch \
  device_config_file:="$CFG/device.yaml" config_file:="$CFG/epgeneral_mqtav.yaml"
~~~

先用 rostopic type/echo 检查配置的状态和电池源，再在地面站确认 presence、heartbeat、status。正常退出发布 offline；异常断线由 MQTT Last Will/心跳超时体现。在线不代表 UDP/视频/任务可用。没有电池源时保持 unknown，诊断网络时检查 Broker TCP 1883 与节点耐久日志。

<a id="documents-user-manual-md-53-epgeneral_udp_telemetry"></a>
### 5.3 epgeneral_udp_telemetry

~~~bash
roslaunch epgeneral_udp_telemetry epgeneral_udp_telemetry.launch \
  device_config_file:="$CFG/device.yaml" telemetry_config_file:="$CFG/udp_telemetry.yaml" \
  destination_host:=192.168.50.101 destination_port:=14560
rostopic echo -n 1 /epgeneral_udp_telemetry/diagnostics
~~~

把 destination_host 替换为实际地面站地址；该 launch 默认会覆盖 YAML，不传参会使用 192.168.151.100。诊断命令在另一个已 source 终端执行。profile 可能重命名诊断话题，应使用实际 launch 配置。accepted_count 应随有效源增长；descriptor hash 不匹配、未知设备、NaN/Inf、旧 session 或乱序需结合地面站日志排查。

<a id="documents-user-manual-md-54-epgeneral_video_srt"></a>
### 5.4 epgeneral_video_srt

先启动外部相机驱动并确认 Image/CompressedImage 有帧：

~~~bash
roslaunch epgeneral_video_srt epgeneral_video_srt.launch \
  device_config_file:="$CFG/device.yaml" video_config_file:="$CFG/video.yaml"
~~~

在地面站设备详情打开视频；或从有 SRT 支持的客户端测试：

~~~bash
ffplay 'srt://192.168.50.120:9000?mode=caller&transtype=live&latency=120000'
~~~

使用实际设备 IP。视频无画面时依次检查输入类型和帧、GStreamer 插件、UDP 9000、防火墙及 Caller 参数。UGV_003 使用 `/camera/color/image_raw` 和 `manage_ccs_video.sh`；因 Gemini 336L 倒置安装，该 profile 设置 `rotation_degrees: 180`，只旋转 SRT 输出。`video.yaml.enabled` 是说明字段，一键脚本是否启动视频由 `CCS_ENABLE_VIDEO` 控制。

<a id="documents-user-manual-md-55-epgeneral_map_stream"></a>
### 5.5 epgeneral_map_stream

~~~bash
roslaunch epgeneral_map_stream epgeneral_map_stream.launch \
  device_config_file:="$CFG/device.yaml" mapping_config_file:="$CFG/map_stream.yaml"
~~~

在地面站地图工作台选择设备并准备建图，等待 prepare 成功后启动；联合建图选择主设备与参与设备，检查各设备预览 frame 一致。准备会检查输入和外部工具，但不应抢占 Ground-Air 阶段服务。

结束时用“停止并保存”完成后端保存/转换并取得成果，等待 PCD/PGM/YAML 和 manifest 可下载后再开始下一会话；abort 用于放弃当前会话，不保证生成成果。Go2 保存 accumulator，Scout/Wheeltec 执行 finalize，Ground-Air 通过 stage/save 服务，不能把 Go2 保存命令通用于其他设备。HTTP 14600 下载失败应检查设备身份地址、令牌期限、文件大小和目录剩余空间。

<a id="documents-user-manual-md-56-epgeneral_relocalization"></a>
### 5.6 epgeneral_relocalization

~~~bash
roslaunch epgeneral_relocalization epgeneral_relocalization.launch \
  device_config_file:="$CFG/device.yaml" config_file:="$CFG/relocalization.yaml"
~~~

地面站选择地图和设备，下发地图，等待校验及定位栈启动；在地图中选择初始位姿后等待结果。核对 map/odom TF、状态 JSON 和地面站地图绑定。重复定位按地面站替换流程清理旧进程和绑定，不手工伪造 localized。仅 legacy go2_edu 的 enabled=false；Robot2/Robot3 启用重定位，依次启动 navigation_guard 与 navigation，并用新鲜 /localization/ok 和 TF 判断结果。

Ground-Air 第一个有效 TF 即成功，之后 1 Hz 更新或缓存重发，后续持久化限频 30 秒；设备静止时重复结果是正常行为。Scout/Wheeltec 要满足稳定样本窗口。停止时先结束当前定位流程再关闭协调器，避免将残存算法节点误当作下次会话。

<a id="documents-user-manual-md-57-epgeneral_task_control"></a>
### 5.7 epgeneral_task_control

通用协调器用于接入自定义执行器：

~~~bash
roslaunch epgeneral_task_control epgeneral_task_control.launch \
  device_config_file:="$CFG/device.yaml" task_config_file:="$CFG/task_control.yaml"
~~~

Scout 使用 `scout_task_control.launch`，原生 Go2 使用 `navigation_task_control.launch`，UGV_003 使用 `wheeltec_task_control.launch`；这些入口已包含协调器，不能再重复启动通用入口。Wheeltec 入口同时启动 `/wheeltec_control`，导航只需地图三件套中的 `map.yaml/map.pgm`，不要求 `terrain_2p5d.yaml`。自定义执行器需实现[消息契约](INTERFACE_REFERENCE.md#documents-interface-reference-md)。

操作顺序：完成实时重定位 → 地面站创建有效地图航点任务 → 下发并 commit → 等待准备完成/ready → 确认统一 UTC → 执行 → 查看真实反馈。任务 XML 被原子保存，任务目录和地图根目录应可写/可读。停止使用地面站任务停止命令；删除/卸载与常规停止不同，按协调器状态释放导航。适配器失联、位姿陈旧或反馈超时必须排查，不能跳过检查直接发 move_base 目标。

2026-09-12 后续用户已确认两台本轮修复的落地测试完成，来源与范围见 [QRD_002 现场确认](devices/go2/DEPLOYMENT_RECORD.md#deploy-records-qrd-002-deployment-md-field-confirmation-20260912)、[QRD_003 现场确认](devices/go2/DEPLOYMENT_RECORD.md#deploy-records-qrd-003-deployment-md-field-confirmation-20260912)。此前工具验收的 standby/disabled 仅代表当时状态；没有新实测时不推断实时运行状态或后续修订已部署。

<a id="documents-user-manual-md-go2-人工急停复位"></a>
#### Go2 人工急停复位

“下发成功”只说明轨迹已提交，仍需等待导航 ready。当前协调器在状态协商、prepare 和 commit 检查持久急停，传输中出现或损坏标记同样拒绝；适配器保留最终检查。EMERGENCY_STOP_LATCHED 为不可自动重试的准备失败，定位暂不可用等可恢复故障仍按配置重试。复位后重新下发，不自动执行旧任务。

联合下发在 prepare 阶段快速返回 EMERGENCY_STOP_LATCHED 时，先读取安全文件的 recorded_at 和 reason，对照该时间的退出日志；此拒绝分支不调用底盘控制服务，不能据此认定并发传输导致停用超时。升级代码后已有锁存仍需按下面的服务流程恢复。

下发排查程序应在实际 transfer_seconds 内连续传输；两台本次配置为10秒。超时后，相同 revision/CRC 的旧任务也可返回幂等 commit ACK；需要本轮 XML committed 日志与文件内容证明新传输完成。重启后 LOCALIZATION_UNAVAILABLE 表示定位尚未满足准备条件，应恢复定位，不要再次复位急停来绕过它。详见 [GO2 部署经验](devices/go2/DEPLOYMENT_GUIDE.md#documents-go2-deployment-lessons-md)。

先查本次 control/task_control/startup 日志及配置 adapter.emergency_stop_state_file，修复停用超时、master/底盘故障的根因。确认没有准备/执行工作线程或控制过渡、运动指令为零，且 disabled 诊断持续新鲜，再由操作人员调用一次：

~~~bash
source /opt/ros/noetic/setup.bash
source /home/unitree/go2_nav_ws/devel/setup.bash --extend
source /home/unitree/ccs_edge_ws/devel/setup.bash --extend
python3 /home/unitree/ccs_edge_ws/scripts/ccs_ros_readiness.py disabled --timeout 10 --max-age 3
rosservice type /epgeneral_navigation_task_adapter/reset_emergency_stop
# 仅上述条件均满足后执行，预期 std_srvs/Trigger：
rosservice call /epgeneral_navigation_task_adapter/reset_emergency_stop "{}"
python3 /home/unitree/ccs_edge_ws/scripts/ccs_ros_readiness.py disabled --timeout 10 --max-age 3
~~~

必须看到 success: true，并复核锁存解除且底盘仍 disabled；失败停止复位流程，保留响应诊断。复位服务只清锁，不使能。禁止直接删除/覆盖安全文件，禁止通过重启、新任务或手动 enable 绕过。以上也适用于安装 2026-09-11 增量后的 Robot2；仅运行原生导航、CCS 适配器尚未启动时不能执行复位。2026-09-11 的 Robot2 增量当时保留原生导航、未做生产复位；最新结果以按设备 ID 的后续记录为准。


<a id="documents-user-manual-md-58-epgeneral_ground_air_control"></a>
### 5.8 epgeneral_ground_air_control

仅用于 Ground-Air，常规启动由一键脚本启动 stage manager。单独排障时先停止一键服务，再在正确 underlay/overlay 环境中启动：

~~~bash
rosrun epgeneral_ground_air_control ground_air_stage_manager_node.py
~~~

另一个终端检查服务和 guard：

~~~bash
rosservice type /ground_air/system/set_stage
rosparam get /ground_air_stage_manager/ccs_session_guard_version
rosparam get /ground_air_stage_manager/external_tf_required
rostopic echo -n 1 /ground_air/system/stage
~~~

guard 应为 2，external_tf_required 为 1。此单节点命令不替代常驻静态 TF、驱动和外部算法；完整联调仍使用一键脚本。重定位控制 launch 的 map_id 必填，通过局部 car_bringup override 调用，通常由重定位包自动启动。不要手工争抢正在建图或定位的 stage；manager 依 caller/map_id 管理归属。

<a id="documents-user-manual-md-59-epgeneral_go2_integration"></a>
### 5.9 epgeneral_go2_integration

原生 Robot2/Robot3 的第八包，连接 go2_nav_ws 的建图/定位/导航。根脚本持有 Livox、SDK bridge 和相机，按需 launch 不重复启动它们。mapping_fast_lio.launch 与 navigation_guard.launch 共用 lock_file；重定位先取得 guard 再启动 navigation，任务 attach。bringup.launch 是显式组合入口，不具备根脚本全部预检/监控，不能并行运行。外参仍由原生工作空间提供，详见[包说明](../devices/go2/EPGeneral_go2_integration/README.md)。


<a id="documents-user-manual-md-6-日常验收"></a>
## 6. 日常验收

在已 source 的诊断终端检查：

~~~bash
rosnode list
rostopic hz /livox/imu
rostopic hz /livox/lidar
ss -lntup
timedatectl timesync-status
~~~

按实际 profile 替换话题；确认实际接收频率而非只有名称。地面站分别核对 MQTT 在线、UDP 数据更新、视频帧、地图成果和任务反馈。文件时间戳或端口监听不能替代端到端确认。

本次文档发行的自动测试不连接设备，也不代表完成 ROS 编译、真实相机或运动控制验收。现场验收应记录产品/包版本、profile、设备、日期、配置校验值及实际结果。

<a id="documents-user-manual-md-7-故障排查"></a>
## 7. 故障排查

| 现象 | 优先检查 | 处理 |
| --- | --- | --- |
| 修改 YAML 无效果 | 实际 launch/脚本路径和参数覆盖 | 修改真正的 config/profile，重启对应节点 |
| rospack 找不到包 | source 顺序、构建输出、包名大小写 | 重新构建并加载正确 overlay |
| Ground-Air 同名 car_bringup 报错 | 子进程 prepend/exclude | 恢复 profile 配套配置，勿全局屏蔽 underlay |
| 整机预检停止 | profile 的授时策略、实际消息与日志 | Robot3 查 SNTP 可用性，其任务仍检查 UTC；按直接原因修复 |
| MQTT 在线但遥测空白 | descriptor hash、diagnostics、IP/ID、字段映射 | 同步地面站定义，修复具体来源 |
| 建图 prepare 被拒绝 | 输入类型/frame/TF、外部 launch、guard、空间 | 按错误修复配置；不提前调用阶段服务绕过 |
| 地图预览漂移 | 点真实坐标、配对位姿、外参和 preview frame | 成对修改端侧与地面站帧契约 |
| mapping command 127 / bash\r | 所有直接/间接 Shell 的 CRLF、BOM、执行权限 | 只对 staging 文本转 LF，重新计算哈希并同步；执行 bash -n |
| generate_pgm 缺少 source PCD | accumulator 保存响应、本次 PCD 与 session 快照、export 路径 | 使用当前转换脚本发布快照再转 PGM；不造空文件或拿旧图冒充 |
| ARTIFACT_STORAGE_UNAVAILABLE | 成果或会话日志根目录权限/普通文件占位/磁盘 | 修复存储后重新 prepare，确认失败会话已释放 |
| /go2_sdk_bridge_real exited | 实际 PID/退出日志与 master 查询错误 | 当前监控重试查询；真实崩溃修复 DDS/驱动，不能屏蔽 |
| EMERGENCY_STOP_LATCHED | 持久标记、停用 RPC 与清理顺序 | 修复根因后按人工复位步骤，成功后重新下发 |
| D435i 找不到但原驱动可用 | 原相机占用、serial_no 下划线、device_type 大小写、camera.log | Robot2/Robot3 默认自动选择；以新鲜 RGB 帧确认，不凭节点注册；分别保持 30/15 FPS |

| 重定位一直等待 | map topic、initialpose 订阅者、TF、下载路径 | 核查外部定位栈和所选地图 |
| 任务不能 ready/执行 | localized 状态、PGM、导航 action、UTC | 先完成定位和导航准备 |
| UGV_003 等待 move_base 后退出 | navigation 日志中的退出码、map.yaml/map.pgm、专用 launch | 确认使用 wheeltec_ccs_2d_navigation.launch，不再要求 terrain_2p5d.yaml |
| UGV_003 报 Robot is oscillating | `/fastlio_odom` 与 `/odom` 新鲜度、TEB 参数、`/move_base/clear_costmaps`、速度链及 `/wheeltec_safety/status` | 使用 0.6.3/安全门 0.1.2；确认 TEB 后退界 0.10、死区 0.02、costmap 阈值 100，取得明确授权后再做受控短距验收 |
| UGV_003 硬件遥控不能后退/原地转向 | 两个 enabled 状态、驱动心跳、串口速度写入 | 空闲时应为手动状态；修复锁停原因后由操作员 reset，不直接强制 autonomous |
| 停止后节点仍在 | 是否属于外部 underlay 或其他会话 | 按所有权停止，不使用无差别 pkill |
| SRT 无画面 | 相机帧/类型、插件、端口、客户端支持 | 独立验证图像源与编码链路 |

<a id="documents-user-manual-md-8-升级与回滚"></a>
## 8. 升级与回滚

升级前结束建图/任务/定位会话，停止一键栈；备份所选源码包、实际运行 YAML、脚本/launch/override、任务目录和地图状态。记录当前包版本和配置校验值，保持备份在工作空间 src 外。

安装后 source、配置校验并运行受影响的增量测试；仅消息/C++/构建清单变更才重新构建。回滚先停止新栈，保留最新安全状态和诊断，恢复同批次代码/配置/适配文件及权限并核对原 SHA-256；按实际需要构建，再验证消息、TF 和平台绑定，不用旧安全备份覆盖新急停。Ground-Air 的建图帧配置需与地面站配套回滚；不要单独恢复一端。不要把旧 localized JSON 当作回滚后的实时定位，重新完成定位再运行任务。

<a id="documents-user-manual-md-9-设备专项操作"></a>
## 9. 设备专项操作

- [Go2 EDU](devices/go2/DEPLOYMENT_GUIDE.md#deploy-go2-edu-deployment-md)：算法 underlay、相机及时间同步。
- [Go2 Robot2](devices/go2/DEPLOYMENT_GUIDE.md#deploy-go2-robot2-deployment-md)：原生导航接口、受管启动、迁移与回滚。
- [Go2 Robot3](devices/go2/DEPLOYMENT_GUIDE.md#deploy-go2-robot3-deployment-md)：QRD_003 身份、USB2 RGB 参数、输入新鲜度和安全状态确认。
- [Scout Mini](devices/scout_mini/DEPLOYMENT_GUIDE.md#documents-scout-mini-deployment-md)：RealSense/navigation/Livox source 顺序、BMS、相机和导航适配。
- [Wheeltec R550P / UGV_003](devices/wheeltec_r550p/DEPLOYMENT_GUIDE.md#documents-wheeltec-r550p-deployment-md)：二维导航、底盘控制权、Gemini 336L、地图工具和回滚。
- [Ground-Air 基础](devices/ground_air_agv/DEPLOYMENT_GUIDE.md#documents-ground-air-agv-deployment-md)、[建图](devices/ground_air_agv/DEPLOYMENT_GUIDE.md#documents-ground-air-agv-mapping-deployment-md)、[重定位](devices/ground_air_agv/DEPLOYMENT_GUIDE.md#documents-ground-air-agv-relocalization-deployment-md)：用户服务、外部 TF owner、阶段互斥及 override 安装。

以上旧路径均跳转到[按设备 ID 合并的记录](../README.md)。日志保留原日期和版本，供追溯与回滚；当前操作以本手册和从零指南为准。发布安装和预发布验证范围见地面站发行说明。

<a id="documents-user-manual-md-ugv_004-wheeltech-v51"></a>
## UGV_004 WheelTech V5.1

在 `/home/nrc15/ccs_edge_ws` 运行 `./start_ccs_edge_dev.sh --check` 预检，去掉参数启动，Ctrl+C 有序停止。七包安装、视频禁用，算法按需启动；日志 `logs/<UTC时间_纳秒_PID>`，`logs/latest` 指向本次运行。地图下载、共享定位状态和任务目录均在 CCS 工作空间，原生地图工具写入 underlay/maps 中的新会话目录。二维兼容导航保留实时障碍检测，不依赖额外地形文件。验收与恢复见 [UGV_004](devices/wheeltec_r550p/DEPLOYMENT_RECORD.md#deploy-records-ugv-004-deployment-md)。

<a id="documents-deployment-guide-md"></a>

<a id="documents-deployment-guide-md-端侧从零部署指南"></a>
# 端侧从零部署指南

适用：CCS 0.24.0 当前源码；维护日期：2026-09-12。本指南用于没有前次聊天上下文的新部署。包版本见[总览](../README.md)，接口填写见[话题与服务清单](INTERFACE_REFERENCE.md#documents-config-topic-reference-md)和[完整参数参考](INTERFACE_REFERENCE.md#documents-interface-reference-md)，日常操作见[使用手册](USER_MANUAL.md#documents-user-manual-md)。

设备历史集中在 [deploy/records](../README.md)。历史 IP、标定、PID、哈希、告警及“最终运行”只代表当次事实。QRD_002/QRD_003 的适配器退出修复已于 2026-09-12 部署；QRD_003 的建图存储异常和重复启动锁修复仍只有本地验证。本轮 PR 审查新增的普通卸载后重新准备修复尚未部署，真实 close 或 ROS 退出仍阻止新任务。每次交付重新记录源码版本、工作树差异和端侧 SHA-256，不用较早记录证明后续修订已部署。

故障判断与复用规则见 [GO2 部署经验](devices/go2/DEPLOYMENT_GUIDE.md#documents-go2-deployment-lessons-md)。2026-09-12 用户已确认两台本轮修复的落地测试完成，具体范围按设备记录追加；该确认不改变尚未部署修订的状态。

<a id="documents-deployment-guide-md-1-明确部署对象"></a>
## 1. 明确部署对象

填写[部署请求模板](USER_MANUAL.md#deploy-edge-device-deployment-request-md)：设备 ID/显示名、账号/IP、平台地址、硬件、underlay/overlay、允许的验收范围。设备 ID 必须唯一，profile 是运行配置名称，二者不同。新设备另建 profile 和 `deploy/records/<设备ID>/DEPLOYMENT.md`，不覆盖旧设备。

| ID | profile | 已有端侧 | CCS 工作空间 | 原生 underlay |
| --- | --- | --- | --- | --- |
| QRD_001 | go2_edu | nvidia@192.168.50.100 | /home/nvidia/ccs_edge_ws | /home/nvidia/go2_mid360_nav/catkin_ws |
| QRD_002 | go2_robot2 | unitree@192.168.50.111 | /home/unitree/ccs_edge_ws | /home/unitree/go2_nav_ws |
| QRD_003 | go2_robot3 | unitree@192.168.50.112 | /home/unitree/ccs_edge_ws | /home/unitree/go2_nav_ws |
| UGV_001 | scout_mini | nvidia@192.168.50.120 | /home/nvidia/ccs_edge_ws | RealSense → Scout → livox_fastlio，见接口参考 |
| UGV_003 | wheeltec_r550p | nrc19@192.168.50.122 | /home/nrc19/ccs_edge_ws | /home/nrc19/livox_fastlio |
| UGV_004 | wheeltec_r550p_02 | nrc15@192.168.50.123 | /home/nrc15/ccs_edge_ws | /home/nrc15/livox_fastlio（V5.1） |
| AGV_001 | ground_air_agv | bitcq@192.168.50.130 | /home/bitcq/ccs_edge_ws | /home/bitcq/catkin_ws |

以上是实例，不是新设备默认值。原生 Go2 优先参考 go2_robot3 的修复，但其预检仍含 QRD_003、网卡、地址及路径约束；复制后不能只改 device.yaml 或 SSH 地址。不得复制其他设备的 mission、地图绑定、锁或急停状态。密码不写入仓库、记录或命令输出。

<a id="documents-deployment-guide-md-2-只读盘点与备份"></a>
## 2. 只读盘点与备份

确认 `uname -m`、`lsb_release -ds`、`python3 --version`、ROS 发行版、磁盘和各 setup.bash。Noetic 常用 Python 3.8，助手必须兼容。使用 `ip -br addr`、`ip route`、`lsusb -t`、`ps -eo pid,ppid,pgid,sid,args`、`ss -lntup` 记录网络、设备、进程和端口。仅在已有 master 时查询节点、话题、服务类型及任务/建图状态；不为盘点启动算法。

GO2_3 已验证 eth0/LAN 192.168.50.112、go2dds/DDS 192.168.123.18、eth1/雷达网口 192.168.1.50、MID360 192.168.1.119。新机器逐项实测；LAN 网卡不能代替 DDS 网卡。记录旧相机 launch 和 ROS master 的 PID/父进程/启动命令/工作目录、systemd 状态和持有者。

写入前建立 `CCS工作空间/backups/<设备ID>-<UTC时间>/`，保存将替换的文件、权限、相对路径和 SHA-256，以及启动命令、节点/PID、相关日志、地图状态和急停记录。注明原来不存在的文件。系统授时配置和首次写入 underlay 的适配 launch 也单独备份。

确认没有执行中任务、控制过渡、建图、地图生成或定位切换，再正常停止已识别的旧入口。相机原驱动可用但新入口打不开时先查旧驱动占用，只结束已确认的旧相机 launch。禁止 `pkill ros`、清空 `.ros` 或停止无归属 master。保留原生地图、标定和工作目录。

<a id="documents-deployment-guide-md-3-准备实体源码与运行文件"></a>
## 3. 准备实体源码与运行文件

<a id="documents-deployment-guide-md-31-选择包并冻结版本"></a>
### 3.1 选择包并冻结版本

发布包共九包。公共七包是 `EPGeneral_device_config`、`epgeneral_mqtav`、`EPGeneral_udp_telemetry`、`EPGeneral_video_srt`、`EPGeneral_map_stream`、`EPGeneral_relocalization`、`EPGeneral_task_control`。原生 Go2 加 `EPGeneral_go2_integration`；Ground-Air 加 `EPGeneral_ground_air_control`。每种设备构建七或八包，不混装全部专用适配包。

记录 `git rev-parse HEAD`、`git status --short` 和选定源码 SHA-256。比对修复时保留已有工作树修改。部署依据是实际文件，不只是版本号。deploy、documents、历史记录不放入 catkin src；CCS 包必须为实体目录，不依赖历史 vendor/bin 或指回旧 vendor 的链接。

<a id="documents-deployment-guide-md-32-lf权限与传输"></a>
### 3.2 LF、权限与传输

在独立 staging 整理文件和相对路径清单。Shell/Python 入口使用 UTF-8 无 BOM、LF，检查所有间接调用的脚本。CRLF 会把 shebang 解释成 `bash\r`，导致建图协商返回 127。只对本次 staging 文本规范化，之后重新计算哈希；不转换地图或二进制。Python 3.8 写 LF 使用 `open(path, 'w', encoding='utf-8', newline='\n')`，不能用该版本不支持的 `Path.write_text(newline=...)`。

传输后校验 SHA-256、恢复可执行位，用目标 Linux 的 `bash -n` 检查受影响 Shell。Windows 使用明确的 Git Bash 或目标 Linux；不可把未安装发行版的 WSL 当成验证通过。Python、YAML、launch 分别做语法和加载器检查。

<a id="documents-deployment-guide-md-33-go2_3-首次安装示例"></a>
### 3.3 GO2_3 首次安装示例

假定 unitree 用户已收到核验过的 `/tmp/ccs-stage`（src 下的八包与完整 deploy/go2_robot3），并完成备份与空闲确认。更换设备要先改独立 profile、脚本、预检和 launch，再调整下列路径。

~~~bash
WORKSPACE=/home/unitree/ccs_edge_ws
STAGE=/tmp/ccs-stage
STAGE_SRC="$STAGE/src"
PROFILE=go2_robot3
PROFILE_SOURCE="$STAGE/deploy/$PROFILE"
install -d -m 0750 "$WORKSPACE/src" "$WORKSPACE/scripts" \
  "$WORKSPACE/config/$PROFILE" "$WORKSPACE/docs/$PROFILE" \
  "$WORKSPACE/run/state" "$WORKSPACE/run/map/current" "$WORKSPACE/run/map/export" \
  "$WORKSPACE/maps/download" "$WORKSPACE/maps/sessions" "$WORKSPACE/maps/archive" \
  "$WORKSPACE/mission"
for pkg in EPGeneral_device_config epgeneral_mqtav EPGeneral_udp_telemetry \
  EPGeneral_video_srt EPGeneral_map_stream EPGeneral_relocalization \
  EPGeneral_task_control EPGeneral_go2_integration; do
  test -d "$STAGE_SRC/$pkg" && test ! -L "$STAGE_SRC/$pkg" || exit 1
  test ! -e "$WORKSPACE/src/$pkg" || { echo "Back up and reconcile existing $pkg first"; exit 1; }
  cp -a "$STAGE_SRC/$pkg" "$WORKSPACE/src/$pkg" || exit 1
done
install -m 0640 "$PROFILE_SOURCE/config/"*.yaml "$WORKSPACE/config/$PROFILE/"
install -m 0750 "$PROFILE_SOURCE/start_ccs_edge_dev.sh" "$WORKSPACE/start_ccs_edge_dev.sh"
install -m 0750 "$PROFILE_SOURCE/scripts/"*.py "$WORKSPACE/scripts/"
install -m 0750 "$PROFILE_SOURCE/verify_ros_contract.py" "$WORKSPACE/scripts/"
test -r "$WORKSPACE/src/EPGeneral_map_stream/launch/mapping_prerequisites_go2_robot3.launch"
find "$WORKSPACE/src" -type f \( -path '*/scripts/*.py' -o -path '*/scripts/*.sh' \) -exec chmod 0755 {} +
~~~

prerequisites launch 已随 map_stream 包提供，不可漏装。外参指向本机 `/home/unitree/go2_nav_ws/src/go2_core/config/extrinsics.yaml`。根脚本依赖 ccs_go2_preflight.py、ccs_ros_readiness.py 和 ccs_sntp_sync.py，仅复制根脚本和 YAML 不能启动。

其他设备：Scout 两个适配 launch、Wheeltec/legacy Go2 bringup 装入工作空间 launch/。Ground-Air 的 launch/、overrides/car_bringup、用户 service 和两个首次写入 car_bringup 的 launch 按[手册首次安装](USER_MANUAL.md#documents-user-manual-md-ground-air-%E9%A6%96%E6%AC%A1%E5%AE%89%E8%A3%85%E8%A1%A5%E5%85%85)操作，保持 service disabled。Robot2 须把 profile/scripts/ccs_sntp_sync.py 和 ccs_ros_readiness.py 一起安装到工作空间/scripts 并赋予执行权限；2026-09-11 已同步相机独立就绪、独立进程会话及任务急停恢复代码，帧率仍为 30，授时和日志保持该 profile 原有策略。

<a id="documents-deployment-guide-md-34-依赖与构建"></a>
### 3.4 依赖与构建

先 source Noetic，再加载原生 underlay，最后加载已有 CCS overlay（--extend）；全新工作空间尚无 CCS setup，不能提前 source。source ROS 前不要启用 set -u。按[手册依赖](USER_MANUAL.md#documents-user-manual-md-22-%E5%9C%A8%E8%AE%BE%E5%A4%87%E5%87%86%E5%A4%87-ros-%E4%BE%9D%E8%B5%96)补实际缺项，尤其系统 Python 的 yaml、msgpack、paho-mqtt。MAVROS 消息/构建依赖不表示每种底盘都要启动飞控节点。

~~~bash
source /opt/ros/noetic/setup.bash
source /home/unitree/go2_nav_ws/devel/setup.bash --extend
cd /home/unitree/ccs_edge_ws
rosdep install --from-paths src --ignore-src -r -y
catkin_make -j2 -DPYTHON_EXECUTABLE=/usr/bin/python3
source devel/setup.bash --extend
rospack find epgeneral_go2_integration
rospack find epgeneral_task_control
rosmsg show epgeneral_task_control/TaskExecutionCommand
~~~

ARM 控制并行度。核对所有 CCS 包 rospack find/readlink -f 都在本工作空间实体 src；外部依赖仍在 underlay。Python/配置/文档增量无须 catkin 重建；改消息、C++ 或构建清单时执行相应构建。

<a id="documents-deployment-guide-md-4-填写七份-config"></a>
## 4. 填写七份 config

按[接口清单](INTERFACE_REFERENCE.md#documents-config-topic-reference-md)填 topic、ROS 类型、字段、方向和启用阶段，再用[参数表](INTERFACE_REFERENCE.md#documents-interface-reference-md)校验。实际运行配置通常在工作空间/config/profile，不是包内示例；配置无热重载。

| 文件 | 必须核对 |
| --- | --- |
| device.yaml | 唯一 ID、端侧 IP；平台同 ID 新记录，初始地图绑定为空 |
| epgeneral_mqtav.yaml | Broker、状态/连接/电池/任务来源；QRD_003 周期 low_state 判断连接，锁存 Bool.data 表示 armed |
| udp_telemetry.yaml | 正式 name/display_name/type/level 与平台严格哈希一致；source 真实类型/字段；pgm_file 是文件接口 |
| video.yaml | 驱动实际 topic/type、分辨率/帧率、SRT 端口/码率；enabled 元数据不控制节点启停 |
| map_stream.yaml | 原始输入与预览区分；backend、标定、frame/coordinates、保存服务、PCD→PGM 路径、磁盘 |
| relocalization.yaml | stages、地图文件名/下载根目录、initialpose/map/健康话题、TF 和持久状态 |
| task_control.yaml | command/feedback/status、共享地图状态、action/odom/停车、reset/enable 类型、超时及急停文件 |

GO2_3 遥测为 `/go2/imu`、`/odom_nav`、`/go2/battery_state`，算法仍用 `/livox/imu`。算法位姿可能仅按需运行时存在，不为了空闲告警重复启动 FAST-LIO。当前原生 Go2 `ros.frames.map=lio_odom`、`ros.frames.preview=odom`、`artifacts.frame=odom`；平台外参按本设备 ID 配置，不能颠倒帧或只改 header 而不转换坐标。

原生 Go2 重定位拥有导航，任务适配器 attach，共享互斥锁。导航 reset 是 `std_srvs/Trigger`，必须检查 response.success；enable/disable 是 `std_srvs/SetBool`。不能用 Empty 代替 Trigger，也不能把服务应答等同于状态已改变。重启、新任务不清急停。

<a id="documents-deployment-guide-md-5-网络授时与只读预检"></a>
## 5. 网络、授时与只读预检

确认 MQTT TCP1883、遥测 UDP14560、建图 UDP14561/14562 + HTTP TCP14600、任务 UDP14563/14564、定位 UDP14565/14566、SRT UDP9000、NTP UDP123 及防火墙方向，以实际配置为准。平台重启保留原工作目录/数据目录，避免另一实例读取空设备表。

沿用现有授时服务。timesyncd 方案备份后将 profile 的 timesyncd-ccs.conf 安装到 `/etc/systemd/timesyncd.conf.d/ccs.conf`，确认服务工作，不并行另启竞争的守护程序。**GO2_3 启动只检查平台 SNTP 有效应答，不检测时差，也不设置时钟；任务计划 UTC 容差仍为 2 秒**。其他 profile 按各自脚本策略核对。

执行[配置加载器检查](USER_MANUAL.md#documents-user-manual-md-33-%E5%90%AF%E5%8A%A8%E5%89%8D%E6%A0%A1%E9%AA%8C)、gst-inspect-1.0 srtsink/x264enc 和 bash -n。GO2_3 执行 `./start_ccs_edge_dev.sh --check`，比较前后节点/PID 和 latest：不得启停节点、创建本次日志目录、更新 latest。无 master 时确认始终不存在，不为诊断补建 master。按需服务离线只核对类型类、MD5 和 launch 静态解析，不为了检查启动导航。

~~~text
[OK] GO2 configuration, time, persistent and on-demand launch files passed preflight; no nodes were started.
~~~

文案 time 表示当前可用性探测。预检助手中的旧错误文字 “two-second startup time check” 不意味着恢复了时差门控；根脚本 --availability-only 和任务配置各有作用。

<a id="documents-deployment-guide-md-6-首次启动与相机切换"></a>
## 6. 首次启动与相机切换

旧入口停止、底盘持续 disabled 后，从工作空间运行 `./start_ccs_edge_dev.sh`。默认手动启动，不增加自启。GO2_3 依次启动雷达、默认停用的底盘桥接、D435i、MQTT/UDP/SRT、建图/定位协调器、任务协调器及适配器。底盘和输入门控通过后才消费任务，算法按需启动。

D435i 默认单设备自动选择，不传 device_type。多相机时可 `CCS_D435_SERIAL=339222070647 ./start_ccs_edge_dev.sh`（该号是 QRD_003 历史值，现场先枚举），序列号原样传递，禁止添加 `_`。RGB 640×480@15，关闭深度、红外、gyro、accel、TF。注册后最多等30秒，两帧以上、时间戳递增、年龄≤3秒才输出 `[OK] camera is ready.`，随后 SRT 启动。注册不等于图像可用。

组件统一 `[OK] <name> is ready.`；成功底层检查静默，失败回放诊断并使用 `[ERROR]`，路径指向本次 camera.log 等文件。历史相机未连接时跳过验收不代表当前入口支持绕过相机。缺硬件明确标注未完成项，不能假报最终 ready。USB2.1 和既有 Right MIPI 告警保留，通过 RGB/SRT 实测判断，不宣称硬件已修复。

~~~text
[OK] GO2 CCS services are running. Mapping/localization remain task-managed. Ctrl+C stops only this workflow.
~~~

<a id="documents-deployment-guide-md-7-任务地图生成与退出约束"></a>
## 7. 任务、地图生成与退出约束

下发成功仅指轨迹提交，不是导航 ready 或执行成功。已知急停在协商、prepare、commit、适配器最终检查均拒绝；传输中新增或损坏标记同样拒绝。EMERGENCY_STOP_LATCHED 不再每5秒自动准备；定位暂不可用等可恢复错误仍可重试。修复根因后按[人工复位](USER_MANUAL.md#documents-user-manual-md-go2-%E4%BA%BA%E5%B7%A5%E6%80%A5%E5%81%9C%E5%A4%8D%E4%BD%8D)调用服务，不直接删除标记。复位不使能，不自动执行旧任务，恢复需重新下发。

原生 Go2 保存时先由 `/go2_map_accumulator/save_map` 保存本次新鲜非空的 accumulator PCD，从工作空间 `run/map/current/public_map.pcd` 校验并取得本次 session 快照，再由转换脚本把该快照原子复制到 `run/map/export/public_map.pcd`，然后生成 PGM/YAML。首次没有 export PCD 正常，不以旧文件或空文件冒充成功。失败检查 save 响应、PCD 时间/点数和转换日志。成果/日志目录创建失败返回 ARTIFACT_STORAGE_UNAVAILABLE 并释放会话，修复权限或普通文件占位后重新 prepare。

GO2_3 使用工作空间锁、独立 setsid 启动自身 roscore/roslaunch 并验证 PPID。Ctrl+C/TERM 依次停止任务消费/适配器、确认底盘停用、逆序停止组件、最后停止自建 master；不停止复用 master。130/143 为信号退出码，结合清理日志判断。整终端进程组同时结束曾导致 master 先退、disable RPC 超时并持久锁存，不能恢复该启动方式。

内部 shutdown-unload 可早于本进程 ROS 关闭信号；它与 close 使用同一个幂等收尾入口，覆盖 is_shutdown_requested() 回调阶段。仅收尾上下文允许复用新鲜 disabled，且必须同时排除未完成的控制过渡及 RPC；普通 STOP/UNLOAD 仍需服务响应和状态确认，真实失败继续锁存。一次收尾复用首次结果，不把失败改成成功。当前源码还区分可恢复卸载与永久 close：收尾结束后的新 PREPARE 重新校验安全/地图/定位后才可恢复，永久关闭仍拒绝新工作；该后续修订尚未部署。完整约束见[关闭经验](devices/go2/DEPLOYMENT_GUIDE.md#documents-go2-deployment-lessons-md-3-%E5%B9%82%E7%AD%89%E5%85%B3%E9%97%AD%E4%B8%8D%E8%83%BD%E5%8F%98%E6%88%90%E7%BB%95%E8%BF%87%E5%81%9C%E7%94%A8%E6%88%96%E6%B0%B8%E4%B9%85%E7%A6%81%E6%AD%A2%E5%A4%8D%E7%94%A8)。出现 `/go2_sdk_bridge_real exited` 先区分进程真实退出与 rosnode 查询失败；现监控重试 master 查询，不能屏蔽真实故障。

<a id="documents-deployment-guide-md-8-验收与回滚"></a>
## 8. 验收与回滚

首次做完整静态/依赖/包解析/协议检查，再在授权范围验证真机。修复仅跑受影响增量，不自动扩大为全量或重建。记录命令、通过数、未测项及原因；模拟通过不能写成实机通过。

| 阶段 | 记录内容 |
| --- | --- |
| 静态/接口 | 七 YAML、launch、LF/BOM/权限、实体包路径、ROS类型/MD5、硬件/网络、--check 无副作用 |
| 首次通信 | ≥60秒实际计数/帧率，平台正式解析并存储三级 UDP、心跳/MQTT、电池/IMU/雷达；sendto 不能替代平台证据 |
| 相机增量 | 按实际 profile 检查分辨率和帧率；Robot3 为30帧窗口640×480、约13–17Hz，Robot2 为640×480、约30Hz。新鲜帧先于 camera ready，SRT 节点存活且最终 ready；平台解码按本轮范围另验 |
| 急停/日志增量 | 跨≥3个原重试周期不刷错、锁存拒绝/人工复位约束、日志归档、有序退出再启动保持 disabled |
| 联合下发增量 | 在实际 transfer_seconds 内连续 prepare/chunk/commit；匹配新请求 ID、ACK/缺片、本轮 XML 落盘及原版本/CRC/航点；超时后的幂等 ACK 不作完整传输证据 |
| 真实任务 | 未授权使能/运动时保持 disabled，不发送目标、不做整轮建图/定位/导航；现场后续确认按来源另行追加，保留此前工具验收范围 |

失败先停止本次拥有的流程，保存日志及最新急停状态；按清单恢复匹配备份、权限、代码配置，校验原 SHA-256。禁止用备份覆盖更新的安全状态。恢复旧相机前确认新相机已退出，再用原命令/目录启动。归属或停用状态不明时保留诊断，不强行拉起旧整栈。

<a id="documents-deployment-guide-md-9-日志与交付"></a>
## 9. 日志与交付

GO2_3 正常启动在 `/home/unitree/.ros/ccs_edge_ws/<UTC启动时间_纳秒_PID>/` 建目录，latest 指向最近取得工作空间锁的启动。包含 startup.log、组件输出、runtime_monitor.log、ROS_LOG_DIR 的 ros/、mqtav/、relocalization/、mapping/。建图事件在 mapping/map_stream.log，FAST-LIO/PGM 在 `mapping/sessions/<session>/`。CCS_EDGE_LOG_ROOT 可改根目录；--check 不改变日志。其他 profile 保留原路径，见手册。

可选 launch log_dir 只改变建图日志，未传保留旧行为，仍校验会话路径边界。地图成果、任务、锁和急停继续在配置的工作空间路径，不随 latest 移动。

交付追加到 `deploy/records/<设备ID>/DEPLOYMENT.md`：时间/范围、commit与修改摘要、文件清单、前后哈希、备份/证据路径、命令、实测、告警/跳过项、启停和回滚。不覆盖历史日期或失败记录，不包含密码。

端侧文档保存一个完整的 edge 发布包解压树，例如 <工作空间>/docs/distribution/，保留 edge_side_pkg/ 与 docs/EDGE_DEVICE_INTERFACES.md 的相对层级。这样配置、脚本、接口和历史记录的链接均可离线打开；它只用于追溯，运行包仍解析到实体 src，禁止把这个文档归档重新当作 vendor underlay。

`<工作空间>/docs/<profile>/DEPLOYMENT.md` 改为短入口，链接到 ../distribution/edge_side_pkg/deploy/records/<设备ID>/DEPLOYMENT.md；完整记录只维护该一份。同步新记录时更新归档树中的对应文件，保留历史章节，并同时更新本次指南/接口/手册。若部署来自源码而非 edge ZIP，按同一层级整理并检查全部本地链接，不能只复制含相对链接的单个文档。清单记录文档及运行增量的实际哈希。

<a id="deploy-edge-device-deployment-request-md"></a>

<a id="deploy-edge-device-deployment-request-md-端侧设备部署请求模板"></a>
# 端侧设备部署请求模板

更新日期：2026-09-12；配套 CCS 0.25.0。将下表填写后作为一次部署请求使用，实际步骤执行[从零部署指南](USER_MANUAL.md#documents-deployment-guide-md)，接口按[配置话题与服务清单](INTERFACE_REFERENCE.md#documents-config-topic-reference-md)核验。本文件是模板，不代表已获准执行任何未填写的实机操作。

<a id="deploy-edge-device-deployment-request-md-本次设备与范围"></a>
## 本次设备与范围

| 项目 | 填写内容 |
| --- | --- |
| 设备 ID / 显示名 / 类型 | 唯一 ID、新增或已有；平台 profile 类型 |
| 端侧账号与 IP | 用户名、SSH 地址；密码通过本次会话安全提供，不写文档 |
| 指控平台 | IP、Broker/UDP/SRT/HTTP/NTP 端口、运行和数据目录 |
| OS / 架构 / ROS / Python | 实测版本 |
| CCS 工作空间 / profile | 新设备独立 profile，不覆盖其他设备 |
| 原生工作空间 | 所有 underlay 路径及 source 顺序 |
| 硬件与网络 | DDS/雷达/LAN 网卡与 IP，雷达地址，相机型号/序列号/USB链路 |
| 本轮功能 | MQTT、UDP、视频、建图、定位、任务及专用适配；缺硬件时明确未测项 |
| 已有进程与数据 | master、相机、原任务/地图/标定、启动方式和持有者 |
| 验收授权 | 仅静态、通信、相机、急停人工复位、整轮算法或运动；分别说明 |
| 交付与版本管理 | 本地源码/文档/端侧文件；是否提交、推送、PR由本次请求明确 |
| 维护窗口 | 停旧入口/重启平台的范围及可用时段 |
| 联合下发验收 | 实际 transfer_seconds、新请求 ID、完整分片及 XML 落盘证据；明确是否仅下发 |
| 现场确认来源 | 操作者确认日期、测试范围/结果及可提供日志；与工具实测分别记载 |

<a id="deploy-edge-device-deployment-request-md-实施与交付要求"></a>
## 实施与交付要求

1. 先只读盘点并核对原生接口，填写七份实际运行 YAML；设备 ID、消息类型/字段、TF/标定、网络、地图/任务/安全路径跨包一致。原生 Go2 还需核对脚本和预检中的固定值。
2. 写入前备份受影响文件、SHA-256、权限、进程/日志和安全证据。空闲后正常停止已识别入口，只传本轮文件；八包实体 src，无历史 vendor/bin 依赖。
3. 所有运行文本 LF，无 BOM，入口可执行；按变更范围做加载器/launch/语法检查和增量测试。首次安装才按依赖构建，Python/文档局部更新不默认重建。
4. 明确区分静态接口、模拟、实机通信与真实任务验收。未授权运动时持续 disabled，不发运动目标；不以通信成功代替地图/任务成功。
5. 日志和故障恢复按当前 profile；GO2_3 为启动时间分目录、独立会话清理、SNTP可用性、持久急停人工复位。保持原生地图和最新安全状态。
6. 记录追加到 deploy/records/<设备ID>/DEPLOYMENT.md，同步端侧 docs 与文件清单；列出启停、日志、备份、前后哈希、结果/跳过项、回滚。密码不入清单。

开始前阅读 [GO2 部署经验](devices/go2/DEPLOYMENT_GUIDE.md#documents-go2-deployment-lessons-md)，按现有授权执行；联合 prepare 拒绝先追溯锁存记录，闭锁仅通过服务恢复，超时后幂等 ACK 不作为完整传输验收。

原模板中 GO2_2 的历史需求、部署过程和版本操作已合入 [QRD_002 历史材料4](devices/go2/DEPLOYMENT_RECORD.md#deploy-records-qrd-002-deployment-md-source-4)，只作追溯，不自动成为新部署指令。全部设备见[索引](../README.md)。

<!-- 保留旧锚点；完整内容见上方历史材料。 -->
<a id="deploy-edge-device-deployment-request-md-1-目标参数与执行范围"></a>
<a id="deploy-edge-device-deployment-request-md-2-完成目标与适配原则"></a>
<a id="deploy-edge-device-deployment-request-md-3-阶段-a只读盘点与确定接口"></a>
<a id="deploy-edge-device-deployment-request-md-4-阶段-b本地实现与独立配置"></a>
<a id="deploy-edge-device-deployment-request-md-5-阶段-c通信建图和任务契约"></a>
<a id="deploy-edge-device-deployment-request-md-6-阶段-d备份迁移与必要构建"></a>
<a id="deploy-edge-device-deployment-request-md-7-阶段-e增量验收与统一切换"></a>
<a id="deploy-edge-device-deployment-request-md-8-阶段-f文档发布与最终交付"></a>
<a id="deploy-edge-device-deployment-request-md-ccs-端侧部署总结与可复用任务指令"></a>
<a id="deploy-edge-device-deployment-request-md-一本次-go2-部署总结"></a>
<a id="deploy-edge-device-deployment-request-md-二可直接发送的部署指令"></a>

## UAV_001

UAV 新部署采用独立八包工作空间，静态模式与飞行模式显式区分。详见 [UAV 部署说明](devices/uav/DEPLOYMENT_GUIDE.md) 和 [静态验收报告](devices/uav/DEPLOYMENT_REPORT.md)。本轮未进行实飞。

## 可选可信区域（重定位包 0.5.0）

[可信区域](INTERFACE_REFERENCE.md#可选可信区域接收) 说明接收开关、文件路径、XML 格式及协议。缺少区域文件不会改变原重定位流程。
