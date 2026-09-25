# UAV_001 部署与启动指南

设备：UAV_001“金城涵道无人机”；端侧：`nrc@192.168.50.140`；工作空间：
`/home/nrc/ccs_edge_ws`；地面站：`192.168.50.101`。历史部署、实测结果和限制见
[部署记录](DEPLOYMENT_RECORD.md)。

## 当前工作空间结构

UAV_001 使用与 UGV_004 相同的平铺启动结构：

```text
/home/nrc/ccs_edge_ws/
├── start_ccs_edge_dev.sh
├── config/uav_001/*.yaml
├── launch/uav_001_bringup.launch
├── scripts/{supervisor,preflight,readiness,session_log}.py
├── src/
├── logs/
├── run/managed/
└── docs/uav_001/DEPLOYMENT.md
```

运行入口不读取 `deploy/uav_001`。七份 YAML 的唯一运行副本位于
`config/uav_001`；修改后必须停止并重新启动，不支持热更新。Catkin 源包仍位于
`src`，原生 MAVROS、Livox 和涵道无人机工作空间保持独立。

## 日常启动和停止

先启动地面站并确认 MQTT、NTP 和视频接收端可用，然后在端侧执行：

```bash
cd /home/nrc/ccs_edge_ws
./start_ccs_edge_dev.sh --check
./start_ccs_edge_dev.sh
# 前台按 Ctrl+C 有序停止
```

`--check`（兼容 `--preflight`）只检查环境、八个 ROS 包、profile 配置、launch、
GStreamer 插件和 UAV 建图集成，不创建 ROS master、运行日志或 PID 文件。无参数启动
是日常入口，等价于 `--mapping`：启动基础驱动、通信、视频和阶段管理，允许建图、地图
保存和重定位，但保持飞行任务及原生控制器禁用。

UAV 专属维护模式继续保留：

```bash
./start_ccs_edge_dev.sh --static   # 只观察，禁用建图、重定位和飞行执行
./start_ccs_edge_dev.sh --mapping  # 与无参数启动相同
./start_ccs_edge_dev.sh --flight   # 显式开放任务执行，仅限独立实飞验收后使用
```

正常停止使用启动终端的 `Ctrl+C`。`--stop` 仅供失去原终端时请求停止当前受管流程；飞行
模式下若控制器仍在空中或状态未知，停止会被拒绝并保留控制与定位。不得使用
`killall`、`pkill` 或直接删除 PID/闭锁文件绕过保护。

## 日志和状态

每次正常启动创建 `logs/<UTC时间_纳秒_PID>/`，`logs/latest` 指向最近一次运行。主要文件：

- `startup.log`：启动模式、阶段摘要和有序退出结果。
- `runtime_monitor.log`：节点检查重试和异常堆栈。
- `roscore.log`、`bringup.log`、`ros/`：本次自有 ROS 进程输出。
- `mqtav/`、`map_stream/`、`relocalization/`：公共包会话日志。

单实例锁、`startup.pid` 和 `startup.json` 位于 `run/managed`。地图、任务和安全状态分别
保存在 `maps`、`mission`、`run/state`，清理日志或回滚代码时不得覆盖这些状态。

## 配置、接口和就绪检查

七份运行配置位于 `config/uav_001`。基础接口为 MAVROS
`/mavros/state`、`/mavros/extended_state`、`/mavros/local_position/pose`、
`/mavros/local_position/velocity_local`、`/mavros/imu/data` 和
`/mavros/setpoint_position/local`；原生控制器仍是唯一位置目标发布者。

运行栈启动后可执行只读就绪检查：

```bash
source /home/nrc/ccs_edge_ws/devel/setup.bash --extend
python3 /home/nrc/ccs_edge_ws/scripts/readiness.py
```

检查失败必须排查真实 MAVROS、位姿、IMU、Livox 或视频输入，不得用虚拟数据补齐生产
话题。A8 输入为 `rtsp://192.168.144.25:8554/main.264`，SRT listener 使用端侧 UDP
9000；网络与视频参数以 `config/uav_001/video.yaml` 为准。

## 安装、升级和回滚

从仓库生成 profile staging：

```bash
python3 scripts/prepare_profile.py --profile uav_001 --output /tmp/uav001-stage
```

安装时将八个包放入 `src`，将 profile 的 `config`、`launch`、`scripts` 分别安装到上述
平铺目录，并把 profile 启动脚本安装到工作空间根目录。已有部署必须先确认功能栈停止；
升级前记录源码版本、部署清单和现场文件哈希，并备份所有待覆盖或删除文件。

构建顺序：

```bash
source /opt/ros/noetic/setup.bash
source /home/nrc/mavros_catkin_ws/devel/setup.bash --extend
source /home/nrc/ws_livox/devel/setup.bash --extend
source /home/nrc/catkin_ws/devel/setup.bash --extend
cd /home/nrc/ccs_edge_ws
catkin_make -j2 -l2 -DPYTHON_EXECUTABLE=/usr/bin/python3 -DCMAKE_BUILD_TYPE=Release
```

