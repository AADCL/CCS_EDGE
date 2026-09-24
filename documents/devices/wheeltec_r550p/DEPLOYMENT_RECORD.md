# 设备部署记录

整理日期：2026-09-18；源码基线：CCS_dev dbe85904cdbae3d3b837f8816f29d1f030d7bd5a，配套 CCS 0.25.0。

按设备 ID 分区保存历史事实。以下原文中的版本、命令、路径、运行状态和验收结论仅属于原日期；迁移不代表重新部署或验收。新增记录写入对应设备 ID 小节。

<a id="deploy-records-ugv-003-deployment-md"></a>

<a id="deploy-records-ugv-003-deployment-md-ugv_003-部署与验收记录"></a>
# UGV_003 部署与验收记录

合并日期：2026-09-11；操作基线：CCS 0.23.1。此文件是该设备唯一的部署记录入口，后续按日期追加。

<a id="deploy-records-ugv-003-deployment-md-当前入口"></a>
## 当前入口

- 设备：UGV_003；profile：`wheeltec_r550p`；端侧：`nrc19@192.168.50.122`。
- [配置与脚本](../../../devices/wheeltec_r550p/profiles/wheeltec_r550p)保持原位置；[从零部署](../../USER_MANUAL.md#documents-deployment-guide-md)、[接口填写](../../INTERFACE_REFERENCE.md#documents-config-topic-reference-md)、[使用手册](../../USER_MANUAL.md#documents-user-manual-md)、[设备索引](../../../README.md)。
- 七公共包、managed_finalize、CCS 专用二维导航与控制权协调器；Gemini 336L 和 SRT 默认随根脚本启动，可用 `CCS_ENABLE_VIDEO=0` 关闭。

<a id="deploy-records-ugv-003-deployment-md-历史材料与来源校验"></a>
## 历史材料与来源校验

以下合并原文件，保留日期、版本、哈希、失败证据、跳过项和原操作示例。历史章节的“当前/最终运行”、旧日志、相机筛选、时差门控、旧服务/保存路径及退出方式仅适用于当时；新部署执行上方当前指南。未记载实测不能补写通过，旧请求不构成新任务指令。

| 原文件（相对 edge_side_pkg） | 原始字节 SHA-256 | 合并章节 |
| --- | --- | --- |
| `deploy/wheeltec_r550p/DEPLOYMENT.md` | `3665a62b1faa4264f7528e7aceeee58806f1dabfd0d62736a950ec298c8205ad` | [材料 1](DEPLOYMENT_RECORD.md#deploy-records-ugv-003-deployment-md-source-1) |
| `documents/WHEELTEC_R550P_DEPLOYMENT.md` | `071c75cb9d49d3d96d9f83a134774d2e7324b708a2d7457c2dc942e91baacabd` | [材料 2](DEPLOYMENT_RECORD.md#deploy-records-ugv-003-deployment-md-source-2) |
| `documents/WHEELTEC_R550P_DEPLOYMENT_LOG.md` | `fb67b8897f7354043cb579260c0552d89165748d67596c773c3facfa50668b0d` | [材料 3](DEPLOYMENT_RECORD.md#deploy-records-ugv-003-deployment-md-source-3) |

<a id="deploy-records-ugv-003-deployment-md-source-1"></a>

<a id="deploy-records-ugv-003-deployment-md-历史材料-1deploywheeltec_r550pdeploymentmd"></a>
## 历史材料 1：deploy/wheeltec_r550p/DEPLOYMENT.md

> 归档原文；以下命令、状态与结论按原日期理解。

<a id="deploy-records-ugv-003-deployment-md-s1-wheeltech-r550p-ccs-端侧部署"></a>

<a id="deploy-records-ugv-003-deployment-md-wheeltech-r550p-ccs-端侧部署"></a>
### WheelTech R550P CCS 端侧部署

CCS 0.23.1 当前入口：[使用手册](../../USER_MANUAL.md#documents-user-manual-md) · [接口与配置](../../INTERFACE_REFERENCE.md#documents-interface-reference-md)。本页保留设备专项步骤；运行配置以脚本传入的工作空间 config/profile 为准，不能只修改包内默认 YAML。

本 profile 对应 `UGV_003`（`192.168.50.122`），运行于 Ubuntu 20.04、ROS Noetic 和 Jetson NX。CCS 工作空间为 `/home/nrc19/ccs_edge_ws`，并以 Overlay 方式只读依赖 `/home/nrc19/livox_fastlio` 中已验证的 WheelTech、Livox 和 FAST-LIO 包。

<a id="deploy-records-ugv-003-deployment-md-s1-工作空间"></a>

<a id="deploy-records-ugv-003-deployment-md-工作空间"></a>
#### 工作空间

部署以下 ROS 包到 `ccs_edge_ws/src`：

- `EPGeneral_device_config`
- `epgeneral_mqtav`
- `EPGeneral_udp_telemetry`
- `EPGeneral_video_srt`
- `EPGeneral_map_stream`
- `EPGeneral_relocalization`
- `EPGeneral_task_control`

只部署端侧七包 allowlist，不复制 `deploy` 与 `documents`。安装 `python3-msgpack`、`python3-paho-mqtt` 后执行：

```bash
cd /home/nrc19/ccs_edge_ws
source /opt/ros/noetic/setup.bash
source /home/nrc19/livox_fastlio/devel/setup.bash
rosdep install --from-paths src --ignore-src -r -y
catkin_make -j1 --force-cmake -DPYTHON_EXECUTABLE=/usr/bin/python3
```

profile 配置安装到 `/home/nrc19/ccs_edge_ws/config/wheeltec_r550p`，一键脚本安装到工作空间根目录。系统时间必须由 `192.168.50.101` 提供 NTP。

<a id="deploy-records-ugv-003-deployment-md-s1-启动"></a>

<a id="deploy-records-ugv-003-deployment-md-启动"></a>
#### 启动

```bash
cd /home/nrc19/ccs_edge_ws
./start_ccs_edge_dev.sh
```

脚本启动底盘、Livox、MQTT、UDP 遥测、建图协调、重定位协调和任务控制。设备未安装摄像头，视频包只编译部署，不由脚本启动。按 `Ctrl+C` 时脚本先发布零速度，再停止自己管理的进程。

运行日志位于 `/home/nrc19/.ros/ccs_edge_dev_wheeltec_r550p/log`。地图和下载地图仍位于 `/home/nrc19/livox_fastlio/maps`，这是 Overlay 布局的明确例外。

<a id="deploy-records-ugv-003-deployment-md-s1-静态验证"></a>

<a id="deploy-records-ugv-003-deployment-md-静态验证"></a>
#### 静态验证

```bash
rostopic hz /livox/lidar
rostopic hz /livox/imu
rostopic hz /odom
rostopic hz /imu
rostopic echo -n 1 /PowerVoltage
rosnode list
```

不得在无人值守或未准备急停时发送非零 `/cmd_vel`。本次部署只执行静态检查、零速度保护和协议链路验证。

<a id="deploy-records-ugv-003-deployment-md-source-2"></a>

<a id="deploy-records-ugv-003-deployment-md-历史材料-2documentswheeltec_r550p_deploymentmd"></a>
## 历史材料 2：documents/WHEELTEC_R550P_DEPLOYMENT.md

> 归档原文；以下命令、状态与结论按原日期理解。

<a id="deploy-records-ugv-003-deployment-md-s2-wheeltech-r550p-端侧部署说明"></a>

<a id="deploy-records-ugv-003-deployment-md-wheeltech-r550p-端侧部署说明"></a>
### WheelTech R550P 端侧部署说明

CCS 0.23.1 当前入口：[使用手册](../../USER_MANUAL.md#documents-user-manual-md) · [接口与配置](../../INTERFACE_REFERENCE.md#documents-interface-reference-md)。本页保留设备专项步骤；运行配置以脚本传入的工作空间 config/profile 为准，不能只修改包内默认 YAML。

<a id="deploy-records-ugv-003-deployment-md-s2-设备基线"></a>

<a id="deploy-records-ugv-003-deployment-md-设备基线"></a>
#### 设备基线

- 设备：轮趣 WheelTech R550P 四轮差速底盘
- CCS ID：`UGV_003`
- SSH/ROS IP：`192.168.50.122`
- 地面站：`192.168.50.101`
- 用户及主目录：`nrc19`、`/home/nrc19`
- CCS 工作空间：`/home/nrc19/ccs_edge_ws`
- 外部设备栈：`/home/nrc19/livox_fastlio`
- 系统：Ubuntu 20.04.6、ROS Noetic、Jetson NX aarch64

<a id="deploy-records-ugv-003-deployment-md-s2-部署结构"></a>

<a id="deploy-records-ugv-003-deployment-md-部署结构"></a>
#### 部署结构

`ccs_edge_ws` 只保存七个 CCS 通用包、`config/wheeltec_r550p` 和根目录启动脚本。WheelTech 底盘、Livox、FAST-LIO、建图、NDT 和 TEB 包继续由 `livox_fastlio` 提供，部署过程不得修改该外部工作空间。

端侧状态、PID 和日志使用 `~/.ros/ccs_edge_dev_wheeltec_r550p`。地图继续使用 `~/livox_fastlio/maps`，下载地图使用 `~/livox_fastlio/maps/ccs_download`。

<a id="deploy-records-ugv-003-deployment-md-s2-设备接口"></a>

<a id="deploy-records-ugv-003-deployment-md-设备接口"></a>
#### 设备接口

| 功能 | ROS 接口 |
|---|---|
| 底盘在线状态 | `/odom` (`nav_msgs/Odometry`) |
| 底盘电压 | `/PowerVoltage` (`std_msgs/Float32`) |
| Livox 点云/IMU | `/livox/lidar`、`/livox/imu` |
| FAST-LIO 位姿 | `/fastlio_odom` |
| FAST-LIO 原始里程计 | `/Odometry` |
| 控制 | `/cmd_vel`，仅 `linear.x` 和 `angular.z` |
| 地图/里程计坐标 | `map`、`odom`、`base_link`、`body` |

电池化学体系和放电曲线未知，端侧只上报电压，地面站不估算百分比。设备未安装摄像头，视频包默认禁用。

<a id="deploy-records-ugv-003-deployment-md-s2-部署方法"></a>

<a id="deploy-records-ugv-003-deployment-md-部署方法"></a>
#### 部署方法

1. 通过 SSH 登录并确认 `/dev/wheeltec_controller`、`wlan0=192.168.50.122`、`eth0=192.168.1.5` 和 Mid-360 `192.168.1.165`。
2. 安装 `python3-msgpack`、`python3-paho-mqtt`，并对七个 CCS 包执行 `rosdep install`。
3. 创建 `/home/nrc19/ccs_edge_ws/src`，复制七个适用 CCS 包；安装 profile 和根目录脚本。
4. 按 ROS Noetic、`livox_fastlio`、`ccs_edge_ws` 顺序加载环境，以 `catkin_make -j1` 编译。
5. 安装 timesyncd profile，使 NTP 服务端固定为 `192.168.50.101`。
6. 执行 `./start_ccs_edge_dev.sh`，检查基础话题、CCS 节点、MQTT、UDP 和监听端口。
7. 按 `Ctrl+C` 验证零速度发布、进程清理和日志落盘。

<a id="deploy-records-ugv-003-deployment-md-s2-安全边界"></a>

<a id="deploy-records-ugv-003-deployment-md-安全边界"></a>
#### 安全边界

- 本次验收不发送非零 `/cmd_vel`，不发送导航目标。
- `factory_a` 只用于加载地图及节点/TF 链检查，不据此宣称全局定位成功。
- 建图测试只允许 prepare/start/abort，不生成或替换正式地图。
- 安装摄像头并确认图像话题前，不启用视频 launch。

实际执行结果、时间、命令和未验证项见 `WHEELTEC_R550P_DEPLOYMENT_LOG.md`。

<a id="deploy-records-ugv-003-deployment-md-source-3"></a>

<a id="deploy-records-ugv-003-deployment-md-历史材料-3documentswheeltec_r550p_deployment_logmd"></a>
## 历史材料 3：documents/WHEELTEC_R550P_DEPLOYMENT_LOG.md

> 归档原文；以下命令、状态与结论按原日期理解。

<a id="deploy-records-ugv-003-deployment-md-s3-wheeltech-r550p-部署日志"></a>

<a id="deploy-records-ugv-003-deployment-md-wheeltech-r550p-部署日志"></a>
### WheelTech R550P 部署日志

<a id="deploy-records-ugv-003-deployment-md-s3-2026-08-28-epgeneral_map_stream-v0120-联合建图部署验证"></a>

<a id="deploy-records-ugv-003-deployment-md-2026-08-28-epgeneral_map_stream-v0120-联合建图部署验证"></a>
#### 2026-08-28 `epgeneral_map_stream` v0.12.0 联合建图部署验证

- `UGV_003` 作为 `UGV_001` 的联合建图从设备；旧 v0.11.0 包和 `config/wheeltec_r550p/map_stream.yaml` 已备份到 `~/.deployment_backups/20260828T033407Z_map_stream_v012`，未修改只读外部工作空间 `/home/nrc19/livox_fastlio`。
- v0.12.0 归档 SHA-256 为 `43c506d171f7264a63cc61f651657489444c0150e67d312556767cc0a9dd4c43`。部署时恢复 Linux LF 和脚本 0755 权限；版本检查、43 项端侧增量测试、catkin 增量构建、launch 解析和 Bash 语法检查通过，其中 1 项依赖地面站验证器的成果测试按设计跳过。
- 根管理脚本受控重启时清理了此前的重定位/导航子进程。重启后 `/epgeneral_map_stream` 使用 v0.12.0，UDP 14561 和 TCP 14600 正常监听；空闲及验证结束后无 FAST-LIO、mapper、TF manager 或 pose adapter 建图子节点残留。
- 与主设备 `UGV_001` 完成无运动静态联合建图，外参方向 `UGV_001 map <- UGV_003 map`，XYZ `(0,-1.2,0)`、RPY `(0,0,0)`；本设备收到 16 个有效预览分片后正常停止并生成 PCD/PGM/YAML 成果。
- 地面站下载、校验并联合融合 27,477 点，未剔除设备，原子提交到临时地图仓储且未设为 active map。验证全程监听 `/cmd_vel` 无输出，未发送导航目标或初始位姿。

<a id="deploy-records-ugv-003-deployment-md-s3-约束与基线"></a>

<a id="deploy-records-ugv-003-deployment-md-约束与基线"></a>
#### 约束与基线

- 部署目标：`UGV_003` / `192.168.50.122`，执行日期 2026-08-27（Asia/Shanghai）。
- 系统：Ubuntu 20.04.6、ROS Noetic、Jetson Xavier NX（aarch64）。
- 登录用户：`nrc19`；本文不记录登录密码。
- 不发送非零 `/cmd_vel`，不发送导航目标，不启动视频，不替换正式地图。
- `/home/nrc19/livox_fastlio` 作为只读外部设备栈；CCS Overlay 位于 `/home/nrc19/ccs_edge_ws`。

<a id="deploy-records-ugv-003-deployment-md-s3-部署流程"></a>

<a id="deploy-records-ugv-003-deployment-md-部署流程"></a>
#### 部署流程

| 时间 | 阶段 | 命令/操作 | 结果 |
|---|---|---|---|
| 19:00 前 | 设备盘点 | 检查系统、ROS、串口、网络、摄像头、工作空间和地图 | `/dev/wheeltec_controller -> ttyACM0`；无 `/dev/video*`；`factory_a` 和 `wheeltec_install_test` 保持不变 |
| 20:37 | 外部栈核验 | `rospack find`、检查 WheelTech launch 和节点名 | 7 个 WheelTech 依赖包及 3 个正式入口均存在；底盘节点为 `/wheeltec_robot` |
| 20:43 | Overlay 安装 | 创建 `ccs_edge_ws/src`，复制 7 个 CCS 包、profile 和根目录脚本 | 未部署 `EPQRD_go2_bridge`；原生 `bash -n` 通过 |
| 20:46 | 依赖安装 | `apt-get install python3-msgpack python3-paho-mqtt` | 两个缺失依赖安装成功 |
| 20:48 | rosdep | `rosdep install --from-paths src --ignore-src -r -y` | 设备未初始化 rosdep；`rosdep init` 因 `raw.githubusercontent.com` DNS 解析失败，未联网完成 |
| 20:50 | 构建 | `catkin_make -j1 --force-cmake -DPYTHON_EXECUTABLE=/usr/bin/python3` | 成功遍历并构建 7 个包，视频 GStreamer C++ 节点编译成功 |
| 20:52 | NTP | 安装 `timesyncd-ccs.conf` 并重启 `systemd-timesyncd` | `NTPSynchronized=yes`，`ServerName/Address=192.168.50.101` |
| 20:53 | 静态解析 | `rospack find`、4 次 `roslaunch --files` | 7 个 CCS 包均可发现；建图、重定位、导航及统一 bringup 均可解析 |
| 20:54 | 一键启动 | `/home/nrc19/ccs_edge_ws/start_ccs_edge_dev.sh` | 底盘/Livox 和 6 个非视频 CCS 服务全部启动 |
| 20:59 | 建图链 | 地面站发送 `prepare_mapping`、`start_mapping`、`abort_mapping` | prepare/start/abort 均接受并到达 `mapping`；未执行 stop/finalize，未生成正式地图 |
| 21:02 | 重定位链 | `factory_a` negotiate + `start_stack` | 到达 `map_ready -> starting -> awaiting_pose`；未发送初始位姿 |
| 21:05 | 安全退出 | 向一键脚本发送 `SIGTERM` 并监听 `/cmd_vel` | 捕获全零 Twist；ROS Master 停止且 PID 目录为空 |

<a id="deploy-records-ugv-003-deployment-md-s3-自动化测试"></a>

<a id="deploy-records-ugv-003-deployment-md-自动化测试"></a>
#### 自动化测试

- 本地 WheelTech profile：4/4 通过；任务控制：30/30 通过；重定位：13/13 通过。
- Python `compileall`、YAML/XML 解析以及设备端两个 shell 脚本的 `bash -n` 通过。
- 本地全量 `unittest discover`：268 项中 265 项通过，3 项失败。失败均为本次改动前已存在的问题：默认 `UAV_001` 的端/地 IP 不一致、无 OpenGL 上下文导致取色失败、日间主题颜色表不完整。
- 设备端 `catkin_make run_tests`：134 项中 125 项通过、9 项导入/fixture 错误。原因是 CCS-only Overlay 按方案不包含地面站 `ccs_monitor`，也不安装 Scout profile；包运行构建本身成功。
- Scout 兼容命令已恢复原 8 个 launch 参数；WheelTech `managed_finalize` 单独追加 5 个节点名。Windows 运行 Scout 路径测试仍会因 `os.path.abspath` 将 Linux 路径加盘符而失败，Linux 设备不存在该差异。

<a id="deploy-records-ugv-003-deployment-md-s3-实机静态验收"></a>

<a id="deploy-records-ugv-003-deployment-md-实机静态验收"></a>
#### 实机静态验收

- `/livox/lidar`：`livox_ros_driver2/CustomMsg`，约 10.0 Hz。
- `/livox/imu`：`sensor_msgs/Imu`，约 200.0 Hz。
- `/odom`、`/imu`：分别为 `nav_msgs/Odometry`、`sensor_msgs/Imu`，均约 20.0 Hz。
- `/PowerVoltage`：`std_msgs/Float32`，采样值 22.562 V；未估算电量百分比。
- 基础栈未启动 FAST-LIO 时 `/Odometry` 不发布；重定位链启动后 `/fastlio_odom` 和 TF 可用。
- MQTT 日志持续发送 `mqtav/UGV_003/status` 和 `mqtav/UGV_003/heartbeat`。
- UDP 控制端口 14561/14563/14565 和地图 HTTP 端口 14600 正常监听。
- 建图链在收到 abort 后的关闭窗口报告一次点云超时，随后返回 abort accepted 并清理全部建图节点。临时目录 `20260827_205912` 未作为地图保留，已移动到日志状态目录的 `aborted_maps` 下。
- `factory_a` 的 `/map_2d` 成功加载：223 x 188，分辨率 0.05 m；`odom -> base_link` TF 连续可读。
- 重定位状态停留在 `awaiting_pose`，任务适配器据此返回 `Scout is not localized on a usable map`，符合“无活动地图拒绝任务”的保护要求。
- 设备无摄像头，因此视频包已编译但从未启动；全程未执行实车运动。

<a id="deploy-records-ugv-003-deployment-md-s3-工作空间外变更"></a>

<a id="deploy-records-ugv-003-deployment-md-工作空间外变更"></a>
#### 工作空间外变更

- 安装 apt 包：`python3-msgpack`、`python3-paho-mqtt`。
- 新增 `/etc/systemd/timesyncd.conf.d/ccs-edge.conf`，NTP 固定为 `192.168.50.101`。
- 在 `/home/nrc19/livox_fastlio/maps/ccs_download/factory_a` 放置 `factory_a` 的三个只读副本，用于重定位链静态验收。
- ROS 运行日志、PID、状态及中止建图样本位于 `/home/nrc19/.ros/ccs_edge_dev_wheeltec_r550p`，未写入工作空间。

<a id="deploy-records-ugv-003-deployment-md-s3-建图坐标系错误修复2026-08-27"></a>

<a id="deploy-records-ugv-003-deployment-md-建图坐标系错误修复2026-08-27"></a>
#### 建图坐标系错误修复（2026-08-27）

- 首次实机测试中，协商完成后开始建图即出现 `LOCAL FRAME_MISMATCH / PCD 分片源坐标系不匹配`。端侧日志持续记录 `source=odom target=odom`，确认点云已按 WheelTech profile 正确变换到 `odom`，并非 FAST-LIO frame 或外参错误。
- 根因是地面站 `config/map_building.json` 缺少 `UGV_003` 的设备级 frame 配置，因而回退到默认 `preview_source=lio_odom`。现已增加 `remote_mapping=odom`、`preview_source=odom`、`remote_artifact=map`。
- 修复前先对遗留会话发送 `abort_mapping`。已确认 `/wheeltec_pointcloud_mapper`、`/laserMapping`、`/wheeltec_tf_manager` 和 `/wheeltec_pose_adapter` 退出，仅常驻 `/epgeneral_map_stream`；未执行成果 finalize。
- 地面站协调器增加 `FRAME_MISMATCH` 自动中止保护：协商结果、分片 `frame_id` 或 `source_frame_id` 不一致时保留原始错误码和协议日志，进入现有可重试的 `abort_mapping` 状态机；abort ACK 后提示端侧已自动中止并清除活动会话。
- 地面站配置只在启动时读取。已确认原进程命令为 `python.exe run.py`，并重启为新进程，使 `UGV_003` 配置生效；端侧代码、配置及线上协议均未修改。
- 新增配置及协调器测试，覆盖 `odom -> odom` 分片接受、协商 frame 错误自动 abort、分片 source frame 错误自动 abort、相同 request ID 重试，以及 ACK 后保留 `FRAME_MISMATCH`。地图协议、建图服务、Scout 和 Go2 回归共 33 项通过，`compileall` 与 `git diff --check` 通过。
- 新配置下“接收并显示至少 3 个 PCD 分片”的静态实机复验尚未完成。自动化环境无法可靠操作原生 Qt 窗口，因此未采用屏幕坐标点击，以避免误触 stop/finalize；复验时应使用“强制结束”，不得发送非零 `/cmd_vel`。

<a id="deploy-records-ugv-003-deployment-md-s3-未验证项"></a>

<a id="deploy-records-ugv-003-deployment-md-未验证项"></a>
#### 未验证项

- 实车前进、后退、转向和任何非零速度控制。
- 真实初始位姿下的 NDT 收敛和全局定位结果。
- move_base/TEB 导航目标执行。
- 摄像头采集及 SRT 视频流。
- 设备能够访问 GitHub 后的完整 `rosdep update`。
- 修复后的地面站累计接收至少 3 个 `odom -> odom` PCD 分片并显示点数增长。

<a id="deploy-records-ugv-003-deployment-md-2026-09-16-导航硬件遥控与-gemini-336l-修复"></a>
## 2026-09-16 导航、硬件遥控与 Gemini 336L 修复

<a id="deploy-records-ugv-003-deployment-md-根因与行为变化"></a>
### 根因与行为变化

- 旧导航入口要求下载目录中不存在的 `terrain_2p5d.yaml`。地形服务先退出，必需的 `move_base` 随后以 `-6` 退出，所以地面站只看到“waiting for move_base action server”后报 `NAVIGATION_PROCESS_EXITED`。新入口 `wheeltec_ccs_2d_navigation.launch` 直接使用下载的 `map.yaml/map.pgm`，保留实时点云障碍、局部代价地图、TEB 和速度安全门。
- 旧底盘驱动在没有自主任务时仍以 20 Hz 向串口写入零速度，持续抢占原配硬件遥控；地面站停车写入的 `/cmd_vel` 也没有底盘订阅者。驱动补丁把默认状态改为手动控制权，手动状态继续读取里程计、IMU 和电压但不写周期速度；自主状态仅接收安全门输出，并同时要求 10 Hz 控制心跳，超过 0.5 秒即锁定停车。
- 设备已安装 Orbbec Gemini 336L，实际彩色话题为 `/camera/color/image_raw`，旧 profile 却记录为未安装且根脚本不启动视频。新 profile 调用现有 `wheeltec_orbbec336l.launch`，SRT 输出为 640x360、30 fps、2500 kbps、UDP 9000；相机和视频由 `manage_ccs_video.sh` 单独持有并支持重启。

<a id="deploy-records-ugv-003-deployment-md-安装备份与版本"></a>
### 安装、备份与版本

- CCS 工作空间：`/home/nrc19/ccs_edge_ws`；外部驱动工作空间：`/home/nrc19/livox_fastlio`；任务包部署版本：`epgeneral_task_control 0.6.0`。
- CCS 源码、运行配置、启动脚本及二进制部署前备份：`/home/nrc19/.deployment_backups/20260916T041240Z_ugv003_nav_rc_gemini336l`，其中包含 `pre_deploy_files.tar.gz`、归档校验文件和 `pre_deploy.sha256`。
- 底盘驱动独立备份：`/home/nrc19/.deployment_backups/20260916T041444Z_ugv003_control_authority/turn_on_wheeltec_robot.tar.gz`。补丁管理器只接受清单定义的基线或目标树，遇到未知源码拒绝覆盖。
- 驱动补丁目标 SHA-256：`CMakeLists.txt=c17ad363...32cfb0`、`package.xml=2e12054d...0f021`、`include/wheeltec_robot.h=f271e91a...12d8c`、`src/wheeltec_robot.cpp=5d22d5a3...874f91`、`test/test_cmd_vel_watchdog.cpp=38a08aa0...154f`。完整值保存在 `deploy/wheeltec_r550p/driver_patch/patched.sha256`。
- 导航子进程日志写入 `/home/nrc19/.ros/ccs_edge_dev_wheeltec_r550p/log/navigation`；启动失败响应包含退出码、日志末尾摘要和日志路径。
- 关键部署后 SHA-256：任务包 `package.xml=1e7064ec...33847`、二维导航 launch `2984eff8...19e35`、控制权模块 `8c9bf112...54d69`、`task_control.yaml=9d204081...e7851`、`video.yaml=ff3957f9...8f707`、根脚本 `8706485f...906d1`、视频管理脚本 `248f78cf...aa88f`。完整 17 文件清单位于上述 CCS 备份目录的 `post_deploy.sha256`。

<a id="deploy-records-ugv-003-deployment-md-控制权与接口"></a>
### 控制权与接口

导航速度链路固定为 `/move_base -> /nav_cmd_vel -> /wheeltec_safety -> /wheeltec_driver/cmd_vel`。`/wheeltec_control/enable`（`std_srvs/SetBool`）在确认实时定位和 `/fastlio_odom` 新鲜后依次复位安全状态、取得驱动自主权并打开安全门；`data=false` 先停车再归还硬件遥控。`/wheeltec_control/stop`（`std_srvs/Trigger`）锁定停车，`/wheeltec_control/reset` 仅在人工处理故障后复位。真实状态分别由 `/wheeltec_control/enabled`、`/wheeltec_control/localization_ok` 和 `/wheeltec_robot/control_enabled` 发布；任务适配器在自主阶段向 `/wheeltec_driver/control_heartbeat` 以 10 Hz 发布 `std_msgs/Empty`。

基础栈启动和任务准备均保持手动控制权。只有任务调度取得定位、控制权及安全门确认后才允许执行；正常完成、取消和卸载先停车再归还硬件遥控。急停、控制进程失联、心跳过期或驱动故障进入持久锁定状态，修复原因并确认无任务后才能调用复位服务。任务 UDP 协议、端口和消息格式未改变。

<a id="deploy-records-ugv-003-deployment-md-自动验证结果"></a>
### 自动验证结果

- 本地任务控制回归 104/104 通过，端侧文档/布局/配置/profile/版本回归 26/26 通过；Python 编译、launch XML 解析和 `git diff --check` 通过。
- 设备端 CCS 增量构建成功，`check_version.py` 确认 0.6.0；专用二维导航与 Gemini launch 可解析。
- 设备端驱动测试 15/15 通过，覆盖看门狗、前进/后退/纯转向数据包编码、参数、源码身份和控制权租约。
- 设备端候选任务测试 21/21 通过；最终控制权增量测试 11/11 通过。已安装包的 Wheeltec/Scout/Go2 控制回归为 74 通过、2 个 fixture 错误；错误均因 CCS-only overlay 不含公共 `config/task_control.yaml` 测试夹具，不是运行代码失败。
- Gemini 336L 由视频管理脚本成功启动，`/camera/color/image_raw` 实测约 29.97 Hz，UDP 9000 由 `epgeneral_video_srt` 监听；地面站 ffprobe 成功解码 H.264 640x360@30。最终一键重启后再次取得首帧并完成同规格解码。
- 使用地图 `96f90304-7ad9-41e9-bc5a-938841749eef` 的 PCD/PGM/YAML 做无目标静态启动：`move_base`、二维 map_server、实时地形过滤和 `/wheeltec_safety` 均存活，地图为 213x190、0.05 m；全局代价地图仅含 StaticLayer 和 InflationLayer，速度接线与计划一致。验证后临时导航进程全部清理，底盘全程保持 `control_enabled=false`。
- 当前重定位状态为 `standby` 且无 `/fastlio_odom`，控制权接管正确返回 `localization is unavailable or stale`。空闲态归还和人工复位曾因安全门未启动误报失败，现已改为以驱动确认手动/复位为成功条件，并在响应中保留安全门缺失提示；最终实机调用均成功且两个 enabled 状态均为 false。
- 验证未发送非零速度或导航目标。

<a id="deploy-records-ugv-003-deployment-md-启停视频恢复与回滚"></a>
### 启停、视频恢复与回滚

~~~bash
cd /home/nrc19/ccs_edge_ws
./start_ccs_edge_dev.sh
CCS_ENABLE_VIDEO=0 ./start_ccs_edge_dev.sh
./manage_ccs_video.sh status
./manage_ccs_video.sh restart
~~~

正常退出由根脚本调用 `/wheeltec_control/enable data:false`，不能再向无订阅者的 `/cmd_vel` 假停车。视频故障只降级视频，基础服务继续运行；查看 `~/.ros/ccs_edge_dev_wheeltec_r550p/log/camera.log` 和 `video_srt.log` 后可单独重启。

回滚前先停止根脚本并确认没有任务、`/wheeltec_control/enabled=false` 且底盘处于手动控制权。CCS 文件从 `20260916T041240Z_ugv003_nav_rc_gemini336l` 归档恢复；驱动执行：

~~~bash
cd /home/nrc19/ccs_edge_ws/driver_patch
./manage_driver_patch.sh rollback \
  /home/nrc19/livox_fastlio/src/turn_on_wheeltec_robot \
  /home/nrc19/livox_fastlio \
  /home/nrc19/.deployment_backups/20260916T041444Z_ugv003_control_authority/turn_on_wheeltec_robot.tar.gz
~~~

回滚完成后重新构建相关工作空间，仍需先验证手动遥控再恢复任务服务。回滚不得删除或覆盖未处理的急停/故障锁存来绕过安全状态。

<a id="deploy-records-ugv-003-deployment-md-人工待验项"></a>
### 人工待验项

- 原配遥控器的前进、后退、原地左转和原地右转。
- 有效定位后的任务准备、短距离任务、停止/取消、控制权归还和任务结束后再次硬件遥控。
- 地面站界面中的实际连续画面观测；协议层 SRT 解码已自动通过，但界面观测和运动项目不能由静态检查或单元测试替代。

<a id="deploy-records-ugv-003-deployment-md-2026-09-16-导航振荡失败分类修复epgeneral_task_control-061"></a>
## 2026-09-16 导航振荡失败分类修复（`epgeneral_task_control` 0.6.1）

<a id="deploy-records-ugv-003-deployment-md-故障原因与修复"></a>
### 故障原因与修复

- 首次任务已取得自主控制权并运行约 20 秒，随后 `move_base` 因“Robot is oscillating”以 action state 4 结束。任务适配器错误地把这一普通导航失败当作控制安全故障，调用锁定停车并写入持久急停标记；因此后续任务在真正执行前被 `emergency stop requires manual reset` 拒绝。
- TEB 配置同时存在无效速度边界：`max_vel_x_backwards=0.0`，小于 `penalty_epsilon=0.05`，运行时产生负边界告警。专用导航入口现将后退速度上限设为 `0.10`，使优化约束有效；安全门仍保持 `allow_reverse=false`，未放开任务倒车。
- `/fastlio_odom` 在现场只提供定位位姿，twist 始终为零，不适合作为 TEB 的速度反馈。任务适配器继续用 `/fastlio_odom` 校验定位与读取位姿，专用导航新增 `navigation_odom_topic: /odom`，由轮式里程计向 TEB 提供速度。
- 普通的 action 失败、无路径、目标拒绝/抢占及航点超时现只取消导航并释放自主控制权，不再写入急停标记。显式急停、action `LOST`、控制权故障、定位失效、导航进程异常和内部故障仍执行锁定停车并要求人工复位；动作终态处理前再次校验控制心跳，关闭最后一次轮询后的失联窗口。

<a id="deploy-records-ugv-003-deployment-md-部署与验证"></a>
### 部署与验证

- 部署版本：`epgeneral_task_control 0.6.1`。部署前备份及事故证据位于 `/home/nrc19/.deployment_backups/20260916T105402Z_ugv003_oscillation_fault_classification`。
- 备份中的 `pre_deploy.sha256` 和 `post_deploy.sha256` 记录了替换前后校验值。关键文件部署后 SHA-256：`package.xml` 为 `9f364a7d5a7ee21eab7c3a02fd0554644236ff179cb40d1e19b7d826d9a29f7a`，`scout_adapter.py` 为 `8c4a315d0ca82cb6b35b41ef0a5af9325624da2391fd399fdee35e2f2599346e`，专用导航 launch 为 `6dd84c133249a466e0c9b08e0b186183306e30706f0d190619fffc3bc7b4a65c`，设备任务配置为 `e0e64dd0b0b3d0fe3ec0b74dc5fde042b7bc5a19ab6f1c192cd7e1138954c097`；最终部署包为 `1e728d4eff5979585699fce72bda3677975947f491b7a3d425b4cea3d0497877`。
- 本地任务控制测试 111/111 通过；WheelTech profile、配置、文档、包版本和视频测试 26/26 通过。设备端 `catkin_make -j1 --pkg epgeneral_task_control`、0.6.1 版本一致性检查及任务/导航 launch 解析通过。
- 设备端专项回归：Scout 21/21、WheelTech 11/11 通过；Go2 53/55 通过，另 2 项仅因 CCS-only Overlay 未安装源码测试夹具 `EPGeneral_device_config/config/task_control.yaml` 而报错，不影响已部署运行配置。
- 一键栈、Gemini 336L 相机和 SRT UDP 9000 均恢复健康。调用 `/epgeneral_navigation_task_adapter/reset_emergency_stop` 成功，持久急停标记已移除，复位后 `/wheeltec_control/enabled=false`、`/wheeltec_robot/control_enabled=false`，设备保持手动控制权。
- 本轮部署和静态验收未发送导航目标或非零速度。实车运动、短距离任务、原配遥控前进/后退/原地转向以及任务结束后的控制权归还仍须现场人工验收。

<a id="deploy-records-ugv-003-deployment-md-2026-09-16-代价地图自体残留与倒置视频修复任务-063--安全门-012"></a>
## 2026-09-16 代价地图自体残留与倒置视频修复（任务 0.6.3 / 安全门 0.1.2）

<a id="deploy-records-ugv-003-deployment-md-现场根因"></a>
### 现场根因

- 在 0.6.2 已消除 `input_generation_changed_during_check` 后，22:30 的限速探针显示 `move_base` 已发布 `linear.x=0.1437`、`angular.z=0.2395`，但驱动输出仍为零，安全门立即锁存 `obstacle_in_costmap_stop_region`。
- 当时 120x120、0.05 m 的局部网格中有 14 个值 99 单元和 1 个值 100 单元。ROS costmap 的 99 已表示按机器人内切半径膨胀的区域，旧安全门又按完整车体扫掠，形成重复膨胀；唯一值 100 单元中心约为 `(-0.2274, 0.2110)`，其 5 cm 方格与实测车体边界相交，是边界离散/自体残留。
- 同一快照的分类点云和原始点云均新鲜且无遮挡；FAST-LIO 在锁停约 31 秒后才退出，不是本次立即锁停的原因。未知 costmap 单元继续视为不安全，不能随自体残留一起过滤。
- Gemini 336L 物理安装上下倒置，原始话题保持 `/camera/color/image_raw`，仅 SRT 编码输出需要旋转 180 度。

<a id="deploy-records-ugv-003-deployment-md-修复行为"></a>
### 修复行为

- `wheeltec_safety 0.1.2` 只把源致命值 100 送入自身车体扫掠，并使用带朝向的方格/车体相交检测过滤与当前实测车体重合的已知致命单元。未知单元、分类点云和原始点云继续独立阻断。
- `epgeneral_task_control 0.6.3` 在控制仍为 disabled 时调用 `/move_base/clear_costmaps`，等待 0.30 秒并重新校验取消、定位和 disabled 状态后才允许自主使能。服务缺失、调用错误或检查失败时不会使能底盘或发送目标；Scout、Go2 未配置该服务，行为不变。
- `epgeneral_video_srt 0.1.2` 在编码前插入 `videoflip method=rotate-180`，设备 profile 设置 `rotation_degrees: 180`；相机原始话题、标定和 TF 不变。

<a id="deploy-records-ugv-003-deployment-md-部署备份与哈希"></a>
### 部署、备份与哈希

- 部署包 SHA-256：`b6f81f7e7258dc828e354afb14fe614069749c1aa1b9708666c30febb52d31fc`。
- 部署前 CCS/配置/二进制与安全门 0.1.1 备份目录：`/home/nrc19/.deployment_backups/20260916T151457Z_ugv003_nav_video_costmap`；`ccs_nav_video.tar.gz` SHA-256 为 `4b3a0ddac7d186cd2e124f2ffdf1809a10235777177a6c9f9be177347852535c`，`wheeltec_safety_0.1.1.tar.gz` 为 `90c9641e8ba68b66978ea2efc271db1b178b3dfa7bc759dc1fde138cc71a7aa1`。
- 安全补丁管理器从已验证 0.1.0 基线应用 0.1.2，并另建回滚归档 `/home/nrc19/.deployment_backups/20260916T151728Z_ugv003_safety/wheeltec_safety.tar.gz`，SHA-256 为 `29f3b4baafbc2743a98869d9606626ff9ca5037e14c886d87101aa26db27f8e1`。
- 关键部署后 SHA-256：任务 `package.xml=84e6875f7469955b122dc7051c3cdd46d8a372c015158babb2f80242b686e336`、`control_safety.py=7475ba0bef84bbe08ecb919b82ba1b5d50b3d2a48ae2b01c0bc7c1353fd5c28b`、`config.py=b01d6bea9c26d5ea952619fce2161561fbc3e7e2d30a6dd940e52259dae803e0`、`task_control.yaml=62421d7e3f510e589f7a96e3c66cf0441e2bebfd90be1143c9931d68b38666e7`、视频节点 `bbe329fca376af4df9f67980c148d36a79e8ef3a96fa60bf680e58b5dbf75ac8`、`video.yaml=eccf6517f844833eb1c42f0635284012a2805c9192450d8381b43916eed8c79b`、安全门脚本 `bb88cfafa6099913497865a16a56f34abbe14b987aabc6ef8213c73f34c3c60c`。完整清单位于上述备份目录的 `post_deploy.sha256`。

<a id="deploy-records-ugv-003-deployment-md-离线验证与当前状态"></a>
### 离线验证与当前状态

- 本地最终安全补丁从 0.1.0 基线 dry-run、应用和 7 文件目标哈希校验通过，安全门 28/28；任务控制新增清理顺序、清理失败和稳定期取消用例通过。
- 端侧 `wheeltec_safety` 28/28，任务控制/控制权专项 39/39；任务包和视频包增量构建成功，版本分别为 0.6.3 和 0.1.2，安全门为 0.1.2。
- 四个 launch XML、实际 Wheeltec profile 加载、`clear_costmaps_service=/move_base/clear_costmaps`、0.30 秒稳定期、`rotation_degrees=180`、GStreamer `videoflip` 元素、Python 编译及版本一致性均通过。
- 端侧完整任务源码测试执行 114 项，其中 25 项因精简部署工作区不含地面站 `ccs_monitor` 或测试专用 `EPGeneral_device_config/config/task_control.yaml` 而报环境错误；直接覆盖本次改动的 39 项专项测试全部通过。
- 按用户最新指令，本轮未重新启动运行栈、未启动导航、未发送目标或非零速度，也未执行遥控或画面方向现场观察；当前一键栈保持停止。真实运动与画面方向验收等待后续明确指令。

<a id="deploy-records-ugv-003-deployment-md-回滚"></a>
### 回滚

停止一键栈并确认无任务后，CCS 文件从 `20260916T151457Z_ugv003_nav_video_costmap/ccs_nav_video.tar.gz` 恢复。安全门必须在 `/wheeltec_safety` 未运行时执行：

~~~bash
cd /home/nrc19/ccs_edge_ws/safety_patch
./manage_safety_patch.sh rollback \
  /home/nrc19/livox_fastlio/src/wheeltec_safety \
  /home/nrc19/livox_fastlio \
  /home/nrc19/.deployment_backups/20260916T151728Z_ugv003_safety/wheeltec_safety.tar.gz
~~~

恢复后重新构建对应工作空间。回滚不得删除急停标记或绕过手动控制确认。

<a id="deploy-records-ugv-003-deployment-md-后续记录填写格式"></a>
## 后续记录填写格式

追加日期/范围、源码版本与差异、文件清单及前后哈希、备份/证据路径、命令与实测、告警/未测项、启停/回滚。回滚不覆盖更新的急停状态，文档整理不表示重新部署。
<a id="deploy-records-ugv-003-deployment-md-2026-09-17一键脚本-crlf-换行修复"></a>
## 2026-09-17：一键脚本 CRLF 换行修复

- 用户报告 Bash 第 2 行 `set: pipefail: invalid option name`。仓库 Windows 工作副本与端侧 `.deploy-0.6.3-20260916T151728Z/profile/wheeltec_r550p/start_ccs_edge_dev.sh` 均含 127 个 CRLF；只执行部署副本前两行即可复现 `pipefail\r: invalid option name`，退出码 2，不涉及启动任何节点。
- 检查时正式入口 `/home/nrc19/ccs_edge_ws/start_ccs_edge_dev.sh` 已为 LF，语法检查通过；因此不能断言用户报错时运行的就是当前正式入口。此次统一规范正式入口、视频管理脚本和部署副本，保留原权限与业务内容。
- 根因防复发：为 `edge_side_pkg/deploy/wheeltec_r550p/*.sh` 增加 Git `text eol=lf` 规则，确保 Windows 检出后直接部署也保持 LF。Git 中原脚本 blob 已为 LF，本次没有业务逻辑改动。
- 备份及逐文件前后哈希清单：`/home/nrc19/.deployment_backups/20260917T012930Z_ugv003_script_lf/manifest.json`；原文件按相对路径保存在同一目录。
- 部署副本修复前 SHA-256：`bc0f2105c4f76fda8936da3917a9b7090cae0ee4f8f70d7c9fca9bf4f22a2226`；修复后与正式入口、仓库 LF 文件一致：`8706485f2be4985d96fcc92ede0d4930845b370fc8648ddf64fb2fb53b3906d1`。
- 正式入口、视频管理脚本及两份部署副本均通过无 CR/无 BOM 检查、`bash -n` 和前两行选项初始化检查。未执行完整启动脚本，未启动或停止运行栈，未下发运动指令。
- 后续启动使用明确的正式路径：`bash /home/nrc19/ccs_edge_ws/start_ccs_edge_dev.sh`；本轮未执行此启动命令。离线复核使用 `bash -n /home/nrc19/ccs_edge_ws/start_ccs_edge_dev.sh`。
- 如需回滚，先核对上述清单，再从备份恢复对应相对路径文件；CRLF 部署副本仅用于追溯，不应恢复为启动入口。
<a id="deploy-records-ugv-003-deployment-md-2026-09-17第二航点-preempted-与倒车边界冲突"></a>
## 2026-09-17：第二航点 PREEMPTED 与倒车边界冲突

- 本地证据：主工作区 `data/task_server/b4aeeb5994c841d2a4f62470de106236/executions/be9fe9a095494d7a9c1282d9f5b7ca5d/events.jsonl` 记录 09:45:04.755 首点到达、09:45:12.600 第二点 action state 2；执行事件中没有主动取消，`data/logs/ccs.log` 该时段也没有取消记录。
- 端侧证据：ROS 会话 `aea4bfa2-b236-11f1-bee1-3c6d662cc13e/wheeltec_safety-6.log` 第 127 行在 09:45:12.401 记录 `reverse_command_inhibited`，任务控制 09:45:12.446 开始收尾、09:45:12.596 返回失败。09:44:18、09:47:33 也有同类锁停。
- 根因：此前 TEB 为避免零反向边界而设置 `max_vel_x_backwards=0.10`，但安全门 `allow_reverse=false`、`linear_deadband=0.02`。反向求解指令超过死区时安全门锁停并取消全部目标，最终显示 PREEMPTED。现场未保存触发瞬间速度，0.10 是配置上限而非实测值。
- 修改：反向上限改为 0.01、`penalty_epsilon=0.005`，显式关闭反向初始化及比例联动限速；前向惩罚 1000、前进 0.20、转向 0.40 和安全门全部保护保持原值。
- 上游依据：https://github.com/rst-tu-dortmund/teb_local_planner/blob/noetic-devel/src/teb_local_planner_ros.cpp 的 `saturateVelocity`：非正反向上限不会执行反向限幅。正数上限限制残量，独立轴限幅保留转向能力；安全门继续把允许死区内的反向残量归零。
- 备份目录：`/home/nrc19/.deployment_backups/20260917T015516Z_ugv003_teb_reverse_bound`，包含原 launch、前后哈希清单和 `resolved_params.yaml`。
- launch SHA-256：部署前 `b96d1583036239d3acd5c81d8220d29997aa2ae941c4362f9ce6683949c8b9c2`；部署后 `fef079e0b2747913e1cbee256aa12c1992791588e3f1d461122d3778c5e772aa`，与仓库一致。
- 离线验证：本地 profile 7/7、端侧安全门 28/28；`roslaunch --dump-params` 确认实际配置 `0 < 0.005 < 0.01 < 0.02`。使用实际安全核心确认旧边界触发故障、新边界平移归零且保留转向、-0.021 仍锁停。
- 生效条件：仅部署 launch 文件，未更改当前 ROS 参数、未重启节点、未复位安全锁、未发送运动指令。下次先卸载现有导航，再重新准备任务；若提示锁定，按既有禁用控制/人工复位流程处理。第二航点转向和任务完成仍待现场运动验收。
- 回滚：卸载导航后，将备份中的 `wheeltec_ccs_2d_navigation.launch` 恢复到 `/home/nrc19/ccs_edge_ws/src/EPGeneral_task_control/launch/` 并核对原哈希。旧参数会重新引入本次冲突。

<a id="deploy-records-ugv-004-deployment-md"></a>

<a id="deploy-records-ugv-004-deployment-md-ugv_004-部署与验收记录"></a>
# UGV_004 部署与验收记录

<a id="deploy-records-ugv-004-deployment-md-当前入口"></a>
## 当前入口

- 设备：UGV_004；profile：[wheeltec_r550p_02](../../../devices/wheeltec_r550p/profiles/wheeltec_r550p_02)；端侧：nrc15@192.168.50.123。
- 工作空间：`/home/nrc15/ccs_edge_ws`；原生 underlay：`/home/nrc15/livox_fastlio`（V5.1）。
- 七个公共包，视频安装编译但禁用，CCS 二维地图导航兼容入口，算法按需启动。

<a id="deploy-records-ugv-004-deployment-md-2026-09-12-首次部署"></a>
## 2026-09-12 首次部署

本次部署与授权范围内验收已完成。源码基线 `5683f35`，包含本次独立 profile、二维导航入口和平台 UGV_004 登记修正；已有工作树修改保留。

授权范围：安装构建、静止通信、启停与故障清理；不触发真实建图、重定位或导航执行，结束后停止。SSH 凭据只用于本次内存会话。

已盘点 Ubuntu 20.04.6 / ARM64 / Noetic / Python 3.8.10，串口 `/dev/wheeltec_controller -> ttyACM0`，LAN wlan0=192.168.50.123，雷达网卡 eth0=192.168.123.5，雷达192.168.123.124。首次安装前 CCS 工作空间和 ROS master 均不存在。

<a id="deploy-records-ugv-004-deployment-md-配置与生命周期"></a>
## 配置与生命周期

七份 YAML 在 `config/wheeltec_r550p_02`。任务位于 `mission`，共享定位状态 `run/state/relocalization.json`，下载地图 `maps/download`，建图会话 `run/map_stream`；原生 mapper/finalizer 继续在 underlay 的 maps 下写本次会话成果，不覆盖已有地图。

外参使用本机测量的 base_link <- body：平移(0.10,0,0.15)m，pitch=+20度。原生 TF 为了维持树结构发布其逆矩阵，但 CCS 预览须将正向矩阵与 odom <- base_link 位姿相乘。平台 UGV_004 的 remote_mapping/preview_source/remote_artifact 为 odom/odom/map。

V5.1 内部 launch 名带 .launch.xml。基础入口只启动底盘和 Livox；定位 stages 不再重复启动驱动。CCS 二维导航使用原生 GlobalPlanner/TEB、Patchwork++/Terrain Guard 实时障碍及局部 costmap；全局 costmap 为 StaticLayer+InflationLayer，不启动额外地形地图服务。原生源码、标定和其他设备 profile 不改。

<a id="deploy-records-ugv-004-deployment-md-使用与日志"></a>
## 使用与日志

```bash
cd /home/nrc15/ccs_edge_ws
./start_ccs_edge_dev.sh --check
./start_ccs_edge_dev.sh
# 前台 Ctrl+C 有序停止
```

预检不创建运行日志、不启动 ROS 节点。正常启动创建 `logs/<UTC时间_纳秒_PID>`，`logs/latest` 指向最新一次；PID/锁位于 `run/managed`。先停止任务消费和自有导航，发布零速并核对新鲜轮速，再逆序停止组件，最后停止自建 master。共用 master 不清理。视频 YAML 禁用且根脚本不启动视频。

<a id="deploy-records-ugv-004-deployment-md-备份证据与回滚"></a>
## 备份、证据与回滚

本地证据：`artifacts/ugv004_deployment_20260912`；端侧备份：`/home/nrc15/ccs_edge_ws/backups/UGV_004-20260912`。运行清单 `runtime_manifest.json` 包含相对路径、权限和实际传输哈希；规范化前源码哈希单独记录。首次工作空间原不存在。

回滚先有序停止本次流程、保留日志和当前状态；按清单移走本次新增代码/配置并恢复已备份授时配置。原生地图、任务和最新安全状态不能被旧备份覆盖。依赖安装日志记录系统包变更，勿盲目卸载共享依赖。

完整实测见下方追加结果；端侧最终处于停止状态。

<a id="deploy-records-ugv-004-deployment-md-2026-09-12-实测完成与最终状态"></a>
## 2026-09-12 实测完成与最终状态

<a id="deploy-records-ugv-004-deployment-md-安装与源码身份"></a>
### 安装与源码身份

- `rosdep check --from-paths src --ignore-src --rosdistro noetic` 通过；`catkin_make -j1 -DPYTHON_EXECUTABLE=/usr/bin/python3 -DCMAKE_BUILD_TYPE=Release` 成功，构建恰好七个公共包。视频 C++ 节点已编译但未启动。
- 最终 163 个运行文件 SHA-256 全部与交付清单相符；直接及间接 Shell/Python 入口的 LF、无 BOM、权限、Bash/Python 语法检查通过。原始162文件清单和首轮脚本已保存到备份。
- 原生 src 全树排序 SHA-256 清单的聚合摘要，部署前后均为 `7e2e6f3d9c438e8d75a27cd8bce0304871f6148c9b749eaf2a176d0003e4e698`，确认原生源码和标定未被本次部署改动。
- `epgeneral_video_srt_node` 构建产物 SHA-256：`00c014faa41e954559499aedbcbe17b2da52fc63eeba58c29cc6b345c7df09e8`。
- 本地17项 profile/文档回归通过，最终补充的 bringup 禁用视频断言另随新 profile 五项回归通过；文档覆盖八套配置（默认+七设备）、56份 YAML。

<a id="deploy-records-ugv-004-deployment-md-65秒静止输入验收"></a>
### 65秒静止输入验收

| 输入 | 消息数 | 实测频率 | 最大消息年龄 |
| --- | --- | --- | --- |
| /odom | 1301 | 20.00 Hz | 0.075秒 |
| /imu | 1301 | 20.00 Hz | 0.080秒 |
| /PowerVoltage | 109 | 1.67 Hz | 以接收时刻计，消息无header |
| /livox/lidar | 650 | 10.00 Hz | 0.241秒 |
| /livox/imu | 13015 | 200.00 Hz | 0.113秒 |

采样65.089秒，电压末值23.678V。轮速反馈分量最大绝对值0.001，低于静止容差；采样期间 `/cmd_vel` 没有新消息、非零指令计数为零。启动与关闭的零速发布由根脚本成功返回及随后新鲜轮速检查确认。常驻六个CCS节点（含任务适配器）、底盘和雷达在线；无 FAST-LIO、NDT、move_base 或视频节点。

<a id="deploy-records-ugv-004-deployment-md-正式平台接收和存储"></a>
### 正式平台接收和存储

从当前 `CCS_dev` 项目和原有 data 目录启动实际 `ccs_monitor.app.main()`，使用无界面显示后端，被动观察正式 MqttDeviceSource、UdpTelemetryStore，不发送控制任务。实际模块确认 UGV_004 online、电压约23.7V、雷达状态 available；解析结果进入正式内存遥测存储，快照另保存为JSON证据。此次未验收可见UI或视频解码，也不将JSON快照等同于产品新增数据库。

跨启停验收的平台记录：MQTT presence 6、heartbeat 309、status 309；UDP level1 6147、level2 1536、level3 306、heartbeat 306，首末UDP观测跨度393.167秒。上述UDP计数为正式协议成功解码计数，包含下述被存储层拒绝的乱序帧；存储证据另见 online/final 快照。

保留23次 out_of_order 计数，存储层按既有策略拒绝，未产生描述符哈希或未知设备错误。空闲时FAST-LIO/位姿未知、PGM不可用符合无算法、空地图绑定状态。平台观测器偶发Windows文件替换PermissionError，后续快照继续更新，已保留原告警和完整有效快照；无界面Qt也报告OpenGL能力警告，未据此声称UI验收通过。

<a id="deploy-records-ugv-004-deployment-md-生命周期与失败记录"></a>
### 生命周期与失败记录

六项实机检查通过：

1. 运行中 `--check` 保持节点、启动PID、latest和日志目录集合不变。
2. 重复启动返回失败，不改变已有流程或latest。
3. SIGTERM顺序退出，清理自有节点和master。
4. 离线 `--check` 不创建master或新日志，保持latest。
5. 人为终止本次自有MQTT组件后，根脚本以失败退出并清理其他自有节点；复用的测试master仍存活，剩余节点只有rosout。随后仅停止该测试拥有的master。
6. 再次启动成功，SIGINT返回130，有序清理且master退出。

首轮使用4秒 `rostopic pub -1` 检查窗口，零速发布检查超时并中止启动；原日志完整保留。该命令自带3秒latched等待，现使用10秒窗口并保留失败输出，后续全部正常启动、零速确认和退出通过。

系统补装msgpack、paho-mqtt、mavros_msgs及其依赖；apt同时升级13个GStreamer相关包，具体旧/新版本见dependencies.log，未执行系统全量升级或autoremove。timesyncd当前ServerName/ServerAddress均为192.168.50.101，未增加竞争授时服务。

<a id="deploy-records-ugv-004-deployment-md-最终交付"></a>
### 最终交付

端侧工作流已停止，master离线，无startup.pid；此次无界面平台验收进程也已退出并释放端口。日常先启动地面站CCS，确保MQTT/NTP可达，再运行根目录脚本；平台离线时预检会明确失败。

建图/定位/导航本轮仅通过配置、消息、launch和可执行文件静态核验，未运行真实算法、生成地图或执行运动任务。未添加开机自启，未提交或推送Git。

端侧离线文档在 `docs/distribution`，短入口 `docs/wheeltec_r550p_02/DEPLOYMENT.md`。证据在 `docs/evidence/ugv004_deployment_20260912`，运行日志继续保留工作空间logs；记录、文档、运行清单分别可核对哈希。

<a id="deploy-records-ugv-004-deployment-md-核心运行文件摘要"></a>
### 核心运行文件摘要

| 相对工作空间路径 | SHA-256 |
| --- | --- |
| `start_ccs_edge_dev.sh` | `8a0d8eece176aa140e45769336dc8439d57965102f45b4c5bceb2f8ed0226bb4` |
| `scripts/ccs_wheeltec_preflight.py` | `0a5591366f6143cf6fafb04b60f844992c7992689bb2590f0bef3d712ef86e3b` |
| `scripts/ccs_wheeltec_readiness.py` | `eeb73ac9ab0ef57ad17a17e8be6609c05229a84812fcdcb1b665943b106e4d33` |
| `scripts/ccs_sntp_sync.py` | `e7bc6d3e1cf06a441e1963c74b63cb07807a92adfa4d4e1642fcb444b045df3a` |
| `src/EPGeneral_task_control/launch/wheeltec_ccs_2d_navigation.launch` | `8143724c4b009c29e8364c7722f1eb2a3e2be505dafcff5e66e4625623b409b3` |
| `config/wheeltec_r550p_02/map_stream.yaml` | `967ef0326e8cec90f27faa673b1c92cffa869aacc0c6637da0158807fc8a1fa1` |


UGV_004 本次修复见 [2026-09-24 部署记录](UGV004_FIX_20260924.md)。