回滚只恢复本次备份的启动文件、配置和文档，随后重新构建并执行 `--check`。不得回滚
`maps`、`mission`、`run/state`、原生地图、最新急停或飞行故障状态。当前部署不设置
systemd 服务或开机自启。

## 启动、预检与停止

~~~bash
cd /home/nrc/ccs_edge_ws
./start_ccs_edge_dev.sh --check
./start_ccs_edge_dev.sh
./start_ccs_edge_dev.sh --mapping
./start_ccs_edge_dev.sh --static
# 另一个终端请求结束本次自有进程：
./start_ccs_edge_dev.sh --stop
~~~

--check（兼容 --preflight）只检查依赖和配置，不启动 ROS 节点或创建运行日志。无参数启动和显式 --mapping 含义相同：启动 MAVROS、Livox、通信、视频和阶段管理器，允许原生建图、地图保存及重定位，但任务适配器和原生控制器执行权限保持关闭，不接受飞行任务 PREPARE/SCHEDULE，不触发解锁、起飞或云台运动。--static 为纯观察模式，同时拒绝建图、重定位和飞行。

地图流包版本应为 0.13.3 或更高。若建图协商提示“mapping integration script is unavailable: rosrun”，先按本节顺序加载工作空间，再执行以下只读检查；成功输出应包含版本一致及 native packages available，且不会启动 ROS 节点或原生建图。

~~~bash
rosrun epgeneral_map_stream check_version.py
command -v rosrun
rosrun epgeneral_uav_integration uav_stage_client.py offline_check
~~~

--flight 显式开启全部功能，包括任务适配器、原生控制器、建图和重定位；仅在实飞条件经过独立验收后使用。本次没有实机使用此选项，也没有新增 systemd/开机自启。--stop 在控制器空中或状态未知时拒绝结束，保留控制与定位。请先正常降落并确认未解锁；不能用 killall/pkill 杀飞行控制进程。重复启动由文件锁拒绝，已有 ROS master/监听端口会阻止启动，不复用未知进程。

只读运行就绪检查：

~~~bash
source /home/nrc/ccs_edge_ws/devel/setup.bash
python3 /home/nrc/ccs_edge_ws/deploy/uav_001/scripts/readiness.py
~~~

就绪检查失败必须排查具体缺失项，不能用静态 TF 或虚拟位姿补齐生产数据。

## 配置与接口

MQTT 0.5.0 配套共享配置包 0.1.4。UAV profile 使用 MQTT 配置 schema_version 2、field 连接模式和 fraction 电池单位；任务订阅由 device.id 展开。uav_001_bringup 显式传入已安装的共享配置目录，因此升级时须同步安装 MQTT 包、配置包与该 launch 文件。设备身份仍采用 schema_version 1。部署前可执行：

~~~bash
rosrun epgeneral_mqtav epgeneral_mqtav_node.py --config-dir "$(rospack find epgeneral_device_config)/config" --check-config
rosrun epgeneral_mqtav epgeneral_mqtav_node.py --config-dir "$(rospack find epgeneral_device_config)/config" --check-ros
~~~

这些检查不启动 ROS 节点或 MQTT 连接。完整迁移与回滚边界见 [MQTT 包说明](../../../epgeneral_mqtav/README.md)。

运行配置位于 /home/nrc/ccs_edge_ws/src/EPGeneral_device_config/config/ 的七份 YAML；deploy/uav_001/config 是交付快照。修改后同步两处并重启，不支持热更新。各配置字段及话题矩阵见[接口参考](../../INTERFACE_REFERENCE.md)。

| 功能 | 原生接口 |
| --- | --- |
| 飞控状态 / 电池 / 飞行状态 | /mavros/state、/mavros/battery、/mavros/extended_state |
| 位置 / 速度 / IMU | /mavros/local_position/pose、/mavros/local_position/velocity_local、/mavros/imu/data |
| 原生位置目标唯一输出 | /mavros/setpoint_position/local |
| 原生状态 / 指令参数 | /ctrl_cmd/status、/ctrl_cmd/state（ROS 参数，非话题） |
| 原生定位 | /ducted/localization/body_odom、/ducted/localization/map_ready、map→odom TF |
| 建图注册点云 / 保存 | /ducted/mapping/cloud_registered、/ducted/mapping/save_map |
| 重定位初值 | /ducted/relocalization/initialpose |
| 阶段协调服务 | /uav/UAV_001/stage |

CCS mission 使用 map 坐标，经实时 odom←map TF 完整三维转换为原生 odom 轨迹。转换前比较原生 body_odom 与 MAVROS 位姿：位置差不超过 0.15 m、姿态差不超过 10°，消息及 TF 新鲜度 0.5 s。不会重复进行 ENU/NED 转换。

PREPARE 仅加载/验证任务并启动未解锁原生控制器；计划时刻满足落地、未解锁、FCU system_status 为 STANDBY(3)/ACTIVE(4)、定位健康后发送参数 1，确认原生 HOLDING/OFFBOARD 及本轮任务代次后发送 2。默认起飞高度 1 m，水平速度≤0.3 m/s，垂直速度 0.2 m/s；不接受更高水平速度或非空中任务类型。direct 不提供自动避障。

任务身份绑定 task/subtask/device/revision/map/frame 和 execution_id。完成、取消、STOP 保持悬停；不能将悬停解释为落地。急停持久记录 run/state/emergency_stop.json，指令 3 请求原生 AUTO.LAND，只有新鲜 landed_state=1 且 armed=false 才报告成功。超时或失联报告失败，禁止自动恢复。适配器租约超时将 run/state/flight_fault.json 持久化并请求保持。

人工排障后清除闭锁需要落地锁定、没有控制器；通过阶段服务 reset 操作，不能直接删除正在生效的标记。新一轮自动起飞必须重新满足落地条件。

## A8 视频与网络

实际 A8 地址 192.168.144.25，MAC 7c:11:d7:15:d3:9a；RTSP 为 rtsp://192.168.144.25:8554/main.264，实际输入 HEVC/H.265 Main 1280×720@30。192.168.1.25 和 192.168.193.25 的探测没有响应。端侧 eth0 增加 192.168.144.140/24，保存到既有 Wired connection 1；未改雷达网段、Wi-Fi 地址或 ZeroTier 路由。

输出 H.264 Constrained Baseline 640×480@15、2000 kbps、MPEG-TS、SRT listener UDP 9000。初始 120 ms 在现场 Wi-Fi 出现丢包，实测改为 500 ms；设备配置与平台一致。GStreamer latency 属性使用毫秒，FFmpeg URL latency 使用微秒，接收示例：

~~~bash
ffplay 'srt://192.168.50.140:9000?mode=caller&latency=500000'
~~~

ARM64 下 ROS Python 与 libav 组合存在 libgomp 静态 TLS 加载冲突，因此仅视频节点设置 LD_PRELOAD=/lib/aarch64-linux-gnu/libgomp.so.1。H.265 用显式 avdec_h265 软件解码，避免自动选中不适配的硬件输出。8 秒无帧判定断流，3 秒后重试；/epgeneral_video_srt/status 记录帧数、新鲜度和重连次数。连接建立时请求新关键帧，不依赖旧云台驱动，不发送云台动作。

## 建图与重定位

由同一阶段服务互斥启动原生 mapping.launch / relocalization.launch。保存调用原生 save_map 服务到独立会话的新目录，仅接受本轮新生成非空 GlobalMap.pcd。使用实际 odom←camera_init 变换导出 map.pcd、map.pgm、map.yaml，并在 transform.json 保存变换；原生元数据的固定 frame_id: map 不作为依据。

PGM 中观测点为占据、未观测为未知，只供显示，不能作为 direct 三维避障保证。下载地图用于原生重定位，auto_initialize=false；发布初值后持续验证 map_ready 和新鲜 map→odom TF。空中不能切换/停止定位阶段。

## 日志与回滚

运行日志位于 logs/session-日期时间-PID/，logs/latest 指向最近一次启动会话。终端采用与 Go2/WheelTec 一致的 [OK]/[INFO]/[WARN]/[ERROR] 摘要，保留模式、日志路径、ROS master、节点注册和停止结果；节点注册不代表实机数据就绪。startup.log 保存带时间戳的生命周期信息，runtime_monitor.log 保存监控重试和异常堆栈；重复安全保护提示最多每 30 秒记录一次，状态变化立即记录。roscore.log、bringup.log、ros/ 保留子进程及 ROS 诊断，mqtav/、map_stream/、relocalization/ 归入同一会话。预检成功不再输出内部 JSON，重复启动等预期错误不再向终端打印堆栈。原有历史日志保留；原生受管子进程位于 logs/stages/、logs/offboard/；run/supervisor.json 标明本次拥有的 PID 和日志目录。任务位于 mission/，地图位于 maps/，闭锁位于 run/state/。验证夹具在 validation/，与正式任务目录隔离。部署证据保存在控制端 artifacts/uav001_deployment_20260920/。

停止并确认落地锁定后，仅恢复本次改动的源文件、profile 与 UAV_001 配置。不要覆盖已有 maps/、mission/ 或最新 run/state/emergency_stop.json、flight_fault.json。初次部署没有旧 CCS 工作空间；回退可将本次 src/deploy 保留为禁用备份，保留任务、地图和闭锁以供审计。

相机地址回滚仅删除本次新增项：

~~~bash
sudo nmcli connection modify 'Wired connection 1' -ipv4.addresses 192.168.144.140/24
sudo ip address del 192.168.144.140/24 dev eth0
~~~

原网络快照在 /home/nrc/.deployment_backups/UAV_001-20260920/。测试用 RTSP 丢包规则已自动清除；无线省电诊断完成后恢复原值 on。不得恢复整个旧网络文件覆盖后续变动，也不得覆盖原生标定。

静态检查和模拟任务验收不等同于实飞验收；direct 控制不提供自动避障。
