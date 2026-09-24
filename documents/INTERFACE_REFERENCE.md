# 端侧接口与配置参考

## 0.14.0 占据图接口

prepare 新增可选 artifact_formats，成果 manifest 支持 ot 角色及 SHA-256。保持旧平台 PGM 三件套契约，拒绝未协商的 OT-only 成果。命令、源文件/会话路径、新鲜度及各机型约束见 [OT 成果接口](OCTOMAP.md)。

整理日期：2026-09-18；源码基线：CCS_dev dbe85904cdbae3d3b837f8816f29d1f030d7bd5a，配套 CCS 0.25.0。

以本仓库 README 和各机型部署指南为当前目录入口。配置无热重载，包内默认配置与设备运行目录配置必须区分。

<a id="documents-interface-reference-md"></a>

<a id="documents-interface-reference-md-端侧设备内接口与配置参考"></a>
# 端侧设备内接口与配置参考

适用产品：CCS 0.24.0；`epgeneral_task_control` 0.6.3；更新日期：2026-09-16。包版本见[端侧 README](../README.md)，操作步骤见[使用手册](USER_MANUAL.md#documents-user-manual-md)。

本册面向设备集成开发者，描述 CCS 包如何调用设备其他工作空间的功能。MQTT、UDP、SRT 消息格式以[地面站通信协议](https://github.com/AADCL/CCS_dev/blob/dbe85904cdbae3d3b837f8816f29d1f030d7bd5a/docs/EDGE_DEVICE_INTERFACES.md)为准。配置 schema、网络 schema 和软件版本是三个独立概念。

填写配置时先查[七套 profile 的完整话题/类型/服务矩阵](INTERFACE_REFERENCE.md#documents-config-topic-reference-md)，再用本册逐键表检查约束。部署经验及从零流程见[部署指南](USER_MANUAL.md#documents-deployment-guide-md)，按设备 ID 的历史见[索引](../README.md)。

<a id="documents-interface-reference-md-1-工作空间与进程边界"></a>
## 1. 工作空间与进程边界

<a id="documents-interface-reference-md-11-ros-环境"></a>
### 1.1 ROS 环境

所有交互节点使用同一个 `ROS_MASTER_URI`，`ROS_IP` 为其他节点可达的本机地址。新终端先 source Noetic，再加载设备 underlay，最后加载 CCS overlay。已有 overlay 用 `--extend`，并以 `rospack find` 检查实际解析路径；复制源码不会自动提供外部依赖。

| profile | 外部工作空间及集成要求 |
| --- | --- |
| Go2 EDU legacy | `/home/nvidia/go2_mid360_nav/catkin_ws` 提供 Livox、LIO、地图 accumulator 和 PGM 工具；CCS 在 `/home/nvidia/ccs_edge_ws` |
| Go2 Robot2 / Robot3 | `/home/unitree/go2_nav_ws` 提供原生控制、Livox、LIO、定位和导航；CCS 在 `/home/unitree/ccs_edge_ws`，由 `EPGeneral_go2_integration` 管理按需算法入口 |
| Scout | 启动脚本依次 source Noetic、RealSense、Scout navigation、livox_fastlio、CCS；依赖 Scout 状态/BMS、Livox、FAST-LIO、TF/pose/cloud adapter 和 move_base |
| Wheeltec | `/home/nrc19/livox_fastlio` 提供底盘、Livox、FAST-LIO、地图工具和导航；CCS 在 `/home/nrc19/ccs_edge_ws` |
| Ground-Air | `/home/bitcq/catkin_ws` 提供算法与 `ground_air_msgs`；`/home/bitcq/ccs_edge_ws` 提供 CCS、阶段控制及局部 override |

算法工作空间不是本仓库的部署目标。已有 profile 中地图输出到算法工作空间的 `maps` 是显式文件接口，不能据此覆盖算法源码。Ground-Air 的重定位子进程局部 prepend `ccs_edge_ws/overrides` 并排除原同名包搜索路径，避免 `car_bringup` 重复资源；不要全局替换 `ROS_PACKAGE_PATH`。

<a id="documents-interface-reference-md-12-功能交互矩阵"></a>
### 1.2 功能交互矩阵

| CCS 包 | 从外部接收 | 向外部输出或调用 | 就绪与故障语义 |
| --- | --- | --- | --- |
| device_config | 无 | 七份 YAML 资源 | 不是节点，不需要 rosrun |
| mqtav | 可配置 ROS 状态、电池、任务摘要 | MQTT presence/heartbeat/status | 未知值保留未知；状态消息新鲜度可代替 MAVROS connected |
| udp_telemetry | Pose、Odometry、IMU、String、任意话题新鲜度及 PGM 文件 | UDP 14560、Bool 链路状态、DiagnosticArray | 单个坏来源隔离；本机 sendto 成功不表示地面站已收到 |
| video_srt | Image 或 CompressedImage | H.264 baseline/MPEG-TS/SRT Listener | 外部相机驱动需独立运行；缺帧及插件异常写日志 |
| map_stream | Livox/IMU 输入探测、PointCloud2、Odometry、TF | 外部建图 launch、保存服务/finalizer、UDP 控制状态及 HTTP 成果 | prepare 校验输入和依赖，start 才进入建图；会话结束释放自身资源 |
| relocalization | 地面站地图归档、定位 TF | 外部定位 launch、initialpose | 栈就绪后发初始位姿；状态文件与实时定位一致 |
| task_control | UDP 任务、执行反馈、适配器的 Odometry/TF | 自定义 command、任务状态、move_base action、停车 Twist | 协调器不直接控制 MAVROS；运动由设备适配器执行 |
| ground_air_control | stage 请求、initialpose | SetSystemStage、LoadMap、Relocalize、阶段状态 | 建图与重定位互斥，按会话归属释放阶段 |
| go2_integration | 原生 Go2 ROS 包、设备标定和栈占用状态 | 建图/导航 launch、互斥锁 | 持久设备由根脚本持有，按需栈不重复启动 Livox 或 SDK bridge |

<a id="documents-interface-reference-md-2-ros-消息服务与-tf"></a>
## 2. ROS 消息、服务与 TF

<a id="documents-interface-reference-md-21-状态遥测与视频"></a>
### 2.1 状态、遥测与视频

MQTT 的 `ros.state/battery` 使用 `package/Message` 动态加载消息类，`mapping` 使用点分字段路径。Scout 来源为 `/scout_status`、`/BMS_status`；Wheeltec 为 `/odom`、`/PowerVoltage`；legacy Go2 用 `/livox/lidar` 新鲜度且禁用电池源；Robot2/Robot3 使用 `/go2/control/enabled`（std_msgs/Bool.data）及 `/go2/battery_state`（sensor_msgs/BatteryState），Robot3 另以周期 `/go2/state/low_state`（go2_control/Go2LowState，3 秒超时）判断连接；Ground-Air 使用 `/mavros/state`、`/mavros/battery`。没有可确认的数据时不能填造电池或飞控状态。

UDP 的 ros_fields/value_status 加载具体消息并读取字段，topic_freshness 使用 AnyMsg 监测到达时间，不能判断 Bool 值。file_status 从状态 JSON 取得配置字段，在根目录检查 path_template（默认 map_id/map.pgm），不订阅示例 topic；disabled 不创建来源。默认诊断输出为 `/epgeneral_udp_telemetry/diagnostics`（diagnostic_msgs/DiagnosticArray），链路状态为 `/epgeneral_udp_telemetry/link/udp_tx`（std_msgs/Bool，latched），可按 launch 覆盖。

视频输入支持 `sensor_msgs/Image`、`sensor_msgs/CompressedImage` 或 RTSP；输出流不使用 ROS 消息，状态另发布 JSON String。运行依赖 appsrc、videoconvert、x264enc、h264parse、mpegtsmux、srtsink。地面站作为 Caller 连接端侧 UDP 9000；YAML 延迟单位为 ms，FFmpeg SRT URL 的 latency 单位为微秒。

<a id="documents-interface-reference-md-22-建图与坐标契约"></a>
### 2.2 建图与坐标契约

输入探测与预览不是同一话题：`ros.inputs` 检查雷达/IMU，`ros.stream` 提供预览点云和配对位姿。配置的消息类型、字段路径及 frame 必须匹配实际消息。点坐标需要按 TF/外参真正变换，不能只改 frame 字符串。

| 后端 | 外部契约 |
| --- | --- |
| go2_accumulator | prerequisites/FAST-LIO launch；原生 `/go2_map_accumulator/save_map`（legacy 名称按 profile 核验）；PCD 转 PGM 工具 |
| scout_finalize | Scout FAST-LIO、pointcloud_mapper、TF/pose adapter；`finalize_map.py` 产出 PCD/PGM/YAML |
| managed_finalize | 与 Scout 生命周期相同，由 `integrations.managed` 指定 Wheeltec 的包、launch 和节点名 |
| ground_air_service | 阶段服务管理原生建图；`/ground_air/mapping/save` 及 save launch 提供地图成果 |

Ground-Air 输入 `/cloud_registered` 在 camera_init，预览需转换为 odom，最终 manifest 声明 map。静态 `odom <- camera_init` 和 `base_link <- body` 由一键脚本持有，stage manager 不重复启动。客户端接受整数 guard 1/2；manager 当前发布 2。缺失、类型错误、未知 guard 均拒绝；stop/abort 仍需匹配 caller/map_id，但不要求 TF 继续存在。

<a id="documents-interface-reference-md-23-重定位与文件协作"></a>
### 2.3 重定位与文件协作

定位栈应订阅 `/initialpose`（geometry_msgs/PoseWithCovarianceStamped），发布配置指定的地图话题和 `map <- odom` TF。先等 map 及 initialpose 订阅者就绪，再发送初始位姿。Scout/Wheeltec 按连续样本稳定窗口判断；Ground-Air 首个有效 TF 即成功，此后每秒回报缓存或新 TF，最多每 30 秒持久化。后续静止或短暂查询失败不会把缓存误判成首样本超时。

地图安装根目录、重定位 `active_map_state_file`、任务适配器读取的同名状态路径、UDP `pgm_file` 的 `state_file/map_root` 必须对齐。状态 schema 2 包含 status/map_id；localized 另有 map_frame、odom_frame、localized_at、map_from_odom（x/y/z/qx/qy/qz/qw）。重启后旧 localized 不作为实时定位；任务需要有效状态及变换。地图文件名按后端为 public_map.pcd 或 cloud_map.pcd，栅格由 map.pgm 与 map.yaml 配对。

<a id="documents-interface-reference-md-24-任务适配器接口"></a>
### 2.4 任务适配器接口

消息真源为 `EPGeneral_task_control/msg/TaskExecutionCommand.msg` 和 `TaskExecutionFeedback.msg`。command 默认话题 `/epgeneral_task_control/execution_command`，feedback 默认 `/epgeneral_task_control/execution_feedback`，摘要为 `/epgeneral_task_control/task_status`（std_msgs/String）。

命令常量为 SCHEDULE=1、CANCEL=2、STOP=3、PREPARE=4、UNLOAD=5、EMERGENCY_STOP=6。适配器必须保持 request/task/subtask/device/execution/revision 身份对应，读取协调器持久化 XML，按 UTC scheduled_at 执行并回报真实状态及进度。完整字段及类型以随包 .msg 为准，可用 `rosmsg show epgeneral_task_control/TaskExecutionCommand` 和对应 Feedback 检查构建结果。

导航适配器调用 `move_base_msgs/MoveBaseAction`，读取 nav_msgs/Odometry 和 TF，向配置的 zero_velocity_topic 发布 geometry_msgs/Twist 停车。`adapter.odom_topic` 是适配器反馈、航点进度和位姿新鲜度输入；可选的 `adapter.navigation_odom_topic` 只作为受管导航 launch 的 `odom_topic` 参数，供局部规划器读取底盘速度，两者不能因消息类型相同而混用。commit 后准备并常驻导航；常规 stop 复用导航进程，删除/卸载按状态清理。PGM 可通行性、TF、反馈超时和 UTC 校验不应被自定义适配器跳过。

以下为当前 .msg 的全部业务字段；同名身份字段在 command 和 feedback 中均为 string，revision 均为 uint32。

| 消息 | 字段 | ROS 类型 | 定义 |
| --- | --- | --- | --- |
| 两者 | request_id、task_id、subtask_id、device_id、execution_id | string | 请求、任务、子任务、设备和执行身份，反馈必须对应当前请求 |
| 两者 | revision | uint32 | 任务修订号 |
| command | action | uint8 | 前述六个命令常量 |
| command | xml_path | string | 协调器持久化的任务 XML 绝对路径，执行器需可读 |
| command | frame_id、map_id | string | 航点坐标系与地图身份 |
| command | scheduled_at | time | ROS time 表示的 UTC 计划开始时间，不是本地字符串 |
| feedback | state | string | preparing/ready/failed、scheduled/running 及执行终态，按请求阶段回报 |
| feedback | waypoint_index、waypoint_count | int32 | 当前航点索引及总数 |
| feedback | progress | float64 | 执行进度值，与地面站协议定义一致 |
| feedback | position | geometry_msgs/Point | x/y/z，任务参考系内位置，m |
| feedback | error_code、message | string | 结构化失败原因及诊断说明 |

<a id="documents-interface-reference-md-原生-go2-的控制与恢复"></a>
#### 原生 Go2 的控制与恢复

| 配置键/接口 | 名称示例 | 类型及确认条件 |
| --- | --- | --- |
| adapter.navigation_reset_service | /go2_navigation_supervisor/reset | std_srvs/Trigger；response.success 必须 true，不能用 Empty |
| adapter.control_enable_service | /go2_sdk_bridge_real/enable | std_srvs/SetBool；data=false 停用，data=true 仅按调度门控；响应后确认状态 |
| adapter.control_enabled_topic | /go2/control/enabled | std_msgs/Bool，锁存；data 不作为周期心跳 |
| adapter.control_diagnostics_topic | /go2/diagnostics | diagnostic_msgs/DiagnosticArray；默认匹配 GO2 SDK bridge 的 motion_enabled，新鲜度由 header/到达检查 |
| adapter.localization_ok_topic | /localization/ok | std_msgs/Bool，必须新鲜为 true |
| 私有 reset_emergency_stop 服务 | /epgeneral_navigation_task_adapter/reset_emergency_stop | std_srvs/Trigger；无活动准备/执行/控制过渡且持续 disabled 才清锁，不使能 |

可选 adapter.control_diagnostics_status 与 adapter.control_diagnostics_key 改变诊断匹配名/键，默认 GO2 SDK bridge / motion_enabled，不能选择无关状态来绕过控制确认。持久标记由 adapter.emergency_stop_state_file 指定，协调器和适配器读取同一文件。损坏标记按锁存处理，在协商/下发准备/提交时返回已有 EMERGENCY_STOP_LATCHED；传输期间出现也拒绝。此失败不自动重试，复位成功后重新下发；可恢复定位错误仍可重试。协议格式未改。

普通 STOP/UNLOAD 需要 disable RPC 成功及新鲜状态。内部 UNLOAD/request_id=shutdown-unload 可先于适配器 ROS 关闭信号；它与 close 共用幂等收尾入口，识别 is_shutdown_requested 回调阶段。仅收尾上下文同时取得控制过渡锁和 RPC 锁、确认无未完成调用且 disabled 新鲜时才允许跳过重复 RPC；否则进入有界严格停用，真实失败仍锁存。当前源码允许未永久关闭的适配器在卸载完成后重新 PREPARE，但仍检查锁存/地图/定位；该后续修订尚未部署。以上不新增消息、服务或 YAML 键。排查与验收见 [GO2 经验](devices/go2/DEPLOYMENT_GUIDE.md#documents-go2-deployment-lessons-md)，不能删除文件代替人工复位。

<a id="documents-interface-reference-md-ugv_003-wheeltec-控制权"></a>
#### UGV_003 Wheeltec 控制权

| 配置键/接口 | 名称 | 类型及确认条件 |
| --- | --- | --- |
| adapter.odom_topic | /fastlio_odom | nav_msgs/Odometry；适配器的地图位姿、执行反馈和新鲜度来源 |
| adapter.navigation_odom_topic | /odom | nav_msgs/Odometry；传给 move_base/TEB 的轮式底盘速度里程计，不替代定位位姿 |
| adapter.control_enable_service | /wheeltec_control/enable | std_srvs/SetBool；true 先确认实时定位并取得驱动和安全门控制权，false 停车后归还硬件遥控 |
| adapter.control_stop_service | /wheeltec_control/stop | std_srvs/Trigger；控制故障或急停锁定停车 |
| adapter.navigation_reset_service | /wheeltec_control/reset | std_srvs/Trigger；人工确认故障处理后复位，不直接执行任务 |
| adapter.clear_costmaps_service | /move_base/clear_costmaps | std_srvs/Empty；控制仍停用时清除上次导航残留，失败即拒绝接管 |
| adapter.clear_costmaps_settle_seconds | 0.30 | 清理后稳定期；期间持续检查取消、定位及手动状态 |
| adapter.control_enabled_topic | /wheeltec_control/enabled | std_msgs/Bool；驱动与安全门均确认后才为 true |
| adapter.localization_ok_topic | /wheeltec_control/localization_ok | std_msgs/Bool；活动地图状态为 localized 且 `/fastlio_odom` 新鲜 |
| adapter.control_heartbeat_topic | /wheeltec_driver/control_heartbeat | std_msgs/Empty；自主状态 10 Hz，驱动 0.5 秒未收到即锁停 |
| control_authority.driver_enable_service | /wheeltec_robot/set_autonomous | std_srvs/SetBool；切换驱动串口速度写入权 |
| control_authority.driver_stop/reset_service | /wheeltec_robot/stop、/wheeltec_robot/reset_authority | std_srvs/Trigger；锁停与人工复位归还手动控制 |
| control_authority.safety_arm/stop/reset_service | /wheeltec_safety/arm、stop、reset | std_srvs/Trigger；速度安全门生命周期 |

任务速度固定经过 `/move_base -> /nav_cmd_vel -> /wheeltec_safety -> /wheeltec_driver/cmd_vel`。专用导航入口固定 TEB `max_vel_x=0.20`、`max_vel_theta=0.40`、`max_vel_x_backwards=0.10` 和 `weight_kinematics_forward_drive=1000`。安全门 0.1.2 将完整检查周期与感知提交串行化，`costmap_lethal_threshold=100` 并过滤与实测车体相交的已知致命单元；未知单元和实时点云继续阻断。`linear_deadband=0.02` 容忍求解漂移，`allow_reverse=false` 仍使所有负线速度在输出前归零。基础栈与任务准备阶段保持手动控制权；正常终态先停车再归还硬件遥控。

`NAVIGATION_ACTION_FAILED`、`NAVIGATION_GOAL_PREEMPTED`、`NAVIGATION_GOAL_REJECTED`、`NAVIGATION_PLAN_FAILED` 和 `NAVIGATION_WAYPOINT_TIMEOUT` 只表示本次路线执行失败；适配器取消目标、正常停用并返回手动控制，不创建持久急停。显式急停、`NAVIGATION_ACTION_LOST`、控制状态或定位失效、导航进程退出、停车或停用确认失败仍调用 fault stop 并锁存。动作进入终态后还会再次确认控制心跳，避免把终态轮询间隙中的控制失联误报为普通导航失败或成功。已有锁存不会因升级或普通导航失败分类变化而自动清除，必须按使用手册确认两个控制状态均为 false 后人工复位。


<a id="documents-interface-reference-md-25-ground-air-专属服务"></a>
### 2.5 Ground-Air 专属服务

| 接口 | 类型与已核实字段 |
| --- | --- |
| `/ground_air/system/set_stage` | ground_air_msgs/SetSystemStage；请求 stage/map_id/timeout，响应 success/message/active_stage |
| `/ground_air/system/stage` | std_msgs/UInt8，latched；0=基础、1=建图、2=重定位 |
| `/ground_air/system/stage_detail` | std_msgs/String，latched，阶段诊断详情 |
| `/ground_air/load_map` | ground_air_msgs/LoadMap，由初始位姿适配器加载地图 |
| `/ground_air/relocalize` | ground_air_msgs/Relocalize，适配 initialpose，use_initial_guess=true |

外部 .srv 不在本仓库，设备升级后先执行 `rossrv show ground_air_msgs/SetSystemStage`、`rossrv show ground_air_msgs/LoadMap`、`rossrv show ground_air_msgs/Relocalize` 核验，不能把本表当作完整外部消息定义。建图 caller 为 `/ccs_mapping_stage_<session>`，阶段由 caller/map_id 共同归属；保持幂等与互斥。旧 `deploy_stage_manager_update.sh` 和 `car_bringup_scripts` 是 legacy underlay 路径，当前新部署使用 CCS 控制包。

<a id="documents-interface-reference-md-3-配置入口覆盖与修改"></a>
## 3. 配置入口、覆盖与修改

| 节点 | 路径选择与覆盖规则 |
| --- | --- |
| mqtav | launch 的 config_file/device_config_file/log_dir 转为 CLI；业务值直接读 YAML |
| relocalization | launch 的 config_file/device_config_file 转为 CLI；阶段环境只对子进程生效 |
| map_stream | 私有 mapping_config_file/device_config_file 选择 YAML |
| task_control | 私有 task_config_file/device_config_file；适配器读取同一配置 |
| udp_telemetry | 显式 config_dir 或完整文件对读取 YAML；仅非空 destination_host/destination_port/link_status_topic/diagnostics_topic 覆盖 |
| video_srt | device YAML 加载到全局 /edge_device；video YAML 加载到节点私有参数，C++ 启动读取 |
| ground_air_control | 无独立 YAML；launch 参数控制 map_id/maps_root/service_wait_timeout/relocalize_timeout |

所有节点启动读取配置，没有热重载。除明确列出的覆盖项外，`rosparam set` 不会改变直接读取 YAML 的运行节点。

设备脚本入口修改 `<CCS工作空间>/config/<profile>/*.yaml`；单包默认入口修改 `$(rospack find epgeneral_device_config)/config/*.yaml`，或显式传入文件。profile 原件在仓库 `devices/<机型>/profiles/<profile>/config`，发布 ZIP 和设备实际运行配置是不同层次。

修改顺序：备份实际运行配置；停止受影响会话/节点；修改 YAML；用包解析器校验；确认 ID、地址、端口和跨包地图路径一致；重启；检查 ROS 数据及地面站接收。示例见手册。地面站地址变化需同步 MQTT/network 配置及授时服务器；仅设 CCS_GROUND_STATION_IP 不会重写所有 YAML，Ground-Air 脚本还存在固定地址与诊断话题，需要逐项同步。

<a id="documents-interface-reference-md-31-参数表约定"></a>
### 3.1 参数表约定

后续表格按文件划分，键均为 YAML 完整路径；`[]` 表示列表元素。值栏“必填；示例”表示文件必须提供该值，并非加载器缺省。路径示例依 profile 而异；默认配置不能直接投入设备。每张表的参数修改位置就是该文件的实际运行副本，生效方式均为重启对应节点；身份变更需重启全部通信节点。

`deployment.state` 为可选说明元数据。视频 0.2.0 的顶层 `enabled` 实际控制启停，并兼容旧 `deployment.enabled`，两者冲突时拒绝启动；其他包按各自加载器定义处理。视频已声明字段进行校验，不推定其他包采用相同规则。

<a id="documents-interface-reference-md-4-deviceyaml"></a>
## 4. device.yaml

| 键 | 类型 / 默认或要求 | 定义与约束 |
| --- | --- | --- |
| `schema_version` | int；必填 1 | 共享身份配置 schema |
| `device.id` | string；必填 | 唯一非空设备 ID，与地面站登记、主题、任务及会话一致 |
| `device.ip` | string；必填 | 设备自身 IP，不能填地面站地址；整套建图/任务使用 IPv4。MQTT 单包解析器也支持 IPv6，不代表整套支持 IPv6 |

<a id="documents-interface-reference-md-5-epgeneral_mqtavyaml"></a>

UAV 补充字段：

| 参数 | 说明 |
| --- | --- |
| `deployment.enabled` | UAV profile 配置项，见部署指南约束。 |
| `deployment.state` | UAV profile 配置项，见部署指南约束。 |

## 5. epgeneral_mqtav.yaml

0.5.0 新增配置版本 2：`ros.connection_mode` 为 field/freshness/heartbeat/disabled；启用电池时必须指定 `percentage_unit`。以下旧配置说明仍兼容；新增字段、换算及完整迁移方法见 [MQTT 包说明](../epgeneral_mqtav/README.md)。

省略 schema_version 时按旧版本 1 加载；新 profile 使用版本 2。以下频率为 Hz，时间为秒。状态/电池 mapping 支持字段路径、换算对象或 null；null 表示不提供该项。

| 键 | 类型 / 默认或要求 | 定义与约束 |
| --- | --- | --- |
| `schema_version` | int；新配置为 2 | 旧配置省略时按 1 加载 |
| `ros.connection_mode` | field/freshness/heartbeat/disabled；版本 2 必填 | 分别为字段、状态新鲜度、独立周期源、禁用 |
| `ros.state.enabled` | bool；默认 true | false 时不订阅状态 |
| `ros.battery.percentage_unit` | fraction/percent/legacy_auto | 版本 2 启用电池时必填；换算后的百分比单位 |
| `mqtt.ground_station_ip` | string；必填 | Broker 的 IPv4/IPv6 地址，不能填 DNS 名 |
| `mqtt.port` | int；必填，示例 1883 | 1..65535，Broker TCP 端口 |
| `mqtt.client_id_prefix` | string；必填，示例 mqtav- | 非空，与 device.id 组成客户端 ID |
| `mqtt.qos` | int；必填，示例 1 | 0 或 1 |
| `mqtt.keepalive_seconds` | int；必填，示例 10 | 1..3600 |
| `mqtt.heartbeat_hz` | number；必填，示例 1 | 大于 0 且不超过 100 |
| `mqtt.telemetry_hz` | number；必填，示例 1 | 状态发送频率，大于 0 且不超过 100 |
| `mqtt.topics.presence` | string；必填 | 示例 mqtav/{device_id}/presence |
| `mqtt.topics.heartbeat` | string；必填 | 示例 mqtav/{device_id}/heartbeat |
| `mqtt.topics.status` | string；必填 | 示例 mqtav/{device_id}/status；三主题仅支持 device_id 模板，禁用 +/# 通配符 |
| `ros.node_name` | string；必填 | 非空 ROS 节点名 |
| `ros.connection.topic` | string；提供 connection 时必填 | 独立周期状态输入；Go2 native 使用 /go2/state/low_state 判断连接，不依赖 latched armed 状态 |
| `ros.connection.message_type` | string；提供 connection 时必填 | package/Message；Go2 native 为 go2_control/Go2LowState |
| `ros.connection.timeout_seconds` | number；默认 3.0 | 0.1..3600 秒；独立连接输入的新鲜度阈值，省略 connection 时沿用 ros.state 的连接判断 |
| `ros.state.topic` | string；必填 | 以 / 开头的状态输入话题 |
| `ros.state.message_type` | string；必填 | package/Message，必须在已 source 工作空间中可加载 |
| `ros.state.connected_on_message` | bool；旧配置默认 false | 旧配置 true 时以消息新鲜度判断 connected；版本 2 以 connection_mode 为准 |
| `ros.state.timeout_seconds` | number；默认 3.0 | freshness 或旧配置 connected_on_message=true 时生效，0.1..3600 秒 |
| `ros.state.mapping.connected` | string/null；默认 connected | connected 字段路径；新鲜度模式可置 null |
| `ros.state.mapping.armed` | string/null；默认 armed | 解锁状态来源 |
| `ros.state.mapping.system_status` | string/null；默认 system_status | 系统状态来源 |
| `ros.state.mapping.mode` | string/null；默认 mode | 模式来源 |
| `ros.battery.enabled` | bool；默认 true | false 时不订阅电池，不伪造电量 |
| `ros.battery.topic` | string；启用时必填 | 绝对话题 |
| `ros.battery.message_type` | string；启用时必填 | package/Message |
| `ros.battery.mapping.percentage` | string/null；默认 percentage | 原始电池百分比字段，沿用消息语义 |
| `ros.battery.mapping.voltage` | string/null；默认 voltage | 电压字段，V |
| `ros.battery.mapping.current` | string/null；默认 current | 电流字段，A |
| `ros.mission.enabled` | bool；默认 false | 是否采集可选任务摘要，不启动任务控制器 |
| `ros.mission.topic` | string；启用时必填 | 绝对话题 |
| `ros.mission.message_type` | string；启用时必填 | package/Message |
| `ros.mission.field_path` | string；启用时必填 | 非空任务文本路径，String 通常为 data |

<a id="documents-interface-reference-md-6-udp_telemetryyaml"></a>
## 6. udp_telemetry.yaml

name/display_name/type/level 共同决定 SHA-256 descriptor_hash；source 与设备身份不参与该 hash。修改公共定义须同步地面站，修改来源无需改变接收协议。配置 schema 与线协议版本独立。详见 [UDP 重构与迁移](UDP_TELEMETRY_GENERIC.md)。

| 键 | 类型 / 默认或要求 | 定义与约束 |
| --- | --- | --- |
| `schema_version` | int；1 或 2，新配置使用 2 | 配置 schema；schema 2 拒绝未知配置键，线协议仍是 schema 1 |
| `protocol_id` | string；必填 | 必须 ccs-udp-telemetry-v1 |
| `network.destination_host` | string；必填 | IPv4/IPv6 字面地址，不解析 DNS；显式 launch 参数可覆盖 |
| `network.destination_port` | int；必填 | 1..65535，常用 14560；显式 launch 参数可覆盖 |
| `network.max_datagram_bytes` | int；16384 | 512..65507，最终数据报大小上限 |
| `runtime.link_status_topic` | string；/epgeneral_udp_telemetry/link/udp_tx | 输出 latched std_msgs/Bool；支持 {device_id} |
| `runtime.diagnostics_topic` | string；/epgeneral_udp_telemetry/diagnostics | 输出 DiagnosticArray；支持 {device_id} |
| `descriptors[].name` | string；必填 | 非空且唯一，地面站部分名称有业务语义 |
| `descriptors[].display_name` | string；必填 | 显示名，参与 hash |
| `descriptors[].type` | enum；必填 | pose/imu/pointcloud_status/availability/text_status |
| `descriptors[].level` | int；必填 | pose/imu 为 1=20 Hz；pointcloud_status 为 2=5 Hz；availability/text_status 为 3=1 Hz |
| `descriptors[].source.mode` | enum；schema 2 必填 | ros_fields/topic_freshness/value_status/file_status/disabled；详见通用化说明 |
| `descriptors[].source.kind` | string；兼容项 | 只支持 pgm_file，须搭配 file_status；schema 1 未声明 mode 时据此推断 |
| `descriptors[].source.topic` | string；ROS 源必填 | 绝对话题名，支持 {device_id}；file_status 不使用此键 |
| `descriptors[].source.message_type` | string；字段源必填 | package/Message；ros_fields/value_status 预检消息类；topic_freshness 使用 AnyMsg |
| `descriptors[].source.queue_size` | int；50 | ROS 订阅队列，1..10000 |
| `descriptors[].source.max_samples` | int；1000 | 每来源缓存 1..100000；超限淘汰最旧样本并计数 |
| `descriptors[].source.aggregation` | enum；pose/imu 默认 mean，其他 latest | pose/imu 支持 mean/latest，文本与值状态仅 latest |
| `descriptors[].source.stale_policy` | enum；schema 2 invalidate，schema 1 hold | ros_fields/value_status 的过期策略；hold 明确保留最近值 |
| `descriptors[].source.max_age_seconds` | number；默认 timeout_seconds 或 3 | invalidate 的过期阈值，有限正数且不超过 3600 秒 |
| `descriptors[].source.timeout_seconds` | number；点云 1，状态/文本 3 | topic_freshness 与文本可用性阈值；字段源可回退 max_age_seconds，范围 (0,3600] |
| `descriptors[].source.mapping.position` | string 或 x/y/z 字典；pose.position | 位置点分路径；Odometry 通常为 pose.pose.position；字典为逐分量路径 |
| `descriptors[].source.mapping.orientation` | string 或 x/y/z/w 字典 | pose 默认 pose.orientation，imu 默认 orientation；四元数分量 |
| `descriptors[].source.mapping.angular_velocity` | string 或 x/y/z 字典；angular_velocity | IMU 角速度路径 |
| `descriptors[].source.mapping.linear_acceleration` | string 或 x/y/z 字典；linear_acceleration | IMU 加速度路径 |
| `descriptors[].source.mapping.value` | string；data | 文本、Bool 或枚举的公开点分字段，不支持表达式/数组下标 |
| `descriptors[].source.units.position` | enum；schema 2 的 pose 必填 | m/cm/mm，输出 m |
| `descriptors[].source.units.angular_velocity` | enum；schema 2 的 imu 必填 | rad/s 或 deg/s，输出 rad/s |
| `descriptors[].source.units.linear_acceleration` | enum；schema 2 的 imu 必填 | m/s2 或 g，输出 m/s2，1g=9.80665m/s2 |
| `descriptors[].source.expected_frame` | string；可选 | 校验 header.frame_id；不执行 TF 或坐标变换 |
| `descriptors[].source.values` | 标量到状态的字典 | value_status 使用，值只能 available/unavailable/unknown；按标量类型精确匹配，未匹配 unknown |
| `descriptors[].source.values.True` | YAML true；默认 available | Bool true 的映射，键为布尔而非字符串 |
| `descriptors[].source.values.False` | YAML false；默认 unavailable | Bool false 的映射，消息到达不会将其变成 available |
| `descriptors[].source.text_limit` | int；128 | 文本截断字符数，范围 1..128 |
| `descriptors[].source.state_file` | string；file_status 必填 | 状态 JSON 的绝对或 ~/ 路径，支持 {device_id}，上限 1 MiB |
| `descriptors[].source.map_root` | string；file_status 必填 | 成果根目录，绝对或 ~/ 路径，支持 {device_id}，禁止符号链接 |
| `descriptors[].source.state_field` | string；map_id | 状态 JSON 内地图 ID 的点分字段路径 |
| `descriptors[].source.path_template` | string；{map_id}/map.pgm | 受限相对文件路径，仅支持 {map_id}，可改为 OT 等文件；拒绝路径穿越/符号链接/非普通文件 |

新模板使用过期失效；共享及八份历史 profile 显式保留 hold。预检先于 ROS/socket 建立，未知消息类型或字段导致启动失败。NaN/Inf、无效四元数及单项快照失败隔离到对应 descriptor，disabled 输出 valid=false。文本 hold 超过 timeout_seconds 后保留 value 但 status 为 unavailable。

<a id="documents-interface-reference-md-7-videoyaml"></a>
## 7. video.yaml

视频 0.2.0 统一由配置解析器校验；schema 2 必须显式选择输入模式。修改后重启。见 [通用化迁移说明](VIDEO_SRT_GENERIC.md)。

| 键 | 类型 / 默认 | 定义与约束 |
| --- | --- | --- |
| `image_topic` | string；/camera/image_raw | 输入相机话题 |
| `image_message_type` | string；sensor_msgs/Image | 仅支持 Image 或 CompressedImage |
| `output_width` | int；640 | 输出宽度 16..3840，偶数；优先于 image_width |
| `output_height` | int；480 | 输出高度 16..2160，偶数；优先于 image_height |
| `image_width` | int；640 | 兼容别名，仅 output_width 缺失时读取 |
| `image_height` | int；480 | 兼容别名，仅 output_height 缺失时读取 |
| `framerate` | int；30 | 输出帧率 Hz，1..120 |
| `srt_bind_address` | string；0.0.0.0 | 本机 Listener 绑定地址 |
| `srt_port` | int；9000 | UDP 端口，1..65535 |
| `srt_latency_ms` | int；120 | SRT 延迟，20..8000 毫秒 |
| `bitrate_kbps` | int；2000 | 编码码率 100..20000 kbps |
| `rotation_degrees` | int；0 | SRT 编码前的视频旋转；仅允许 0 或 180，不改变输入 ROS 图像 |
| `frame_timeout_seconds` | number；5.0 | 缺帧重建阈值 0.1..3600 秒；RTSP 缺省 8 秒 |
| `enabled` | bool；true | false 时视频和相机入口成功退出，不加载运行依赖 |
| `camera_model` | string；可选元数据 | profile 相机说明，当前 C++ 不读取 |
| `deployment.state` | string；可选元数据 | 部署状态说明 |
| `deployment.enabled` | bool；兼容旧格式 | 与 enabled 冲突时拒绝启动 |

<a id="documents-interface-reference-md-8-map_streamyaml"></a>

UAV 补充字段：

| 参数 | 说明 |
| --- | --- |
| `input_mode` | 输入模式；UAV 使用 rtsp，原 ROS 图像 launch 保留。 |
| `rtsp_codec` | h264 或 h265，UAV 为 h265。 |
| `rtsp_uri` | 真实 A8 RTSP 地址。 |


| 键 | 类型 / 默认 | 定义与约束 |
| --- | --- | --- |
| `schema_version` | int；2 | 新配置显式模式；兼容 schema 1 |
| `rtsp_uri_env` | string；可选 | URI 环境变量名，与 rtsp_uri 互斥；诊断输出脱敏 |
| `rtsp_transport` | string；tcp | tcp 或 udp |
| `rtsp_latency_ms` | int；100 | RTSP 缓冲 0..10000 毫秒 |
| `runtime.status_topic` | string；~status | std_msgs/String JSON 状态，支持 {device_id} |
| `runtime.reconnect_interval_seconds` | number；3.0 | 0.1..300 秒，运行中故障重建间隔 |
| `runtime.decoder_preload` | list；[] | 绝对库路径；仅需要的平台配置 |
| `capture.enabled` | bool；false | 仅 camera.launch 读取并启动驱动 |
| `capture.package` | string | 驱动 ROS 包名 |
| `capture.launch` | string | 驱动 launch 文件名 |
| `capture.args` | mapping；{} | 标量 roslaunch 参数，不执行 shell |
| `capture.arg_env` | mapping；{} | launch 参数名映射环境变量，非空环境值优先 |
| `capture.args.color_width` / `capture.args.color_height` / `capture.args.color_fps` | int | Go2 RGB 输入尺寸、帧率 |
| `capture.args.enable_color` / `capture.args.enable_depth` / `capture.args.enable_infra` / `capture.args.enable_infra1` / `capture.args.enable_infra2` | bool | Go2 图像流开关 |
| `capture.args.enable_gyro` / `capture.args.enable_accel` / `capture.args.publish_tf` | bool | Go2 相机惯性/TF 开关 |
| `capture.arg_env.serial_no` | string | Go2 为 CCS_D435_SERIAL，未设则自动选相机 |
| `capture.args.camera_ip` / `capture.args.image_topic` | string | Ground-Air A8 驱动地址和输出话题 |

## 8. map_stream.yaml

0.14.0 新增可选 OT 配置，默认不启用任何未知的设备命令：

| 参数 | 默认 / 约束 |
|---|---|
| `artifacts.ot_path` | `{session_dir}/map.ot`，必须与 PCD 同目录且位于当前会话内 |
| `artifacts.source_ot_path` | 可选，经核实的原生功能包源路径，支持会话模板变量 |
| `integrations.occupancy.command` | 可选，导出程序 argv 数组，支持 `{pcd_path}`、`{ot_path}` 等路径占位符 |
| `integrations.occupancy.check_command` | 配置导出命令时必填，预检查 argv 数组 |

成果组合、旧平台协商、新鲜度和机型约束见 [OT 接入说明](OCTOMAP.md)。

配置 schema=6，协议为 ccs-map-stream-v2。除明确写“默认/可选”的项外，下表均必须提供；数值示例来自公共模板，设备 profile 可能不同。backend 不会消除基础 integrations 配置结构，保留 profile 中的兼容占位字段，勿自行删除。

<a id="documents-interface-reference-md-81-通信输入与处理"></a>
### 8.1 通信、输入与处理

| 键 | 类型 / 值 | 定义与约束 |
| --- | --- | --- |
| `schema_version` | int；6 | 配置 schema |
| `protocol_id` | string；ccs-map-stream-v2 | 与地面站一致 |
| `network.bind_host` | string；0.0.0.0 | 本地 IP，可为 unspecified |
| `network.control_port` | int；14561 | 1..65535，控制接收 |
| `network.ground_station_ip` | string；按设备 | 有效且非 unspecified 的 IP |
| `network.data_port` | int；14562 | 1..65535，状态上行；prepare 可协商 return_host/return_port |
| `network.max_datagram_bytes` | int；1400 | 512..1400 |
| `http.bind_host` | string；0.0.0.0 | HTTP 本地绑定 |
| `http.port` | int；14600 | 1..65535，预览/成果下载 |
| `http.token_ttl_seconds` | number；900 | 正秒数，下载令牌有效期 |
| `ros.inputs.lidar.topic` | string；/livox/lidar | 原始雷达预检话题 |
| `ros.inputs.lidar.message_type` | string；按 profile | 雷达具体 ROS 消息类 |
| `ros.inputs.lidar.frame` | string；按 profile | 原始雷达 frame |
| `ros.inputs.imu.topic` | string；/livox/imu | IMU 预检话题 |
| `ros.inputs.imu.message_type` | string；sensor_msgs/Imu | 固定预期类型 |
| `ros.inputs.imu.frame` | string；按 profile | IMU frame 配置 |
| `ros.stream.cloud.topic` | string；按 profile | 实际预览点云话题 |
| `ros.stream.cloud.message_type` | string；sensor_msgs/PointCloud2 | 固定预期类型 |
| `ros.stream.cloud.frame` | string；按 profile | 点云源 frame |
| `ros.stream.cloud.coordinates` | enum；map 或 sensor | 点的真实坐标语义 |
| `ros.stream.pose.topic` | string；按 profile | 点云配对位姿 |
| `ros.stream.pose.message_type` | string；nav_msgs/Odometry | 固定预期类型 |
| `ros.stream.pose.position_path` | string；pose.pose.position | 位置信息字段路径 |
| `ros.stream.pose.orientation_path` | string；pose.pose.orientation | 四元数字段路径 |
| `ros.frames.map` | string；按 profile | 建图位姿参考帧 |
| `ros.frames.preview` | string；odom | 上传预览参考帧；Go2 必须与 map 不同 |
| `ros.frames.body` | string；按 profile | 设备本体帧 |
| `ros.frames.sensor` | string；按 profile | 传感器帧 |
| `ros.body_from_sensor.x`、`ros.body_from_sensor.y`、`ros.body_from_sensor.z` | number；标定值 | sensor 到 body 平移，m，有限值 |
| `ros.body_from_sensor.qx`、`ros.body_from_sensor.qy`、`ros.body_from_sensor.qz`、`ros.body_from_sensor.qw` | number；标定值 | 有限四元数，范数至少 1e-6，读取时归一化 |
| `sync.tolerance_seconds` | number；0.05 | 点云/位姿时间容忍，0 < 值 <= 1 秒 |
| `sync.pose_buffer_size` | int；100 | 2..10000 个样本 |
| `sync.preview_transform_timeout_seconds` | number；0.20 | 0 < 值 <= 5 秒 |
| `preprocess.sample_window_seconds` | number；1.0 | 正秒数，点云聚合窗口 |
| `preprocess.preview_transport` | string；pcd_fragment_http | 当前预览使用 HTTP PCD 分片描述符 |
| `preprocess.min_range_m` | number；0.30 | >=0，且小于 max_range_m |
| `preprocess.max_range_m` | number；100 | 正米数 |
| `preprocess.voxel_size_m` | number；0.05 | 正米数，体素下采样 |

<a id="documents-interface-reference-md-82-生命周期与资源"></a>
### 8.2 生命周期与资源

| 键 | 类型 / 值 | 定义与约束 |
| --- | --- | --- |
| `timeouts.prepare_probe_timeout_seconds` | number；1.5 | 正秒数，输入预检 |
| `timeouts.integration_check_timeout_seconds` | number；8 | 正秒数，外部命令检查 |
| `timeouts.ready_timeout_seconds` | number；60 | 正秒数，准备状态有效窗口 |
| `timeouts.input_timeout_seconds` | number；3 | 正秒数，数据源超时 |
| `timeouts.command_cache_seconds` | number；60 | 正秒数，幂等命令缓存 |
| `timeouts.artifact_poll_seconds` | number；0.5 | 正秒数，成果稳定性轮询 |
| `timeouts.artifact_stable_polls` | int；2 | 2..100，连续稳定次数 |
| `limits.max_frame_points` | int；200000 | 正数，单帧点上限 |
| `limits.max_window_points` | int；1000000 | 不小于 max_frame_points |
| `limits.max_decompressed_bytes` | int；2400000 | 至少 max_frame_points × 12 |
| `limits.max_artifact_bytes` | int；4294967296 | 1024..17179869184 字节 |
| `limits.min_free_bytes` | int；5368709120 | 至少 1024 字节；Ground-Air 示例为 1073741824 |
| `limits.command_output_bytes` | int；16384 | 256..1048576，外部命令输出截取上限 |
| `limits.max_preview_fragment_bytes` | int；8388608 | 1024..1073741824，单预览文件大小 |
| `limits.max_pending_preview_fragments` | int；4 | 1..64，待处理队列上限 |
| `limits.max_unacked_preview_fragments` | int；16 | 1..256，未确认预览上限 |
| `artifacts.workspace_root` | string；按 profile | 可写会话工作目录，展开 ~ |
| `artifacts.accumulator_pcd_path` | string；按 profile | Go2 accumulator 原始输出路径 |
| `artifacts.source_pcd_path` | string；按 profile | 外部生成工具原始 PCD |
| `artifacts.source_pgm_path` | string；按 profile | 外部生成工具原始 PGM |
| `artifacts.source_yaml_path` | string；按 profile | 外部生成工具原始 YAML |
| `artifacts.archive_root` | string；按 profile | 外部成果归档根目录 |
| `artifacts.pcd_path` | string；{session_dir}/map.pcd | 会话内 PCD 模板 |
| `artifacts.pgm_path` | string；{session_dir}/map.pgm | 会话内 PGM 模板 |
| `artifacts.yaml_path` | string；{session_dir}/map.yaml | 会话内 YAML 模板 |
| `artifacts.frame` | string；默认 ros.frames.map | 最终成果 manifest frame，profile 常为 map |
| `deployment.state`、`deployment.enabled` | string / bool；可选 | 说明元数据，无启停作用 |

<a id="documents-interface-reference-md-83-外部程序配置"></a>
### 8.3 外部程序配置

| 键 | 类型 / 默认或要求 | 定义与约束 |
| --- | --- | --- |
| `integrations.backend` | enum；默认 go2_accumulator | go2_accumulator/scout_finalize/managed_finalize/ground_air_service |
| `integrations.mapping_prerequisites.setup_file` | string；必填 | prerequisites underlay setup.bash |
| `integrations.mapping_prerequisites.launch_file` | string；必填 | prerequisites launch 文件名 |
| `integrations.mapping_prerequisites.extrinsics_file` | string；必填 | 已标定外参文件 |
| `integrations.mapping_prerequisites.startup_timeout_seconds` | number；必填，示例 15 | 正秒数 |
| `integrations.fast_lio.setup_file` | string；必填 | 建图启动环境 |
| `integrations.fast_lio.package` | string；必填 | 外部建图 ROS 包 |
| `integrations.fast_lio.launch_file` | string；必填 | 外部建图 launch |
| `integrations.fast_lio.launch_args` | string[]；必填，可空 | 每元素一个 launch 参数模板，不是一条拼接 shell |
| `integrations.fast_lio.startup_timeout_seconds` | number；必填，示例 30 | 正秒数 |
| `integrations.fast_lio.stop_timeout_seconds` | number；必填，示例 30 | 正秒数，受管进程停止等待 |
| `integrations.fast_lio.pid_path` | string；必填 | 含 {session_dir} 的会话 PID 路径 |
| `integrations.fast_lio.log_path` | string；必填 | 含 {session_dir} 的会话日志路径 |
| `integrations.map_accumulator.setup_file` | string；必填 | 保存接口环境 |
| `integrations.map_accumulator.service` | string；必填 | 绝对 ROS 服务名；非 Go2 可为 profile 兼容占位值 |
| `integrations.map_accumulator.save_timeout_seconds` | number；必填，示例 60 | 0 < 值 <= 600 秒 |
| `integrations.pgm.setup_file` | string；必填 | 地图转换环境 |
| `integrations.pgm.package` | string；必填 | PGM 工具包 |
| `integrations.pgm.launch_file` | string；必填 | PGM launch，按后端保留占位值 |
| `integrations.pgm.launch_args` | string[]；必填，可空 | PGM launch 模板参数 |
| `integrations.pgm.generation_timeout_seconds` | number；必填，示例 300 | 正秒数；节点成果生成等待还包含 30 秒余量 |
| `integrations.pgm.log_path` | string；必填 | 含 {session_dir} 的转换日志 |

建图模板允许 map_id、device_id、session_id、session_dir、pcd_path、pgm_path、yaml_path、map_name；不允许未知模板字段。map_name 使用 YYYYMMDD_HHMMSS。配置模板中的 PID、日志和成果先按 session_dir 校验；启用 launch log_dir 后仅日志映射到受控的 sessions/<session_id>，仍需通过路径边界检查，PID/成果不迁移。不得通过 .. 越界。更改 backend 后既要调用 load_config，也要检查 build_integration_commands；专有参数部分在构造命令时才校验。

<a id="documents-interface-reference-md-84-scout-与-managed-后端专有项"></a>
### 8.4 Scout 与 managed 后端专有项

下表每行列出两个完整键。scout_finalize 使用 integrations.scout，managed_finalize 使用 integrations.managed；另一个分组不参与该后端。除节点名默认值外，所选后端各项均需提供非空字符串，具体包名见对应 profile。

| Scout 键 / managed 键 | 类型 / 默认或要求 | 定义与约束 |
| --- | --- | --- |
| `integrations.scout.fast_lio_package` / `integrations.managed.fast_lio_package` | string；必填 | FAST-LIO 包 |
| `integrations.scout.fast_lio_launch` / `integrations.managed.fast_lio_launch` | string；必填 | FAST-LIO launch |
| `integrations.scout.mapper_package` / `integrations.managed.mapper_package` | string；必填 | 点云累积包 |
| `integrations.scout.mapper_launch` / `integrations.managed.mapper_launch` | string；必填 | 累积器 launch |
| `integrations.scout.tf_package` / `integrations.managed.tf_package` | string；必填 | TF 管理包 |
| `integrations.scout.tf_launch` / `integrations.managed.tf_launch` | string；必填 | TF launch |
| `integrations.scout.pose_package` / `integrations.managed.pose_package` | string；必填 | 位姿适配包 |
| `integrations.scout.pose_launch` / `integrations.managed.pose_launch` | string；必填 | 位姿适配 launch |
| `integrations.scout.finalize_package` / `integrations.managed.finalize_package` | string；必填 | 最终地图转换包 |
| `integrations.scout.finalize_executable` / `integrations.managed.finalize_executable` | string；必填 | rosrun 可执行文件，示例 finalize_map.py |
| `integrations.scout.filtered_pcd_filename` / `integrations.managed.filtered_pcd_filename` | string；必填 | 单一文件名，禁用 .、.. 和目录分隔符 |
| `integrations.scout.map_root` / `integrations.managed.map_root` | string；必填 | 地图工具可写根目录，按 map_name 建子目录 |
| `integrations.managed.fast_lio_node` | string；默认 /laserMapping | 生命周期检查的绝对 ROS 节点名 |
| `integrations.managed.mapper_node` | string；默认 /scout_pointcloud_mapper | Wheeltec 必须覆盖为其节点名 |
| `integrations.managed.tf_node` | string；默认 /scout_tf_manager | 同上 |
| `integrations.managed.geometry_tf_node` | string；默认 /scout_geometry_tf_publisher | 同上 |
| `integrations.managed.pose_node` | string；默认 /scout_pose_adapter | 同上 |

加载器也接受 integrations.scout 下同名的五个 *_node 可选键，但仅 managed_finalize 的命令使用可配置节点参数；Scout 脚本继续使用其既有节点约定，不应依赖这些键改名。

<a id="documents-interface-reference-md-85-ground-air-后端专有项"></a>
### 8.5 Ground-Air 后端专有项

仅 ground_air_service 使用以下分组。

| 键 | 类型 / 默认或要求 | 定义与约束 |
| --- | --- | --- |
| `integrations.ground_air.expected_nodes` | string[]；必填 | 非空绝对 ROS 节点名列表，含外部静态 TF owner |
| `integrations.ground_air.save_package` | string；必填 | 保存 launch 所属包，示例 car_bringup |
| `integrations.ground_air.save_launch` | string；必填 | 示例 save_mapping.launch |
| `integrations.ground_air.map_root` | string；必填 | 算法侧地图输出根目录 |
| `integrations.ground_air.saved_pcd_filename` | string；默认 cloud_map.pcd | 单一 PCD 文件名 |
| `integrations.ground_air.saved_pgm_filename` | string；默认 map.pgm | 单一 PGM 文件名 |
| `integrations.ground_air.saved_yaml_filename` | string；默认 map.yaml | 单一地图 YAML 文件名 |
| `integrations.ground_air.metadata_filename` | string；默认 metadata.json | 保存元数据文件名；上述文件名禁用目录分隔符、. 和 .. |

<a id="documents-interface-reference-md-9-relocalizationyaml"></a>
## 9. relocalization.yaml

network/storage/ros/tf_stability 结构必填。stages 仅接受程序可调用的包与 launch，不会自动安装外部算法。

| 键 | 类型 / 默认或要求 | 定义与约束 |
| --- | --- | --- |
| `schema_version` | int；必填 1 | 配置 schema |
| `protocol_id` | string；必填 ccs-relocalization-v1 | 与地面站一致 |
| `enabled` | bool；必填 | 本包实际读取的开关；仅在设备定位 stages 已完成联调时设为 true |
| `backend` | enum；必填 | scout_mini/wheeltec_r550p/ground_air_agv/go2_edu |
| `network.bind_host` | string；必填，示例 0.0.0.0 | 本机 UDP 绑定地址 |
| `network.control_port` | int；必填，示例 14565 | 1..65535 |
| `network.ground_station_ip` | string；必填 | 地面站控制来源与状态目标 |
| `network.status_port` | int；必填，示例 14566 | 1..65535 |
| `network.max_datagram_bytes` | int；必填，示例 1400 | 512..65507 |
| `trusted_regions.enabled` | bool；可选，默认 true | 接收可信区域开关，关闭不影响定位 |
| `trusted_regions.root` | string；可选，默认 ~/.ros/ccs_edge_dev/trusted_regions | 区域 XML 保存根目录 |
| `trusted_regions.apply_to_ndt` | bool；可选，默认 false | 将可信区域同步给 NDT 定位器 |
| `storage.map_root` | string；必填 | 下载地图可写根目录，需与任务及遥测一致 |
| `storage.pcd_filename` | string；默认 public_map.pcd | 仅 public_map.pcd/cloud_map.pcd |
| `storage.active_map_state_file` | string；默认 ~/.ros/ccs_edge_dev/state/relocalization.json | 活动地图状态；Ground-Air 指向 CCS run 目录 |
| `storage.max_artifact_bytes` | int；必填，示例 4294967296 | 正字节数，下载归档上限 |
| `storage.download_timeout_seconds` | number；必填，示例 300 | 正秒数 |
| `ros.map_frame` | string；必填，示例 map | 定位地图坐标系 |
| `ros.odom_frame` | string；必填，示例 odom | 本地里程计坐标系 |
| `ros.base_frame` | string；可选，默认 base_link | 新鲜 TF 链检查的车体坐标系 |
| `ros.require_fresh_tf` | bool；可选，默认 false | 定位成功前要求 map 到 odom 与车体 TF 均新鲜 |
| `ros.algorithm_lock_file` | string；可选 | 建图与定位算法的进程间所有权锁文件 |
| `ros.navigation_guard_file` | string；可选 | 导航与定位阶段共享的互斥锁文件 |
| `ros.initial_pose_topic` | string；必填，示例 /initialpose | 初始位姿输出 |
| `ros.localization_health_topic` | string；默认空 | 可选定位健康 Bool 话题；配置后必须为 true 且数据新鲜，TF 才可判定成功 |
| `ros.localization_health_timeout_seconds` | number；默认 tf_stability.timeout_seconds | 定位健康样本最大年龄，必须为正数 |
| `ros.map_topic` | string；必填 | 就绪判定地图话题，Scout 通常 /map_2d、AGV /map |
| `ros.startup_timeout_seconds` | number；必填，示例 60 | 正秒数，栈启动等待 |
| `ros.stages` | mapping[]；必填 | 按顺序启动；`enabled: true` 时必须非空 |
| `ros.stages[].name` | string；必填 | 阶段标识 |
| `ros.stages[].package` | string；必填 | ROS 包名 |
| `ros.stages[].launch` | string；必填 | launch 文件名 |
| `ros.stages[].args` | string[]；默认 [] | 每元素一个 launch 参数，可用本节模板 |
| `ros.stages[].runtime_sandbox.workspace` | string；可选 | 阶段运行时隔离工作空间 |
| `ros.stages[].runtime_sandbox.bindings[].source` | string；可选 | 隔离环境中的源路径 |
| `ros.stages[].runtime_sandbox.bindings[].target` | string；可选 | 映射到原生工作空间的目标路径 |
| `ros.stages[].ros_package_path_prepend` | string；可选，无缺省覆盖 | 子进程 ROS_PACKAGE_PATH 前置目录，可用模板 |
| `ros.stages[].ros_package_path_exclude` | string[]；默认 [] | 从子进程环境排除指定绝对路径 |
| `ros.stages[].cmake_prefix_path_exclude` | string[]；默认 [] | 排除子进程 CMAKE_PREFIX_PATH 指定绝对路径 |
| `tf_stability.timeout_seconds` | number；必填，示例 30 | 正秒数；连续回报模式仅首样本受此超时约束 |
| `tf_stability.sample_hz` | number；必填，示例 10 | 正 Hz，稳定采样频率 |
| `tf_stability.sample_count` | int；必填，示例 10 | >=2，稳定窗口样本数 |
| `tf_stability.translation_tolerance_m` | number；必填，示例 0.10 | 正米数 |
| `tf_stability.yaw_tolerance_deg` | number；必填，示例 2 | 正角度数 |
| `tf_reporting.continuous` | bool；默认 false | Ground-Air profile=true，首样本后持续发送 |
| `tf_reporting.interval_seconds` | number；默认 1/sample_hz | 正秒数，Ground-Air=1 |
| `tf_reporting.persist_interval_seconds` | number；默认 30 | 正秒数，后续样本落盘间隔 |
| `deployment.state` | string；可选元数据 | 不改变功能开关 |

重定位阶段模板为 map_id、map_dir、map_root、map_pcd、map_yaml，与建图模板不同。路径排除是规范化后的绝对路径精确匹配，不是递归排除整个目录树。保留 Ground-Air profile 中 prepend/exclude 的配套配置，单独删除会重新暴露同名 underlay 包。

<a id="documents-interface-reference-md-10-task_controlyaml"></a>
## 10. task_control.yaml

adapter 整段可省略，此时仅运行通用协调器；提供非空 adapter 时，公共字段和所选类型的字段必填。`adapter.type` 省略时按兼容模式使用 navigation；ground_air 必须显式声明。其数值不设置隐式默认，示例来自公共配置。网络 bind 可用 0.0.0.0，其余身份/地面站 IP 使用有效 IPv4。

| 键 | 类型 / 默认或要求 | 定义与约束 |
| --- | --- | --- |
| `schema_version` | int；必填 2 | 配置 schema |
| `protocol_id` | string；必填 ccs-task-control-v2 | 当前协议 |
| `network.bind_host` | string；必填 | 本地 IPv4 绑定 |
| `network.control_port` | int；必填，示例 14563 | 1..65535 |
| `network.ground_station_ip` | string；必填 | 地面站 IPv4 |
| `network.status_port` | int；必填，示例 14564 | 1..65535 |
| `network.max_datagram_bytes` | int；必填，示例 1400 | 512..1400 |
| `storage.directory` | string；必填，示例 ~/ccs_edge_ws/mission | XML 和任务持久化目录，展开 ~ |
| `ros.command_topic` | string；必填 | command 发布话题 |
| `ros.feedback_topic` | string；必填 | feedback 订阅话题 |
| `ros.status_topic` | string；必填 | String 摘要状态发布话题 |
| `ros.map_frame` | string；必填，示例 map | 任务目标坐标系 |
| `timeouts.ack_cache_seconds` | number；必填，示例 60 | >=1 秒，ACK 幂等缓存 |
| `timeouts.transfer_seconds` | number；必填，示例 10 | >=0.1 秒，任务传输超时 |
| `timeouts.adapter_feedback_seconds` | number；必填，示例 2 | >=0.1 秒，适配器反馈阈值 |
| `timeouts.preparation_retry_on_failure` | bool；可选，默认 true | 准备失败后是否自动重试 |
| `timeouts.execution_feedback_seconds` | number；必填，示例 5 | >=0.1 秒，执行反馈阈值 |
| `timeouts.preparation_retry_seconds` | number；必填，示例 5 | >=0.5 秒，准备重试 |
| `timeouts.utc_tolerance_seconds` | number；必填，示例 2 | >=0.01 秒，UTC 误差容忍 |
| `limits.max_waypoints` | int；必填，示例 500 | 2..500 |
| `limits.max_compressed_bytes` | int；必填，示例 1048576 | >=1024 字节 |
| `limits.max_raw_bytes` | int；必填，示例 8388608 | >=1024 且不小于 max_compressed_bytes |
| `limits.max_chunks` | int；必填，示例 2048 | 1..4096 |
| `adapter.type` | string；默认 navigation | navigation 或 ground_air；Ground-Air profile 必须显式填写 |
| `adapter.active_map_state_file` | string；条件必填 | 与重定位活动地图状态一致 |
| `adapter.navigation_map_root` | string；条件必填 | 与重定位下载根目录一致；两种适配器共用 |
| `adapter.navigation_map_yaml` | string；条件必填，示例 map.yaml | 地图栅格描述文件名；两种适配器共用 |
| `adapter.navigation_launch_package` | string；条件必填 | 导航 ROS 包 |
| `adapter.navigation_launch_file` | string；条件必填 | 导航 launch |
| `adapter.navigation_action` | string；条件必填，示例 /move_base | MoveBaseAction 服务端命名空间 |
| `adapter.odom_topic` | string；条件必填 | 适配器位姿、进度反馈和新鲜度使用的 nav_msgs/Odometry 输入 |
| `adapter.navigation_odom_topic` | string；可选 | 受管导航 launch 的速度里程计输入；缺省回退到 adapter.odom_topic，UGV_003 必须显式为 /odom |
| `adapter.zero_velocity_topic` | string；条件必填，示例 /cmd_vel | geometry_msgs/Twist 停车话题 |
| `adapter.navigation_cmd_vel_topic` | string；可选 | move_base 的速度输出；UGV_003 为 /wheeltec_driver/cmd_vel |
| `adapter.navigation_log_directory` | string；可选 | 受管导航 stdout/stderr 日志目录；失败消息附退出码、摘要和路径 |
| `adapter.navigation_guard_file` | string；可选 | 原生导航进程所有权锁文件 |
| `adapter.navigation_startup_timeout_seconds` | number；条件必填，示例 25 | 正秒数 |
| `adapter.waypoint_timeout_seconds` | number；条件必填，示例 300 | 正秒数，单航点执行 |
| `adapter.pose_timeout_seconds` | number；条件必填，示例 2 | 正秒数，位姿新鲜度 |
| `adapter.base_frame` | string；可选，默认 base_link | 车体 TF 检查坐标系 |
| `adapter.require_fresh_tf` | bool；可选，默认 false | 准备导航前要求 TF 链新鲜 |
| `adapter.localization_health_topic` | string；可选 | 定位健康状态 Bool 话题 |
| `adapter.zero_velocity_hz` | number；条件必填，示例 20 | 正 Hz，停车消息频率 |
| `adapter.zero_velocity_count` | int；条件必填，示例 10 | >=1，停车消息次数 |
| `adapter.navigation_management` | enum；默认 managed | managed 启停导航进程；attach 复用重定位持有的导航栈，Go2 native 使用 attach |
| `adapter.native_map.enabled` | bool；可选，默认 false | 启用原生地图导航就绪检查 |
| `adapter.native_map.readiness_file` | string；native_map 启用时必填 | 原生导航地图就绪状态文件 |
| `adapter.auto_arm_on_schedule` | bool；默认 false | 调度时校验定位并调用控制使能；启用时必须同时启用 auto_disarm_on_terminal |
| `adapter.auto_disarm_on_terminal` | bool；默认 false | 任务终态调用控制禁用，并等待真实禁用状态确认 |
| `adapter.emergency_stop_state_file` | string；自动控制时必填 | 持久化急停闭锁文件；Go2 native 位于 CCS 工作空间 run/state/go2_task_safety.json |
| `adapter.localization_ok_topic` | string；自动控制时必填 | 定位健康 std_msgs/Bool 输入，Go2 native 为 /localization/ok |
| `adapter.control_enabled_topic` | string；自动控制时必填 | 真实使能状态 std_msgs/Bool 输入，Go2 native 为 /go2/control/enabled |
| `adapter.control_diagnostics_topic` | string；可选，Go2 示例 /go2/diagnostics | diagnostic_msgs/DiagnosticArray，补充周期性控制状态及新鲜度确认 |
| `adapter.navigation_reset_service` | string；自动控制时必填 | std_srvs/Trigger，Go2 native 为 /go2_navigation_supervisor/reset |
| `adapter.control_enable_service` | string；自动控制时必填 | std_srvs/SetBool，Go2 native 为 /go2_sdk_bridge_real/enable |
| `adapter.control_stop_service` | string；可选 | std_srvs/Trigger；UGV_003 用于故障锁定停车 |
| `adapter.control_heartbeat_topic` | string；可选 | std_msgs/Empty；控制权租约话题 |
| `adapter.control_heartbeat_hz` | number；可选，1..100 | 控制权租约发送频率；UGV_003 为 10 Hz |
| `adapter.reset_control_on_emergency_clear` | bool；默认 false | 清除任务急停时同时调用 navigation_reset_service；只在对应控制器支持时启用 |
| `adapter.control_service_timeout_seconds` | number；自动控制时必填，示例 5 | >=0.01 秒，控制服务等待与调用超时 |
| `adapter.control_state_timeout_seconds` | number；自动控制时必填，示例 3 | >=0.01 秒，控制状态与健康输入的新鲜度及确认阈值 |
| `adapter.control_authority` | mapping；可选 | 启动 Wheeltec 控制权协调器；提供时下列接口键全部必填 |
| `adapter.control_authority.safety_gate_enabled` | bool；可选 | 原生安全门是否接管速度输出 |
| `adapter.control_authority.driver_auto_acquire` | bool；可选 | 自动取得底盘驱动控制权 |
| `adapter.control_authority.driver_odom_topic` | string；可选 | 底盘驱动速度里程计话题 |
| `adapter.control_authority.state_file` | string；control_authority 必填 | schema 2 重定位状态文件 |
| `adapter.control_authority.odom_topic` | string；control_authority 必填 | nav_msgs/Odometry 新鲜度来源 |
| `adapter.control_authority.localization_ok_topic` | string；control_authority 必填 | std_msgs/Bool 定位状态输出 |
| `adapter.control_authority.enabled_topic` | string；control_authority 必填 | std_msgs/Bool 协调器控制状态输出 |
| `adapter.control_authority.driver_enabled_topic` | string；control_authority 必填 | std_msgs/Bool 驱动自主状态输入 |
| `adapter.control_authority.driver_enable_service` | string；control_authority 必填 | std_srvs/SetBool 驱动控制权切换 |
| `adapter.control_authority.driver_stop_service` | string；control_authority 必填 | std_srvs/Trigger 驱动故障锁停 |
| `adapter.control_authority.driver_reset_service` | string；control_authority 必填 | std_srvs/Trigger 人工复位并归还手动控制 |
| `adapter.control_authority.safety_arm_service` | string；control_authority 必填 | std_srvs/Trigger 打开安全门 |
| `adapter.control_authority.safety_stop_service` | string；control_authority 必填 | std_srvs/Trigger 关闭安全门并停车 |
| `adapter.control_authority.safety_reset_service` | string；control_authority 必填 | std_srvs/Trigger 复位安全门状态 |
| `adapter.control_authority.state_publish_hz` | number；默认 10，1..100 | 状态发布频率 |
| `adapter.control_authority.odom_timeout_seconds` | number；默认 1，0.1..10 | 实时定位里程计最大年龄 |
| `adapter.task_launch_package` | string；ground_air 必填 | 原生分层任务 launch 所属 ROS 包 |
| `adapter.task_launch_file` | string；ground_air 必填，示例 task_system.launch | 原生分层任务 launch 文件 |
| `adapter.localization_param` | string；ground_air 必填 | 实时定位 bool 参数，历史状态文件不能替代 |
| `adapter.vehicle_status_topic` | string；ground_air 必填 | ground_air_msgs/VehicleStatus 输入 |
| `adapter.mission_status_topic` | string；ground_air 必填 | ground_air_msgs/MissionStatus 输入 |
| `adapter.prepare_ground_service` | string；ground_air 必填 | 地面模式准备 Trigger 服务 |
| `adapter.mission_submit_service` | string；ground_air 必填 | 任务提交服务 |
| `adapter.mission_start_service` | string；ground_air 必填 | 任务启动 Trigger 服务 |
| `adapter.mission_cancel_service` | string；ground_air 必填 | 任务取消 Trigger 服务 |
| `adapter.emergency_stop_service` | string；ground_air 必填 | 原生急停服务；必须确认闭锁成功 |
| `adapter.emergency_lock_file` | string；ground_air 必填 | CCS 工作空间内持久化急停闭锁状态 |
| `adapter.service_timeout_seconds` | number；ground_air 必填，示例 10 | 正秒数，服务等待和调用超时 |
| `adapter.dwell_seconds` | number；ground_air 必填，示例 2 | 正秒数，航点停留时间 |
| `adapter.max_linear_speed_mps` | number；ground_air 必填，示例 0.1 | 正 m/s；任务请求超过此值时拒绝 |
| `adapter.max_angular_speed_rps` | number；ground_air 必填，示例 0.2 | 正 rad/s，传入原生导航运行参数 |
| `deployment.state`、`deployment.enabled` | string / bool；可选 | 说明元数据，不启动任务节点 |

使用 YAML 的 true/false 和真正的数字，不要写字符串 "false" 或 "2.0"。各包校验强度不同，不能依赖类型强制转换来修正配置。

<a id="documents-interface-reference-md-11-launch-参数与脚本环境变量"></a>
| `adapter.clear_costmaps_service` | string；可选，无默认服务 | 非空 ROS std_srvs/Empty 服务名；UGV_003 为 /move_base/clear_costmaps。wheeltec_r550p 后端使能前清理代价地图；修改 task_control.yaml 并重启适配器。 |
| `adapter.clear_costmaps_settle_seconds` | number，秒；默认 0.30 | 0.01–5.0，必须同时配置 clear_costmaps_service；清理后等待时间；修改同一文件并重启。 |


UAV 补充字段：

| 参数 | 说明 |
| --- | --- |
| `adapter.workspace` | 独立 CCS 工作空间及受管进程边界。 |

## 11. launch 参数与脚本环境变量

<a id="documents-interface-reference-md-111-单包-launch"></a>
### 11.1 单包 launch

文件路径参数均为 string，建议使用绝对路径。默认共享目录为 `$(find epgeneral_device_config)/config`。参数在启动时求值，重启才生效。

| launch / 参数 | 默认或要求 | 作用 |
| --- | --- | --- |
| 除 MQTT/UDP/视频外的业务主 launch：device_config_file | 共享目录/device.yaml | 唯一身份配置；MQTT/UDP/视频要求显式选择 |
| epgeneral_mqtav.launch：config_dir | 空，须显式填写 | 同时加载 device.yaml 和 epgeneral_mqtav.yaml；兼容显式 config_file/device_config_file 文件对 |
| epgeneral_mqtav.launch：log_dir | HOME/.ros/log/epgeneral_mqtav/设备ID | 耐久日志目录，可覆盖 |
| epgeneral_udp_telemetry.launch：config_dir | 空，须显式选择 | 同时加载 device.yaml 与 udp_telemetry.yaml；与完整文件对互斥 |
| epgeneral_udp_telemetry.launch：telemetry_config_file / device_config_file | 均为空 | 兼容显式完整文件对，不能只传其中一个 |
| epgeneral_udp_telemetry.launch：destination_host / destination_port | 均为空 | 仅非空值覆盖 YAML，不再隐式覆盖目标 |
| epgeneral_udp_telemetry.launch：link_status_topic / diagnostics_topic | 均为空 | 仅非空值覆盖 YAML runtime 输出话题 |
| epgeneral_video_srt.launch / rtsp_srt.launch / epgeneral_realsense_d435i_srt.launch / camera.launch：config_dir | 空，须显式选择 | 同时读取 device.yaml/video.yaml，与完整文件对互斥 |
| 同上：video_config_file / device_config_file | 均为空 | 兼容完整文件对 |
| 同上：decoder_preload | 空 | 兼容覆盖；推荐 runtime.decoder_preload |
| camera.launch：capture_args | 空 | 兼容参数 --capture-arg name:=value；新部署优先 YAML |
| epgeneral_map_stream.launch：mapping_config_file | 共享目录/map_stream.yaml | 建图配置 |
| epgeneral_map_stream.launch：log_dir | 空字符串 | 可选 map-stream 事件日志目录；设置后 FAST-LIO 与 PGM 日志进入 `sessions/<session_id>` 子目录 |
| mapping_prerequisites.launch：extrinsics_file | Go2 calibration/go2_edu_02/extrinsics.yaml 绝对路径 | Go2 prerequisites 的外参文件，不通用于其他 profile |
| epgeneral_relocalization.launch：config_file | 共享目录/relocalization.yaml | 重定位配置 |
| epgeneral_relocalization.launch：log_dir | 空字符串 | 空时由节点选默认日志目录 |
| relocalization_map_server.launch：map_yaml | 必填 | map_server 读取的栅格描述文件 |
| epgeneral_task_control.launch / scout_task_control.launch / navigation_task_control.launch / wheeltec_task_control.launch / ground_air_task_control.launch：task_config_file | 共享目录/task_control.yaml | 设备入口同时包含对应适配器；Wheeltec 入口另启动控制权协调器，只选择一个入口 |
| wheeltec_ccs_2d_navigation.launch：map_name / map_dir / nav_map_yaml | ccs_map / 下载根目录下同名目录 / map.yaml | 指定已下载地图目录和二维栅格 YAML；不读取 terrain_2p5d.yaml |
| wheeltec_ccs_2d_navigation.launch：odom_topic / cmd_vel_topic | /odom / /nav_cmd_vel | 轮式速度里程计输入与 move_base 速度输出；定位位姿仍由适配器读取 /fastlio_odom |
| ground_air_control 的 relocalization_control.launch：map_id | 必填 | 当前地图 ID |
| 同上：maps_root | /home/bitcq/ccs_edge_ws/maps/download | 下载地图根目录 |
| 同上：service_wait_timeout / relocalize_timeout | 90.0 / 60.0 | 正秒数，外部服务等待/重定位请求超时 |

设备 bringup 的 profile_dir 默认相对 launch 位置，不同安装布局下应显式传绝对路径。legacy Go2 的 enable_task_control 默认 false，仅该 launch 生效，不会启用一键脚本中的任务。Wheeltec 的 enable_video 默认 true，先启动 Gemini 336L 再启动 SRT。三种 bringup 的 ground_station_ip 默认 192.168.50.101，主要传给 UDP，不会改写 MQTT 等 YAML。

Ground-Air 设备适配 launch 还提供：manual_mapping_control/relocalization_control 的 map_id（必填）、maps_root（默认 /home/bitcq/catkin_ws/maps）、service_wait_timeout（90 秒）及重定位的 relocalize_timeout（60 秒）；override 的 relocalization_system 使用 map_id 和两个超时。mapping_coordinate_transforms 的 odom_frame/camera_init_frame/body_frame/base_frame 默认 odom/camera_init/body/base_link。mavros_base 的 fcu_url 默认串口 by-id 路径加 :57600，gcs_url 默认空；livox_mid360_base 的 msg_frame_id 默认 base_link。

<a id="documents-interface-reference-md-go2-native-集成入口"></a>
#### Go2 native 集成入口

`epgeneral_go2_integration/bringup.launch` 是显式组合入口，不能与 Robot2/Robot3 根脚本同时运行；常规部署使用根脚本提供的预检、状态确认和进程监控。Robot3 的配置、遥测命名空间和相机参数必须按该设备覆盖，不能直接使用 Robot2 默认值。

| launch / 参数 | 默认或要求 | 作用 |
| --- | --- | --- |
| bringup.launch：`profile_dir` | /home/unitree/ccs_edge_ws/config/go2_robot2 | 七份业务 YAML 的运行目录 |
| bringup.launch：`network_interface` | go2dds | 传入真实 SDK bridge 的 DDS 网络接口 |
| bringup.launch：`ground_station_ip` | 192.168.50.101 | UDP 遥测目标，不重写其他 YAML 的地址 |
| bringup.launch：`log_root` | /home/unitree/ccs_edge_ws/logs | MQTT 与重定位日志根目录 |
| bringup.launch：`telemetry_namespace` | /qrd/QRD_002 | UDP link 与 diagnostics 话题前缀；Robot3 使用 /qrd/QRD_003 |
| bringup.launch：`camera_serial` | 空字符串 | 仅该组合 launch 的 serial_no 参数；Robot2/Robot3 根脚本默认自动选择，可选 CCS_D435_SERIAL 原样传入，不能用此参数推断根脚本行为 |
| bringup.launch：`color_fps` | 空 | 空时使用 capture.args.color_fps；非空显式覆盖 |
| mapping_fast_lio.launch / navigation_guard.launch：`lock_file` | /home/unitree/ccs_edge_ws/run/go2_stack.lock | 建图与导航共用的排他锁；必须在两条生命周期中一致 |
| navigation.launch：`map_name` | 必填 | 原生定位和导航加载的地图名 |
| navigation.launch：`map_root` | /home/unitree/ccs_edge_ws/maps/download | 下载地图根目录 |
| navigation.launch：`extrinsics_file` | /home/unitree/go2_nav_ws/src/go2_core/config/extrinsics.yaml | 原生标定文件，不以其他设备标定替换 |
| mapping_prerequisites_go2_robot2.launch / mapping_prerequisites_go2_robot3.launch：`output_path` | /home/unitree/ccs_edge_ws/run/map/current/public_map.pcd | accumulator 的 PCD 导出路径 |

重定位须先启动 navigation_guard，再启动 navigation，逆序停止。`/localization/ok` 必须为新鲜真值，不能仅凭原生栈的临时单位 TF 判断定位成功。

<a id="documents-interface-reference-md-112-一键脚本环境"></a>
### 11.2 一键脚本环境

下表为启动前 export 的字符串变量；时间、波特率仍需满足其使用程序的要求。不设置时采用表内缺省。这些变量不改变运行 YAML 内容。

| 环境变量 | 适用 profile / 默认 | 含义 |
| --- | --- | --- |
| `CCS_EDGE_WORKSPACE` | 全部；见 README 工作空间表 | CCS 工作空间根目录 |
| `CCS_EDGE_PROFILE_CONFIG_DIR` | 全部；工作空间/config/profile | 运行 YAML 目录；仅 legacy Go2 先尝试脚本旁 config/device.yaml，Robot2/3 直接使用各自 profile |
| `CCS_EDGE_PROFILE_LAUNCH_DIR` | UAV_001；默认工作空间/launch | UAV 根启动 launch 目录 |
| `CCS_EDGE_PROFILE_SCRIPT_DIR` | UAV_001；默认工作空间/scripts | UAV 预检、就绪和 supervisor 脚本目录 |
| `CCS_ROS_IP` | Go2 legacy .100、Robot2 .111、Robot3 .112、Scout .120、Wheeltec .122、AGV .130、UAV_001 .140；前缀 192.168.50 | ROS 本机地址 |
| `CCS_ENABLE_VIDEO` | Wheeltec；1 | 1 时由视频管理脚本启动 Gemini 336L/SRT；设为 0 跳过视频且不影响基础服务 |
| `CCS_GROUND_STATION_IP` | Go2/Scout/Wheeltec；192.168.50.101 | 授时默认目标及 UDP 覆盖；Ground-Air 脚本不提供此变量 |
| `CCS_NTP_SERVER` | 前三者默认地面站变量；AGV 默认 192.168.50.101 | 预检要求的授时服务器 |
| `CCS_GO2_NAV_SETUP` | Go2；/home/nvidia/go2_mid360_nav/catkin_ws/devel/setup.bash | 算法 underlay |
| `CCS_GO2_NAV_WORKSPACE` | Go2 Robot2/Robot3；/home/unitree/go2_nav_ws | 原生算法工作空间根目录，脚本 source 其中 devel/setup.bash |
| `CCS_GO2_NETWORK_INTERFACE` | Go2 Robot2/Robot3；go2dds | 真实 SDK bridge 使用的 DDS 接口 |
| `CCS_D435_SERIAL` | Go2 Robot2/Robot3；空字符串 | 可选 RealSense 序列号；空值使用单设备自动选择，非空值原样传给 `serial_no`，不添加前导下划线；Robot2 保持 RGB 640×480@30，Robot3 为 15 FPS |
| `CCS_EDGE_LOG_ROOT` | Go2 Robot3；`/home/unitree/.ros/ccs_edge_ws` | 每次正常启动按 UTC 时间、纳秒和 PID 建立独立日志目录；`--check` 不创建目录 |
| `CCS_GO2_USE_REAL_SDK` | Go2 Robot2；true | SDK 模式开关，仅接受 true/false；Robot3 固定使用真实 SDK，不提供此覆盖 |
| `CCS_LIVOX_SETUP` | Scout /home/nvidia/livox_fastlio/devel/setup.bash；Wheeltec /home/nrc19/livox_fastlio/devel/setup.bash | 雷达与算法环境 |
| `CCS_REALSENSE_SETUP` | Scout；/home/nvidia/realsense_ws/devel/setup.bash | 相机环境 |
| `CCS_NAVIGATION_SETUP` | Scout；/home/nvidia/github_upload/AADCL_UAV_UGV/Scout_mini/devel/setup.bash | 导航环境 |
| `CCS_DEVICE_UNDERLAY_SETUP` | AGV；/home/bitcq/catkin_ws/devel/setup.bash | Ground-Air 算法环境 |
| `CCS_EDGE_STATE_DIR` | legacy Go2 ~/.ros/ccs_edge_dev；Scout/Wheeltec 加 _scout_mini / _wheeltec_r550p | 脚本 PID/log 根目录；Robot2 默认工作空间/run/managed（仅 PID），不自动改变 YAML 状态文件 |
| `CCS_FCU_DEVICE` | AGV；/dev/serial/by-id/usb-CUAV_PX4_CUAV_Nora_0-if00 | 飞控串口设备 |
| `CCS_FCU_BAUD` | AGV；57600 | 飞控串口波特率 |
| `CCS_EDGE_LAUNCH_DIR` | AGV；工作空间/launch | 已安装的设备适配 launch |
| `CCS_EDGE_LOG_DIR` | AGV：工作空间/log/ground_air_agv；Robot2：工作空间/logs/managed | 组件日志目录 |
| `CCS_ROS_HOME` | AGV；工作空间/run/ros_home | ROS 主目录，实际以脚本 PID_DIR 为前缀 |
| `CCS_ROS_LOG_DIR` | AGV；组件日志目录/ros | ROS 日志目录 |

<a id="documents-interface-reference-md-113-timesyncd-ccsconf"></a>
### 11.3 timesyncd-ccs.conf

六套配置均包含 [Time]：`NTP=192.168.50.101` 为主授时地址，`FallbackNTP=` 清空回退列表，`RootDistanceMaxSec=5` 为最大根距离秒数，`PollIntervalMinSec=16`、`PollIntervalMaxSec=64` 为轮询间隔秒数。安装到 /etc/systemd/timesyncd.conf.d/ccs.conf 后重启 systemd-timesyncd，并用 timedatectl timesync-status 核实真实 ServerAddress 与同步状态。端口为 UDP 123。

不要同时引入相互争用的授时服务；已有 chrony 的设备应按现场管理方式配置等价授时并核对一键脚本的预检要求。GO2_3 根脚本只以 SNTP 有效应答判断平台授时可用（--availability-only），不检查时差、不设置时钟；不可用仍阻止启动。任务 timeouts.utc_tolerance_seconds=2.0 独立保留。其余 profile 按各自脚本验证服务器/同步状态。

<a id="documents-interface-reference-md-12-联调检查清单"></a>
## 12. 联调检查清单

~~~bash
rospack find epgeneral_device_config
rospack find epgeneral_task_control
rostopic type /initialpose
rosmsg show epgeneral_task_control/TaskExecutionCommand
rosmsg show epgeneral_task_control/TaskExecutionFeedback
rosservice type /ground_air/system/set_stage
rossrv show ground_air_msgs/SetSystemStage
rosrun tf tf_echo map odom
ss -lntup
~~~

按设备能力选用上述命令；非 Ground-Air 不要求存在阶段服务。首次接入外部包先核实实际消息类型、字段、frame、到达频率和 launch 参数，再更新 profile。通信通过不等于算法或执行器已验收；设备运动前按使用手册确认任务适配与现场操作条件。

<a id="documents-interface-reference-md-ugv_004-v51-补充"></a>
## UGV_004 V5.1 补充

`wheeltec_r550p_02` 使用 `CCS_EDGE_WORKSPACE`、`CCS_LIVOX_SETUP`、`CCS_EDGE_PROFILE_CONFIG_DIR`、`CCS_GROUND_STATION_IP`、`CCS_NTP_SERVER`、`CCS_ROS_IP`、`CCS_EDGE_LOG_ROOT`。默认目录为 `/home/nrc15/ccs_edge_ws`，日志根为工作空间/logs；`--check` 不创建运行目录或节点，正常启动只查询 SNTP 可用性，任务 UTC 容差仍为2秒。

`epgeneral_task_control/wheeltec_ccs_2d_navigation_v51.launch` 接受 `map_name`、`map_dir`、`nav_map_yaml`、`odom_topic`、`cmd_vel_topic`；地图目录和 YAML 来自 CCS 下载根，默认位姿 `/fastlio_odom`、停车 `/cmd_vel`。它只启动导航层，保留 V5.1 实时障碍检测与 TEB，使用二维全局栅格，不要求 terrain_2p5d.yaml。视频仅安装编译，脚本不启动视频节点。

该 profile 的 timesyncd 配置设置 NTP=192.168.50.101、FallbackNTP=，其余轮询参数使用系统默认；端侧脚本不修改时钟。详细行为及实测见 [UGV_004 记录](devices/wheeltec_r550p/DEPLOYMENT_RECORD.md#deploy-records-ugv-004-deployment-md)。

<a id="documents-external-workspace-integration-md"></a>

<a id="documents-external-workspace-integration-md-ccs-端侧其他工作空间接入与配置说明"></a>
# CCS 端侧其他工作空间接入与配置说明

更新日期：2026-09-11；适用 CCS 0.23.1 当前源码。依据本项目 `edge_side_pkg` 中的共享配置、六套设备 profile、launch、消息定义及接口实现编写。当前交付使用 ROS1 Noetic / Ubuntu 20.04 / Python 3；视频节点为 C++。本文件是源码级接入说明，不代表已经对外部设备完成实机验收。

项目实际源码目录为 `edge_side_pkg`，本文所称“CCS 通用包”指其中的 `EPGeneral_*` 和 `epgeneral_mqtav`；设备运行工作空间通常名为 `ccs_edge_ws`。目录名与 ROS 包名不同，`roslaunch` 使用小写包名，如 `epgeneral_map_stream`。

完整类型/配置键/当前值已集中在[配置话题与服务清单](INTERFACE_REFERENCE.md#documents-config-topic-reference-md)，新部署执行[从零指南](USER_MANUAL.md#documents-deployment-guide-md)，历史按[设备 ID](../README.md)归档。

<a id="documents-external-workspace-integration-md-1-先明确其他工作空间需要交付什么"></a>
## 1. 先明确其他工作空间需要交付什么

CCS 通用包负责通信、会话和任务协调，底盘驱动、传感器驱动、建图算法、定位算法及运动执行能力需要设备侧其他工作空间配合。下表的“必需”均指启用相应能力时必需，并非要求所有设备实现全部功能。

| 启用能力 | 外部工作空间应交付 | 对应配置 |
| --- | --- | --- |
| 在线状态和电池摘要 | 可用的状态消息源；需要电池显示时提供电池消息 | `epgeneral_mqtav.yaml` |
| 高频遥测和运行状态 | 所选 descriptor 的位姿、IMU、文本或持续有消息的话题；也可提供地图文件状态 | `udp_telemetry.yaml` |
| 视频 | 持续发布图像的相机驱动或视频转 ROS 节点 | `video.yaml` |
| 建图 | 雷达/IMU、点云/里程计、正确的 TF/外参、可受控启动的算法 launch、地图保存/转换工具 | `map_stream.yaml` |
| 重定位 | 可加载指定地图的定位 launch、初始位姿接收者、栅格地图和 `map <- odom` TF | `relocalization.yaml` |
| 导航任务 | move_base Action 服务端、里程计、TF、速度执行接口；或自行实现通用任务适配器 | `task_control.yaml` |
| Ground-Air 原生任务 | `ground_air_msgs`、原生任务和急停服务、车辆/任务状态、实时定位参数 | Ground-Air profile 与 `EPGeneral_ground_air_control` |

`EPGeneral_device_config` 只提供七份 YAML，没有常驻节点。普通设备使用公共七包；Ground-Air 加阶段控制包，原生 Go2 Robot2/Robot3 加 EPGeneral_go2_integration，各八包。发布归档共有九包，不能混装两个专用适配包。

<a id="documents-external-workspace-integration-md-2-配置文件在哪里改怎样生效"></a>
## 2. 配置文件在哪里改、怎样生效

<a id="documents-external-workspace-integration-md-21-选择实际运行副本"></a>
### 2.1 选择实际运行副本

| 启动方式 | 实际配置来源 | 修改方法 |
| --- | --- | --- |
| 单包 launch 默认入口 | `$(rospack find epgeneral_device_config)/config/` | 修改该目录，或通过 launch 参数显式指定文件 |
| 设备一键脚本 | 通常为 `<CCS工作空间>/config/<profile>/` | 修改实际运行目录；可由 `CCS_EDGE_PROFILE_CONFIG_DIR` 指定 |
| 本仓库部署原件 | `devices/<机型>/profiles/<profile>/config/` | 用作安装和版本管理原件；只改仓库原件不保证设备立即生效 |

共享模板位于 [EPGeneral_device_config/config](../EPGeneral_device_config/config)。它混合了 MAVROS、Go2、Scout 的示例：设备 IP 为 `192.168.50.150`，MQTT 地面站为 `192.168.20.10`，部分 UDP 为 `192.168.151.100`，建图/重定位又为 `192.168.50.101`。必须选定实际设备 profile 并统一地址、路径和话题，不能原样整体部署。

各节点在启动时加载配置，当前没有热重载。除 launch 明确暴露的参数外，直接 `rosparam set` 不会修改正在运行的 YAML 驱动节点。修改后重启相关节点；设备身份变化后重启所有相关通信节点。

<a id="documents-external-workspace-integration-md-22-ros-工作空间环境"></a>
### 2.2 ROS 工作空间环境

外部消息包必须已经构建，且 CCS 进程能加载其 Python 消息模块。所有互相通信的节点连接同一个 ROS Master；`ROS_IP` 填本机可达地址。Linux 设备示例如下，路径需换成实际值：

```bash
source /opt/ros/noetic/setup.bash
source /home/robot/device_ws/devel/setup.bash --extend
source /home/robot/ccs_edge_ws/devel/setup.bash --extend
export ROS_MASTER_URI=http://192.168.50.120:11311
export ROS_IP=192.168.50.120
rospack find epgeneral_device_config
rospack find epgeneral_task_control
```

同机不同 catkin 工作空间也必须连接同一 Master。跨主机时还要允许 ROS XMLRPC/TCPROS 的动态端口通信，不能只开放 11311。设备运行使用真实时间；任务按 UTC 调度，不能让某个算法 launch 把整套设备意外切换到无 `/clock` 的仿真时间。

<a id="documents-external-workspace-integration-md-3-外部功能包需要发布的-ros-话题"></a>
## 3. 外部功能包需要发布的 ROS 话题

本节列的是共享模板的原始配置值；实际 profile 差异见第 7 节。“外部 → CCS”指外部包发布、CCS 订阅或探测。可配置名字通常无需强制改外部代码，修改 CCS 对应键即可；但其他消费者和算法自身的输入配置仍须同步。

<a id="documents-external-workspace-integration-md-31-mqtt-状态摘要epgeneral_mqtavyaml"></a>
### 3.1 MQTT 状态摘要：`epgeneral_mqtav.yaml`

| 方向 | 模板话题 | 消息类型 | 配置键及字段映射 | 外部责任与条件 |
| --- | --- | --- | --- | --- |
| 外部 → CCS | `/mavros/state` | `mavros_msgs/State` | `ros.state.topic/message_type`；mapping 为 `connected/armed/system_status/mode` 同名字段 | 状态来源；无 MAVROS 的设备应替换为底盘状态或真实数据新鲜度来源 |
| 外部 → CCS | `/mavros/battery` | `sensor_msgs/BatteryState` | `ros.battery.topic/message_type`；mapping 为 `percentage/voltage/current` | 电池源默认启用；没有真实电池接口时设 `ros.battery.enabled: false` |
| 外部 → CCS | `/mission/status` | `std_msgs/String` | `ros.mission.topic/message_type/field_path: data` | 默认 `enabled: false`，仅启用任务摘要显示时需要 |

`mapping` 的值是消息字段路径，不是常量。对于只有里程计、没有 connected 字段的底盘，可用 `connected_on_message: true` 和 `timeout_seconds: 3.0` 按消息新鲜度判定在线，把不存在的字段显式设为 `null`。如果状态源为锁存 Bool（只在变化时发布），应另配置可选 ros.connection.topic/message_type/timeout_seconds 判断连接；QRD_003 为 /go2/state/low_state、go2_control/Go2LowState、3.0 秒，armed 继续读取 /go2/control/enabled 的 data，QRD_002 当前保持未配置 connection 的旧行为。此时“在线”仅表示该数据源近期有消息，不代表飞控解锁或导航就绪。电池电压使用 V、电流使用 A；不支持的量应保留未知，不能用常量伪造。

<a id="documents-external-workspace-integration-md-32-udp-遥测udp_telemetryyaml"></a>
### 3.2 UDP 遥测：`udp_telemetry.yaml`

| descriptor 名称 | 模板话题 | 消息类型/接收方式 | 取值路径或到达超时 |
| --- | --- | --- | --- |
| `global_pose` | `/mavros/local_position/pose` | `geometry_msgs/PoseStamped` | `position: pose.position`；`orientation: pose.orientation` |
| `vision_pose` | `/vision_pose/pose` | `geometry_msgs/PoseStamped` | 同上 |
| `imu` | `/mavros/imu/data` | `sensor_msgs/Imu` | `orientation`、`angular_velocity`、`linear_acceleration` |
| `livox_pointcloud` | `/livox/lidar` | `AnyMsg`，仅监测到达 | `pointcloud_status`，1 秒 |
| `livox_driver` | `/livox/lidar` | `AnyMsg`，仅监测到达 | `availability`，3 秒 |
| `fastlio2` | `/Odometry` | `AnyMsg`，仅监测到达 | `availability`，3 秒 |
| `pgm_mapping` | `/map_pgm` | `AnyMsg`，仅监测到达 | `availability`，3 秒 |
| `octomap_mapping` | `/octomap_binary` | `AnyMsg`，仅监测到达 | `availability`，3 秒 |
| `occupancy_grid_mapping` | `/map` | `AnyMsg`，仅监测到达 | `availability`，3 秒 |
| `mapping_mode` | `/mapping_mode` | `std_msgs/String` | `mapping: {value: data}`，3 秒 |

以上均为外部 → CCS。完整键为 `descriptors[].source.topic/message_type/mapping/timeout_seconds`。`AnyMsg` 是 Python 接收方式，不是外部应定义的一种 ROS 消息；这些监测项不强制指定载荷类型，也不证明算法结果正确。共享配置不能据此推导 `/map_pgm` 的固定消息类型。只发布一次的 latched 地图可能在到达超时后显示不可用，应选择与实际语义一致的持续状态源或 `pgm_file`。

`level: 1/2/3` 对应遥测分级发送，不是要求外部传感器分别按 20/5/1 Hz 发布。外部频率应满足算法需求及新鲜度窗口；不要用降低算法频率的方式匹配网络发送频率。修改来源只需调整 source；修改 `name/display_name/type/level` 会改变 descriptor hash，需同步地面站描述符。

Go2、Scout、Wheeltec profile 的 PGM 项采用 `source.kind: pgm_file`：读取 `state_file` 中的地图身份，再检查 `map_root` 下的地图文件，**不会订阅**其中的 `/ccs/relocalization/pgm_file`。无需额外造一个同名发布节点。

CCS 自己发布以下诊断话题，外部包按需订阅，无需自行提供发布者：

| 话题默认值 | 类型 | 含义 |
| --- | --- | --- |
| `/epgeneral_udp_telemetry/link/udp_tx` | `std_msgs/Bool`，latched | 本机 UDP 发送状态；不是地面站接收确认 |
| `/epgeneral_udp_telemetry/diagnostics` | `diagnostic_msgs/DiagnosticArray` | 数据源及发送诊断 |

<a id="documents-external-workspace-integration-md-33-视频videoyaml"></a>
### 3.3 视频：`video.yaml`

外部相机节点发布 `image_topic`，模板为 `/camera/image_raw`，`image_message_type` 为 `sensor_msgs/Image`；也支持 `sensor_msgs/CompressedImage`。CCS 负责编码和 SRT 输出，没有视频输出 ROS 话题。

配置 `output_width/output_height/framerate/bitrate_kbps` 调整输出；模板为 640×480、30 fps、2000 kbps，`frame_timeout_seconds: 5.0`。必须实际启动相机驱动；仅设置 `camera_model` 不会启动相机。视频运行环境需要 GStreamer 的 `appsrc`、`videoconvert`、`x264enc`、`h264parse`、`mpegtsmux`、`srtsink`。

顶层 `enabled: false` 并非视频 C++ 节点读取的启停开关。Wheeltec 依靠启动脚本不启动视频及 bringup 的 `enable_video` 控制，不能只改 YAML 的 enabled。

<a id="documents-external-workspace-integration-md-34-建图map_streamyaml"></a>
### 3.4 建图：`map_stream.yaml`

| 方向 | 模板话题 | 类型 | 配置键 | 外部责任 |
| --- | --- | --- | --- | --- |
| 外部 → CCS 输入探测/算法 | `/livox/lidar` | `livox_ros_driver2/CustomMsg` | `ros.inputs.lidar.topic/message_type/frame` | 驱动持续发布雷达，模板 frame=`livox_frame` |
| 外部 → CCS 输入探测/算法 | `/livox/imu` | `sensor_msgs/Imu` | `ros.inputs.imu.topic/message_type/frame` | 提供 IMU，模板 frame=`livox_frame` |
| 外部 → CCS 预览 | `/lio/cloud_registered_body` | `sensor_msgs/PointCloud2` | `ros.stream.cloud.topic/message_type/frame/coordinates` | 点云含 x/y/z；模板 frame=`body_lio`，coordinates=`sensor` |
| 外部 → CCS 预览 | `/lio/odometry` | `nav_msgs/Odometry` | `ros.stream.pose.topic/message_type/position_path/orientation_path` | `pose.pose.position`、`pose.pose.orientation`，与点云可按时间配对 |

原始雷达输入与预览点云不是同一个接口：仅有 `/livox/lidar` 不能替代算法输出的 PointCloud2。修改 `ros.inputs` 只修改 CCS 对输入的描述/探测，FAST-LIO 的订阅话题仍需在其参数文件或 remap 中配置。

需要同时核对以下约束：

- 点云和里程计的 `header.stamp` 有效且同一时间基准；模板同步容差 `sync.tolerance_seconds=0.05` 秒，位姿缓存 100 条。
- `ros.frames.map/preview/body/sensor` 与实际坐标语义一致。模板分别为 `lio_odom/odom/body_lio/body_lio`。
- `ros.body_from_sensor` 为代码使用的传感器到机体变换，应按实际标定和位姿语义填写；四元数不能全零。不同设备的外参不可互抄。
- `coordinates: sensor` 的点云需结合外参和位姿变换；`coordinates: map` 的点云已在相应世界坐标中，不能再次按机体系点云转换。
- 预览 frame 不同时提供可查询的 TF；模板预览 TF 查询超时 0.20 秒。改 `frame` 字符串不能替代真正的点坐标转换。
- 模板 `input_timeout_seconds=3.0`、`ready_timeout_seconds=60.0`。超时应覆盖真实启动耗时，不应掩盖缺失输入。

<a id="documents-external-workspace-integration-md-35-重定位relocalizationyaml"></a>
### 3.5 重定位：`relocalization.yaml`

| 方向 | 模板接口 | 类型 | 配置位置与要求 |
| --- | --- | --- | --- |
| CCS → 外部定位栈 | `/initialpose` | `geometry_msgs/PoseWithCovarianceStamped` | `ros.initial_pose_topic`；外部必须已有订阅者，frame 为 `ros.map_frame` |
| 定位栈/map_server → ROS | `/map_2d` | `nav_msgs/OccupancyGrid`（当前 map_server 路径） | `ros.map_topic`；Ground-Air 为 `/map` |
| 外部定位栈 → CCS | TF `map <- odom` | `/tf`、`/tf_static` 的标准 TF 消息 | `ros.map_frame/odom_frame`；提供真实定位变换 |

重定位栈就绪检查当前只检查地图/初始位姿话题可解析及 initialpose 有订阅者，并不完整验证栅格内容，因此联调还应检查地图消息。CCS 发布 initialpose 为非 latched；应先启动接收端再触发重定位。

在 `ros.stages` 按依赖顺序填写外部 `package/launch/args`。支持 `{map_id}`、`{map_dir}`、`{map_root}`、`{map_pcd}`、`{map_yaml}` 替换，不是任意 shell 命令。外部 launch 必须接受实际传入的参数。Scout/Wheeltec 默认稳定判据为 10 Hz、10 个样本、平移波动不超过 0.10 m、yaw 波动不超过 2°，等待上限 30 秒。Ground-Air profile 使用首个有效 TF 后连续回报模式，见其 `tf_reporting`。

<a id="documents-external-workspace-integration-md-4-任务执行需要外部订阅反馈及运动接口"></a>
## 4. 任务执行需要外部订阅、反馈及运动接口

<a id="documents-external-workspace-integration-md-41-通用任务契约"></a>
### 4.1 通用任务契约

| 方向 | 默认话题 | 类型 | 配置键 |
| --- | --- | --- | --- |
| CCS 协调器 → 执行适配器 | `/epgeneral_task_control/execution_command` | `epgeneral_task_control/TaskExecutionCommand` | `ros.command_topic` |
| 执行适配器 → CCS 协调器 | `/epgeneral_task_control/execution_feedback` | `epgeneral_task_control/TaskExecutionFeedback` | `ros.feedback_topic` |
| CCS 协调器 → 可选消费者 | `/epgeneral_task_control/task_status` | `std_msgs/String` | `ros.status_topic` |

可以使用随包导航适配器，也可以由外部工作空间实现适配器；同一设备不要同时运行多个执行同一命令的适配器。只运行通用协调器不会自动控制底盘或 MAVROS。

当前 [TaskExecutionCommand.msg](../EPGeneral_task_control/msg/TaskExecutionCommand.msg) 包含 **SCHEDULE=1、CANCEL=2、STOP=3、PREPARE=4、UNLOAD=5、EMERGENCY_STOP=6**。接口参考已同步六个常量，新接入仍以当前 `.msg` 为准。

| 消息 | 必须处理的字段 | 说明 |
| --- | --- | --- |
| command 与 feedback | `request_id/task_id/subtask_id/device_id/execution_id`：string；`revision`：uint32 | 反馈与当前请求身份一致，避免串任务 |
| command | `action`：uint8；`xml_path/frame_id/map_id`：string；`scheduled_at`：time | 读取任务 XML，核对地图与坐标系，按 UTC 调度 |
| feedback | `state`：string；`waypoint_index/waypoint_count`：int32；`progress`：float64 | 准备、就绪、运行和终态反馈，进度按当前协议/适配器语义（完成为 1.0） |
| feedback | `position`：geometry_msgs/Point；`error_code/message`：string | 任务参考系内真实位置与失败原因 |

`storage.directory` 中的 XML 绝对路径须对执行器可读。模板准备反馈阈值 2 秒，执行反馈阈值 5 秒，UTC 容差 2 秒；适配器持续反馈周期应小于相应阈值。急停必须反映真实执行结果，普通 STOP 与原生急停闭锁不能等同。

<a id="documents-external-workspace-integration-md-42-使用随包导航适配器时"></a>
### 4.2 使用随包导航适配器时

| 外部责任 | 默认接口 | 类型/要求 | `task_control.yaml` 配置 |
| --- | --- | --- | --- |
| 提供导航 Action 服务端 | `/move_base` | `move_base_msgs/MoveBaseAction` | `adapter.navigation_action` |
| 发布里程计 | `/fastlio_odom` | `nav_msgs/Odometry`，位姿新鲜 | `adapter.odom_topic`；`pose_timeout_seconds=2.0` |
| 接收停车速度并作用到驱动 | `/cmd_vel` | `geometry_msgs/Twist` | `adapter.zero_velocity_topic` |
| 提供导航启动文件 | `scout_navigation/navigation_teb.launch` | 能加载对应地图并建立导航 Action | `adapter.navigation_launch_package/navigation_launch_file` |
| 提供定位及机体 TF | 任务 `map` 系与里程计参考系之间的有效变换 | 与 Odometry 的 frame 一致 | `ros.map_frame` 与外部 TF 配置 |

`/move_base` 是 Action 名称空间，不是单独一个普通 topic；应提供其 goal/cancel/status/feedback/result 整套接口。停车配置模板为 20 Hz 连续 10 次零 Twist，外部底盘或速度仲裁器必须实际接收并执行该命令。

任务适配器的 `active_map_state_file`、`navigation_map_root`、`navigation_map_yaml` 要与重定位一致。不能仅把旧状态文件写成 localized 就代替当前有效定位。选择 `navigation_task_control.launch` 或兼容的 `scout_task_control.launch` 会同时运行协调器和导航适配器，无需另开一份通用协调器。

<a id="documents-external-workspace-integration-md-5-ros-话题之外的外部协作配置"></a>
## 5. ROS 话题之外的外部协作配置

<a id="documents-external-workspace-integration-md-51-建图-launch保存服务与文件工具"></a>
### 5.1 建图 launch、保存服务与文件工具

由 `map_stream.yaml` 的 `integrations.backend` 决定真正执行的后端；共享模板未写 backend 时走 Go2 兼容路径。不能把所有 integrations 字段都当作每种设备必须提供的运行接口。

| 后端 | 外部应提供 | 具体配置/约定 |
| --- | --- | --- |
| `go2_accumulator` | `go2_tf_manager`、`go2_pose_adapter`、`cloud_frame_adapter`、`go2_map_accumulator` 的被 include launch；`fast_lio/fastlio_mapping` 与 `go2_bringup` 参数文件 | CCS 的 `mapping_prerequisites.launch` 和 `fast_lio_mapping.launch` 仍依赖外部包；修改 `integrations.mapping_prerequisites.*`、`integrations.fast_lio.*` |
| `go2_accumulator` | legacy profile 的 /go2_map_accumulator/save 与 go2_map_tools/pcd_to_pgm.launch；Robot2/Robot3 为 /go2_map_accumulator/save_map 与 go2_mapping/export_occupancy.launch | `integrations.map_accumulator.service/setup_file`、`integrations.pgm.*`；保存脚本无请求参数调用服务，外部必须提供兼容调用契约 |
| `scout_finalize` | Scout 的 FAST-LIO、pointcloud_mapper、TF/pose adapter 及 `scout_map_tools/finalize_map.py` | `integrations.scout` 下的 `*_package/*_launch`、`finalize_executable/map_root/filtered_pcd_filename` |
| `managed_finalize` | Wheeltec 或其他匹配生命周期的 FAST-LIO、mapper、TF/pose adapter、finalizer | `integrations.managed` 同类字段，另须配置实际 `fast_lio_node/mapper_node/tf_node/geometry_tf_node/pose_node` |
| `ground_air_service` | 原生建图阶段、保存 launch 和地图文件 | `integrations.ground_air.expected_nodes/save_package/save_launch/map_root/saved_*_filename`；当前为 `car_bringup/save_mapping.launch` |

Scout/Wheeltec finalizer 要兼容 `rosrun <package> <executable> <map_name> --replace-raw`，在配置 map_root 下相应地图目录产出 `public_map.pcd/map.pgm/map.yaml`。Ground-Air 保存 wrapper 执行配置的 save launch，并检查相应成果；`/ground_air/mapping/save` 是算法保存链路配合项，不能仅凭配置名推断其 `.srv` 类型。

**不需要实现的占位接口：** Scout 的 `/unused_scout_map_service`、Wheeltec 的 `/unused_wheeltec_map_service`、两者的 `unused.launch` 是兼容配置结构保留项，相应 finalize 后端不要求为这些名称额外创建服务或 launch。

保存服务的外部 `.srv` 定义未包含在本目录，尤其 Go2 的 save 服务不能从无参调用推断它一定是 Trigger 或 Empty。应在设备用 `rosservice type`、`rossrv show` 核对。

<a id="documents-external-workspace-integration-md-52-地图任务和状态文件必须对齐"></a>
### 5.2 地图、任务和状态文件必须对齐

| 配置位置 | 与谁保持一致 | 外部要求 |
| --- | --- | --- |
| 建图 `artifacts.accumulator_pcd_path/source_pcd_path/source_pgm_path/source_yaml_path` | 对应算法/地图工具真实输出位置；部分后端按会话地图名派生路径 | 产出本次会话的新文件；不能用旧文件冒充保存成功 |
| 建图 `integrations.scout/managed/ground_air.map_root` | 外部保存器/finalizer 的地图根目录 | 目录可写；文件名及子目录规则一致 |
| 建图 `artifacts.workspace_root/archive_root` | CCS 会话及归档目录 | 有足够空间和读写权限；模板空间下限通常 5 GiB，Ground-Air profile 为 1 GiB |
| 重定位 `storage.map_root` | 任务 `adapter.navigation_map_root`、UDP pgm_file 的 `source.map_root` | 读取同一份下载地图 |
| 重定位 `storage.active_map_state_file` | 任务 `adapter.active_map_state_file`、UDP pgm_file 的 `source.state_file` | 使用同一份活动地图状态，不各写一个副本 |
| 重定位 `storage.pcd_filename` | 外部定位器输入 | 按后端为 `public_map.pcd` 或 `cloud_map.pcd` |
| 任务 `storage.directory` | command 的 `xml_path` | 外部执行器可读取持久化 XML |

栅格 `map.yaml` 的 image、resolution、origin 等必须与实际 PGM 及任务坐标系一致。建图预览 frame 与最终地图 frame 可以不同，但需要真实一致的变换和成果转换，不能只改元数据声明。

<a id="documents-external-workspace-integration-md-53-网络和授时"></a>
### 5.3 网络和授时

| 通道 | 端侧/地面站方向 | 配置位置 |
| --- | --- | --- |
| MQTT TCP 1883 | 端侧连接地面站 Broker | `epgeneral_mqtav.yaml:mqtt.ground_station_ip/port` |
| 遥测 UDP 14560 | 端侧 → 地面站 | `udp_telemetry.yaml:network.destination_host/destination_port` |
| 建图 UDP 14561 / 14562 | 地面站 → 端侧控制 / 端侧 → 地面站数据状态 | `map_stream.yaml:network` |
| 建图 HTTP TCP 14600 | 地面站访问端侧地图/预览资源 | `map_stream.yaml:http` |
| 任务 UDP 14563 / 14564 | 地面站 → 端侧控制 / 端侧 → 地面站状态 | `task_control.yaml:network` |
| 重定位 UDP 14565 / 14566 | 地面站 → 端侧控制 / 端侧 → 地面站状态 | `relocalization.yaml:network` |
| SRT UDP 9000 | 端侧 Listener，地面站 Caller 连接 | `video.yaml:srt_bind_address/srt_port/srt_latency_ms` |
| NTP UDP 123 | 端侧向授时服务器同步 | profile 中 `timesyncd-ccs.conf` 与启动脚本授时设置 |

重定位还需能够访问地面站命令提供的地图下载 URL，具体地址端口以实际地面站配置为准。`device.yaml` 的 `device.ip` 是设备自身地址，`0.0.0.0` 仅用于本机监听，不能作为地面站目的地址。

修改地面站地址时逐份更新 MQTT、UDP、建图、重定位、任务及授时配置。特别注意 `epgeneral_udp_telemetry.launch` 的 `destination_host` 默认 `192.168.151.100`，会覆盖 YAML；启动时必须显式传实际值。仅设置 `CCS_GROUND_STATION_IP` 不会重写所有 YAML，Ground-Air 脚本也不提供统一的该变量替换逻辑。

任务按 UTC 时间执行。按照设备部署方式配置 NTP 后，用 `timedatectl timesync-status` 核实服务器和同步状态。一键脚本的授时预检失败会阻止启动新组件。

<a id="documents-external-workspace-integration-md-6-ground-air-专属外部契约"></a>
## 6. Ground-Air 专属外部契约

本节只适用于 `ground_air_agv`，其他设备不需要构建 `ground_air_msgs`。当前 CCS 提供阶段管理/桥接节点，算法工作空间提供原生定位、建图及任务执行能力。

| 提供者与方向 | 接口 | 类型/要求 | 配置方法 |
| --- | --- | --- | --- |
| CCS 阶段管理器提供，建图/重定位控制调用 | `/ground_air/system/set_stage` | `ground_air_msgs/SetSystemStage` | 使用随包 stage manager；不是要求外部重复实现一个同名服务 |
| CCS 阶段管理器发布 | `/ground_air/system/stage`、`/ground_air/system/stage_detail` | `std_msgs/UInt8`、`std_msgs/String`，latched | 阶段 0 基础、1 建图、2 重定位 |
| 外部定位服务，CCS 调用 | `/ground_air/load_map` | `ground_air_msgs/LoadMap` | 当前 initial pose adapter 中固定服务名，重命名需配套 remap/适配 |
| 外部定位服务，CCS 调用 | `/ground_air/relocalize` | `ground_air_msgs/Relocalize` | initialpose 转换为原生重定位请求，使用初始猜测 |
| 外部车辆节点发布 | `/ground_air/vehicle_status` | `ground_air_msgs/VehicleStatus` | `adapter.vehicle_status_topic` |
| 外部任务节点发布 | `/ground_air/mission/status` | `ground_air_msgs/MissionStatus` | `adapter.mission_status_topic` |
| 外部节点维护参数 | `/ground_air/localized` | bool，实时定位有效状态 | `adapter.localization_param`；不是 ROS 话题 |
| 外部服务，CCS 调用 | `/ground_air/prepare_ground` | `std_srvs/Trigger` | `adapter.prepare_ground_service` |
| 外部服务，CCS 调用 | `/ground_air/mission/submit` | `ground_air_msgs/SubmitMission` | `adapter.mission_submit_service` |
| 外部服务，CCS 调用 | `/ground_air/mission/start`、`/ground_air/mission/cancel` | `std_srvs/Trigger` | `adapter.mission_start_service/mission_cancel_service` |
| 外部服务，CCS 调用 | `/ground_air/emergency_stop` | `ground_air_msgs/SetEmergencyStop` | `adapter.emergency_stop_service`；需真正闭锁并回报成功 |

外部工作空间须提供 `car_bringup/task_system.launch`，在 `adapter.task_launch_package/task_launch_file` 指定。当前 profile 限制线速度 0.1 m/s、角速度 0.2 rad/s，航点停留 2 秒，服务超时 10 秒。持久化急停文件由 `adapter.emergency_lock_file` 指定，应保留在 CCS 可写目录。

外部消息和服务完整定义不在本仓库，交付时用 `rosmsg show` / `rossrv show` 检查与源码访问字段一致。不要根据接口名称自行发明服务请求格式。

建图 profile 的 expected_nodes 必须对应原生建图实际节点，包括 `/fast_lio_node`、`/fastlio_odometry_to_px4`、`/ground_filter_node`、`/noground_trans_node`、`/dynamic_mapping`、`/ground_air_map_recorder`、`/ground_air_world_tf_owner`、`/ground_air_start_mapping` 及两个静态 TF 节点。`odom <- camera_init`、`base_link <- body` 的静态变换由一键脚本持有，避免阶段切换时重复广播。阶段请求按 caller/map_id 归属，建图与重定位互斥。

Ground-Air 重定位 profile 使用局部 `ros_package_path_prepend/exclude` 和 `cmake_prefix_path_exclude` 选择 CCS override 的 `car_bringup/relocalization_system.launch`，须按 [Ground-Air 部署资料](devices/ground_air_agv/DEPLOYMENT_GUIDE.md#documents-ground-air-agv-deployment-md) 安装配套 override，不能只复制 YAML 或全局改写 ROS_PACKAGE_PATH。

<a id="documents-external-workspace-integration-md-7-六套设备-profile-的实际话题差异"></a>
## 7. 六套设备 profile 的实际话题差异

下表保留四类平台的摘要，Go2 EDU 列仅指 legacy QRD_001；原生 Robot2/Robot3 的差异另见下表，逐配置完整键/类型见[配置话题清单](INTERFACE_REFERENCE.md#documents-config-topic-reference-md)。

以下为仓库配置值，不代表已在线探测。完整原件分别见 [Go2](../devices/go2/profiles/go2_edu/config)、[Scout](../devices/scout_mini/profiles/scout_mini/config)、[Wheeltec](../devices/wheeltec_r550p/profiles/wheeltec_r550p/config)、[Ground-Air](../devices/ground_air_agv/profiles/ground_air_agv/config)。

| 项目 | Go2 EDU | Scout Mini | Wheeltec R550P | Ground-Air AGV |
| --- | --- | --- | --- | --- |
| 状态源 | `/livox/lidar`，CustomMsg 新鲜度 | `/scout_status`，ScoutStatus 新鲜度 | `/odom`，Odometry 新鲜度 | `/mavros/state`，State 字段 |
| 电池源 | 禁用 | `/BMS_status`，ScoutBmsStatus 的 battery_voltage | `/PowerVoltage`，Float32.data | `/mavros/battery`，BatteryState |
| UDP 位姿 | `/lio/odometry` | `/scout/odom` | `/fastlio_odom` | `/mavros/local_position/pose` 和 `/Odometry` |
| UDP IMU | `/livox/imu` | `/livox/imu` | `/livox/imu` | `/mavros/imu/data` |
| 建图点云 | `/lio/cloud_registered_body` | `/cloud_registered_body` | `/cloud_registered_body` | `/cloud_registered` |
| 建图位姿 | `/lio/odometry` | `/fastlio_odom` | `/fastlio_odom` | `/Odometry` |
| 点云 frame / coordinates | body_lio / sensor | body / sensor | body / sensor | camera_init / map |
| 建图后端 | go2_accumulator | scout_finalize | managed_finalize | ground_air_service |
| 重定位地图话题 | 配置禁用 | `/map_2d` | `/map_2d` | `/map` |
| 视频输入 | `/camera/color/image_raw` | `/camera/color/image_raw` | 当前脚本不启动视频 | `/a8_cam/image_raw` |
| 一键脚本任务路径 | 不启动任务 | 导航适配器 | 导航适配器 | ground_air 适配器 |

Scout 的状态 mapping 为 `system_status: fault_code`、`mode: control_mode`；电池只取电压，其他量为 null。需要匹配驱动提供的 `scout_msgs/ScoutBmsStatus`，相关补丁见 `devices/scout_mini/profiles/scout_mini/patches`。

Scout 的 UDP 位姿 `/scout/odom` 与建图/任务 `/fastlio_odom` 不同；Scout/Wheeltec 的 FAST-LIO 可用性监测仍指向 `/Odometry`。这些不是同一键的别名，外部应提供各自接口，或经核实后分别修改相关 source。legacy Go2 未启用的任务配置仍留有 `192.168.151.100`，未来启用前必须补齐设备适配器并改为实际地面站地址。

| 原生 Go2 项目 | Robot2 / QRD_002 | Robot3 / QRD_003 |
| --- | --- | --- |
| 状态 / 连接 | /go2/control/enabled，Bool.data，未设置独立 connection | 同 armed；connection=/go2/state/low_state，Go2LowState，3秒 |
| 电池 / 遥测 IMU / 位姿 | /go2/battery_state；/go2/imu；/odom_nav | 相同，BatteryState / Imu / Odometry |
| 建图 | /livox/imu + /lio/cloud_registered_body + /lio/odometry | 相同，算法 IMU 与遥测不同 |
| 相机 | profile RGB 640×480@30；以本机脚本驱动参数为准 | 自动选择，可选原样序列号；640×480@15，新鲜帧后启动 SRT |
| 重定位 / 任务 | enabled=true；健康 Bool + TF；任务 attach | 相同，独立急停文件，人工复位后重新下发 |
| 根脚本授时 / 日志 | Robot2 原脚本策略，workspace/logs/managed | SNTP只测可用，任务UTC仍2秒；~/.ros/ccs_edge_ws/启动时间_纳秒_PID |

<a id="documents-external-workspace-integration-md-8-配置示例与实施步骤"></a>
## 8. 配置示例与实施步骤

<a id="documents-external-workspace-integration-md-81-把已有里程计接入遥测"></a>
### 8.1 把已有里程计接入遥测

假设外部发布 `/robot/local_odom`，类型为 `nav_msgs/Odometry`。在选定 profile 原有 `vision_pose` descriptor 中替换 source，保留原有 name/display_name/type/level：

```yaml
source:
  topic: /robot/local_odom
  message_type: nav_msgs/Odometry
  mapping:
    position: pose.pose.position
    orientation: pose.pose.orientation
```

这只是 source 子段，不能用它覆盖整份 YAML。PoseStamped 的字段少一层 pose，必须同步修改 message_type 与 mapping。若需要把同一里程计用于任务，还要另改 `task_control.yaml:adapter.odom_topic`；若用于建图预览，再改 `map_stream.yaml:ros.stream.pose` 并核对坐标系。

<a id="documents-external-workspace-integration-md-82-无飞控的底盘状态接入"></a>
### 8.2 无飞控的底盘状态接入

以下替换 `epgeneral_mqtav.yaml` 中 `ros.state` 与 `ros.battery`，保留 MQTT 等其他配置：

```yaml
state:
  topic: /robot/local_odom
  message_type: nav_msgs/Odometry
  connected_on_message: true
  timeout_seconds: 3.0
  mapping: {connected: null, armed: null, system_status: null, mode: null}
battery:
  enabled: false
```

`state/battery` 必须置于 `ros:` 下。若有真实电压话题，可参照 Wheeltec profile 配置 Float32 的 data 字段。

<a id="documents-external-workspace-integration-md-83-建图定位任务的改动顺序"></a>
### 8.3 建图/定位/任务的改动顺序

1. 选与硬件匹配的 profile，核实实际运行目录，备份原配置。
2. 外部工作空间构建驱动、消息、算法和导航；加载 underlay，再构建/加载 CCS overlay。
3. 用 `rostopic type/echo/hz` 核实真实名字、类型、字段、时间戳和 frame；按第 3 节填写各 source。
4. 配置外部算法的雷达/IMU输入、标定外参和 TF；再填写 CCS 的点云坐标模式及 frame。
5. 选择建图 backend，填可读 setup.bash、可调用 package/launch、保存工具和可写输出目录；排除旧会话残留的同名进程。
6. 对齐重定位 stages、初始位姿话题、地图路径和活动状态文件；外部定位器必须实际读取传入地图。
7. 配置导航或 Ground-Air 适配器，确认反馈、停车和急停链路。无任务适配器的设备保持任务不启动。
8. 统一 device ID、本机 IP、地面站地址与授时；重新启动受影响节点，按第 9 节联调。

<a id="documents-external-workspace-integration-md-84-显式选择配置文件启动"></a>
### 8.4 显式选择配置文件启动

下列命令在 ROS Linux 设备执行，`PROFILE_DIR` 改为真实目录。各命令对应独立终端，按需要选择，不与一键栈重复运行：

```bash
export PROFILE_DIR=/home/robot/ccs_edge_ws/config/my_robot

roslaunch epgeneral_mqtav epgeneral_mqtav.launch \
  device_config_file:="$PROFILE_DIR/device.yaml" \
  config_file:="$PROFILE_DIR/epgeneral_mqtav.yaml"

roslaunch epgeneral_udp_telemetry epgeneral_udp_telemetry.launch \
  device_config_file:="$PROFILE_DIR/device.yaml" \
  telemetry_config_file:="$PROFILE_DIR/udp_telemetry.yaml" \
  destination_host:=192.168.50.101 destination_port:=14560

roslaunch epgeneral_map_stream epgeneral_map_stream.launch \
  device_config_file:="$PROFILE_DIR/device.yaml" \
  mapping_config_file:="$PROFILE_DIR/map_stream.yaml"

roslaunch epgeneral_relocalization epgeneral_relocalization.launch \
  device_config_file:="$PROFILE_DIR/device.yaml" \
  config_file:="$PROFILE_DIR/relocalization.yaml"

roslaunch epgeneral_task_control navigation_task_control.launch \
  device_config_file:="$PROFILE_DIR/device.yaml" \
  task_config_file:="$PROFILE_DIR/task_control.yaml"

roslaunch epgeneral_video_srt epgeneral_video_srt.launch \
  device_config_file:="$PROFILE_DIR/device.yaml" \
  video_config_file:="$PROFILE_DIR/video.yaml"
```

使用外部自定义任务适配器时将任务入口换为 `epgeneral_task_control.launch`，另启动自己的适配器；Ground-Air 使用 `epgeneral_ground_air_control/ground_air_task_control.launch`。源码中的 `deployment.enabled/state` 多为元数据，不能作为通用启停开关；实际以启动入口及节点读取逻辑为准。

<a id="documents-external-workspace-integration-md-9-联调验收与常见问题"></a>
## 9. 联调验收与常见问题

先检查环境和消息，再启动所选功能，按实际 profile 替换命令中的话题：

```bash
rospack find livox_ros_driver2
rosmsg show epgeneral_task_control/TaskExecutionCommand
rosmsg show epgeneral_task_control/TaskExecutionFeedback
rostopic type /livox/lidar
rostopic hz /livox/lidar
rostopic type /fastlio_odom
rostopic echo -n 1 /fastlio_odom/header
rostopic info /initialpose
rostopic type /map_2d
rosrun tf tf_echo map odom
rostopic info /cmd_vel
rostopic type /move_base/goal
rostopic echo -n 1 /epgeneral_udp_telemetry/diagnostics
timedatectl timesync-status
ss -lntup
```

检查无副作用的服务类型与结构，不用真实任务/急停服务调用代替接口检查：

```bash
# 仅 Go2 保存后端
# 原生 Robot2/Robot3；legacy 使用其 config 指定名称
rosservice type /go2_map_accumulator/save_map
# 仅 Ground-Air
rosservice type /ground_air/system/set_stage
rossrv show ground_air_msgs/SetSystemStage
rossrv show ground_air_msgs/SubmitMission
rossrv show ground_air_msgs/SetEmergencyStop
rosparam get /ground_air/localized
```

| 验收项 | 应达到的结果 |
| --- | --- |
| 状态/遥测 | 类型和字段可读；断开源后正确体现未知/超时；地面站收到实际数据 |
| 视频 | 相机话题持续有帧，地面站可以建立 SRT 连接并解码 |
| 建图 | prepare 依赖检查通过，start 后有预览；保存生成本次 PCD/PGM/YAML，结束释放所属算法资源 |
| 重定位 | 地图安装到约定位置，有 initialpose 接收者，获得有效 map←odom，并更新同一活动状态文件 |
| 任务 | 准备反馈正常、地图与 TF 一致、UTC 同步；在受控现场验证执行/停止/急停反馈与真实执行器一致 |

| 现象 | 优先检查 |
| --- | --- |
| 消息类加载失败 | 外部消息包是否构建、是否 source、package/Message 是否准确 |
| 有话题却字段取不到 | PoseStamped 与 Odometry 路径区别、mapping 的 null 和实际字段 |
| YAML 改了地址仍发旧地址 | 实际配置副本、UDP launch destination_host 覆盖、旧节点是否重启 |
| 原始雷达正常但无建图预览 | 是否有 PointCloud2/配对里程计、时间差、frame/TF/外参 |
| 重定位等待超时 | external launch 是否退出、地图话题及 initialpose 订阅者、map←odom 是否产生 |
| PGM 状态异常 | 是话题模式还是 pgm_file 模式；状态文件和 map_root 是否一致 |
| 任务收到了但车辆不执行 | 是否有且仅有一个适配器、反馈身份、Action/原生服务、地图/实时定位、UTC |

<a id="documents-external-workspace-integration-md-10-新修复的集成要求"></a>
## 10. 新修复的集成要求

原生 Go2 导航 reset 为 std_srvs/Trigger，SDK enable/disable 为 std_srvs/SetBool；不要换成 Empty。调用成功与新鲜 disabled 状态须同时确认。MQTT armed 的锁存状态不能当周期心跳；定位 TF 也不能代替新鲜 /localization/ok。

GO2_3 的根脚本隔离终端进程组，先停任务消费/适配器，再停用底盘、逆序清组件，最后只停自建 master。协调器读同一急停文件，在协商/prepare/commit 拒绝已知或传输中新产生的锁存；损坏文件同样拒绝。锁存失败不自动重试，定位临时失败继续重试；人工复位不使能、不自动执行旧任务。

建图保存链路为 accumulator → 本次 session PCD 快照 → 原子发布 source_pcd_path → PGM/YAML。首次 export 不存在不应阻止转换，也不能用旧 PCD 顶替。所有间接调用的 Shell 必须 LF 无 BOM；此前 bash\r 错误发生在协商阶段。配置模板日志路径仍在 session_dir 通过校验，可选 epgeneral_map_stream.launch 的 log_dir 将日志映射到受控 sessions/<session_id>，地图/任务/锁/安全文件不迁移。存储目录 OSError 返回 ARTIFACT_STORAGE_UNAVAILABLE 并释放会话，修复目录后重试。

新增设备同步修改脚本、预检中的固定 ID/网卡/IP/路径及平台记录，仅 export CCS_GROUND_STATION_IP 不会重写 MQTT 等 YAML。GO2_3 授时只检测 SNTP 可用、不设时钟；任务 UTC 容差独立保留为2秒。首次和增量验收、部署清单及回滚边界见从零指南。

<a id="documents-external-workspace-integration-md-11-依据与后续维护"></a>
## 11. 依据与后续维护

主要依据为 [共享 YAML](../EPGeneral_device_config/config)、[各设备部署配置](../devices)、[ROS 任务消息](../EPGeneral_task_control/msg)、[UDP 节点](../EPGeneral_udp_telemetry/src/epgeneral_udp_telemetry/node.py)、[建图节点](../EPGeneral_map_stream/src/epgeneral_map_stream/node.py)、[重定位桥接](../EPGeneral_relocalization/src/epgeneral_relocalization/ros_bridge.py)、[导航适配器](../EPGeneral_task_control/src/epgeneral_task_control/scout_adapter.py)、[Ground-Air 任务适配器](../devices/ground_air_agv/EPGeneral_ground_air_control/src/epgeneral_ground_air_control/task_adapter.py) 及相应 launch/scripts。

逐键参数范围及更多启动环境变量见 [设备内接口与配置参考](INTERFACE_REFERENCE.md#documents-interface-reference-md)，部署流程见 [使用手册](USER_MANUAL.md#documents-user-manual-md)。当说明与实现不一致时，以当前配置解析器、`.msg` 和实际使用的启动入口为准；外部工作空间的消息/服务定义、标定结果和运行状态需要在设备上另行核验。

<a id="documents-config-topic-reference-md"></a>

<a id="documents-config-topic-reference-md-配置话题类型与服务填写清单"></a>
# 配置话题、类型与服务填写清单

适用 CCS 0.24.0 当前源码及 `epgeneral_task_control` 0.6.3，更新于 2026-09-16。先使用本清单对照设备接口，再查[完整参数参考](INTERFACE_REFERENCE.md#documents-interface-reference-md)填写超时、路径和约束；从零安装见[部署指南](USER_MANUAL.md#documents-deployment-guide-md)。下面数值来自六个 profile 的实际 YAML，表示当前配置要求，不表示每个话题都已完成实机验收。

<a id="documents-config-topic-reference-md-填写方法"></a>
## 填写方法

1. 在相应阶段由外部驱动/算法提供数据，用 rostopic type/info、rosmsg show、带超时的 echo 和 hz 核实绝对话题名、消息类、字段、header.frame_id、时间戳与频率。区分常驻硬件和按需算法：空闲时无算法话题可以是预期行为。
2. 可配置类型写成 package/Message，大小写精确，不带 .msg；动态字段用点分路径，例如 Odometry 的 pose.pose.position，PoseStamped 的 pose.position。null 表示未知，不填伪造值。
3. 表中“代码固定”表示只可通过 YAML 改名字，不能凭空增加 message_type 改掉订阅类型；不同设备消息需真实适配节点。话题名相同但 MD5 不同仍不能通信。
4. 时间用秒，位姿/外参平移用米，角速度用 rad/s，四元数按 x/y/z/w；不得只换 frame 名称冒充坐标变换。source 中的字段值及单位以真实驱动为准。
5. 修改实际运行 config/profile，重启受影响节点；新设备同步更新平台 ID/IP、正式 UDP 描述和设备外参。默认共享配置混有示例路径，不能直接整套上机。

<a id="documents-config-topic-reference-md-七份-yaml-的责任"></a>
## 七份 YAML 的责任

| 文件 | ROS 配置位置 | 谁提供/消费 | 填写注意 |
| --- | --- | --- | --- |
| device.yaml | 无 ROS 话题 | 所有 CCS 通信包读取 ID/IP | schema_version=1，device.id/device.ip 对齐平台 |
| epgeneral_mqtav.yaml | ros.connection/state/battery/mission | 外部或任务节点 → MQTT | topic/message_type/mapping；mission 的 String.data 是任务摘要 JSON |
| udp_telemetry.yaml | descriptors[].source | 外部 → 遥测 | pose/imu/text_status 为动态消息；availability/pointcloud_status 用 AnyMsg 到达时间 |
| video.yaml | image_topic/image_message_type | 相机 → SRT | 仅 Image 或 CompressedImage；参数 enabled 不控制 C++ 启停 |
| map_stream.yaml | ros.inputs/stream/frames；integrations | 原始探测、预览输入、外部保存接口 | backend 对应真正的外部工具；输入与预览不能混用 |
| relocalization.yaml | ros.*_topic、frames、stages | 定位器发布 initialpose，接收地图/健康/TF | enabled 实际控制本包；旧 localized 文件不等于实时定位 |
| task_control.yaml | ros.*_topic、adapter.* | 协调器 ↔ 适配器 ↔ 底盘/导航 | 内部消息/固定类型/服务类型均要匹配；状态文件和定位共用 |

<a id="documents-config-topic-reference-md-通用类型和语义"></a>
## 通用类型和语义

- MQTT 的 ros.connection 可选；配置后以独立周期消息及 timeout_seconds 判断 connected。QRD_003 使用 /go2/state/low_state，3 秒超时；armed 仍从锁存 /go2/control/enabled 的 Bool.data 读取。不要把只在变化时发布的锁存 Bool 当周期心跳。QRD_002 当前未配置 connection，保留旧行为，不把 Robot3 修复写成已同步。
- BatteryState.percentage 是 0..1 比例，voltage 为 V、current 为 A；没有百分比时 mapping.percentage=null，不能把电压当百分比。设备状态中的 mode/fault_code 保留其驱动语义。
- UDP 的 source.message_type 只适用于实际解码的源。AnyMsg 仅说明近期有消息：收到 Bool(false) 仍可显示来源可用，不能据此判断定位成功或运动已使能。正式 descriptor 的 name/display_name/type/level 参与协议契约，source 则连接本地驱动；不得为改 IMU 来源私自更改显示名而破坏严格哈希。
- pgm_file 的 topic 是契约占位名称，无 ROS 发布者/订阅者；实际读取 state_file 和 map_root。map_root、重定位 storage、任务 active_map_state_file 必须对齐。
- 任务 command/feedback 为 epgeneral_task_control/TaskExecutionCommand 和 TaskExecutionFeedback；协调器发布 command/接收 feedback，适配器相反。status_topic 为锁存 std_msgs/String 摘要，可给 MQTT mission。
- 导航 action 基名通常 /move_base，类型 move_base_msgs/MoveBaseAction。对应 /goal、/result、/feedback 为 MoveBaseActionGoal/Result/Feedback；/status 为 actionlib_msgs/GoalStatusArray，/cancel 为 actionlib_msgs/GoalID。停车话题为 geometry_msgs/Twist，不应把它填成 action 基名。
- /tf、/tf_static 均为 tf2_msgs/TFMessage（后者锁存）。重定位需要 map <- odom；原生 Go2 还要求新鲜 /localization/ok=True，临时单位 TF 不足以证明定位。
- UDP launch 默认输出 /epgeneral_udp_telemetry/link/udp_tx（锁存 std_msgs/Bool）和 /epgeneral_udp_telemetry/diagnostics（diagnostic_msgs/DiagnosticArray）；根脚本可重命名，如原生 Go2 的 /qrd/QRD_003/link/udp_tx、/qrd/QRD_003/diagnostics。这是输出，不能作为驱动输入填写。
- 外部保存服务由 underlay 提供，本仓库的保存脚本动态调用，无 .srv 类型选择配置。上线前记录 rosservice type 与 rossrv show；无参数调用 {} 及 success 响应不自动说明它就是 Trigger。不得根据相似名称猜类型。

<a id="documents-config-topic-reference-md-六套实际配置"></a>
## 六套实际配置

以下每行给出完整配置键、当前值、类型和方向；未启用/未配置项不会凭表格产生节点。所有路径均相对于各 profile 的 config。文件接口、参数和 action 已明确标识，不作为普通话题。


<a id="documents-config-topic-reference-md-qrd_001--go2_edu"></a>
### QRD_001 / go2_edu

[配置原件](../devices/go2/profiles/go2_edu/config) · [部署记录](devices/go2/DEPLOYMENT_RECORD.md#deploy-records-qrd-001-deployment-md)

| 文件与完整键 | 当前接口名 | ROS 类型 / 接口类别 | 方向、字段与生效条件 |
| --- | --- | --- | --- |
| `epgeneral_mqtav.yaml: ros.state.topic` | `/livox/lidar` | livox_ros_driver2/CustomMsg（message_type） | 接收；字段 {"connected": null, "armed": null, "system_status": null, "mode": null} |
| `udp_telemetry.yaml: descriptors[global_pose].source.topic` | `/lio/odometry` | nav_msgs/Odometry | ros_fields；字段 {'position': 'pose.pose.position', 'orientation': 'pose.pose.orientation'}；hold |
| `udp_telemetry.yaml: descriptors[imu].source.topic` | `/livox/imu` | sensor_msgs/Imu | ros_fields；字段 {'orientation': 'orientation', 'angular_velocity': 'angular_velocity', 'linear_acceleration': 'linear_acceleration'}；hold |
| `udp_telemetry.yaml: descriptors[livox_pointcloud].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 1.0s |
| `udp_telemetry.yaml: descriptors[livox_driver].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[fastlio2].source.topic` | `/lio/odometry` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[pgm_mapping].source.topic` | `/ccs/relocalization/pgm_file` | 无 ROS 类型 | file_status；不订阅；state_file=/home/nvidia/.ros/ccs_edge_dev/state/relocalization.json；map_root=/home/nvidia/go2_mid360_nav/maps/ccs_download；path_template={map_id}/map.pgm |
| `udp_telemetry.yaml: runtime.link_status_topic` | `/epgeneral_udp_telemetry/link/udp_tx` | std_msgs/Bool | 输出；支持 {device_id} |
| `udp_telemetry.yaml: runtime.diagnostics_topic` | `/epgeneral_udp_telemetry/diagnostics` | diagnostic_msgs/DiagnosticArray | 输出；支持 {device_id} |
| `video.yaml: image_topic` | `/camera/color/image_raw` | sensor_msgs/Image（image_message_type） | 接收；输出 640×480@30；外部相机先就绪 |
| `video.yaml: runtime.status_topic` | `~status` | std_msgs/String JSON |
| `map_stream.yaml: ros.inputs.lidar.topic` | `/livox/lidar` | livox_ros_driver2/CustomMsg（message_type） | 接收；prepare 原始探测；frame=livox_frame |
| `map_stream.yaml: ros.inputs.imu.topic` | `/livox/imu` | sensor_msgs/Imu（message_type） | 接收；prepare 原始探测；frame=livox_frame |
| `map_stream.yaml: ros.stream.cloud.topic` | `/lio/cloud_registered_body` | sensor_msgs/PointCloud2（message_type） | 接收；建图运行时预览；frame=body_lio；coordinates=sensor |
| `map_stream.yaml: ros.stream.pose.topic` | `/lio/odometry` | nav_msgs/Odometry（message_type） | 接收；建图运行时预览；字段 pose.pose.position/pose.pose.orientation |
| `map_stream.yaml: integrations.map_accumulator.service` | `/go2_map_accumulator/save` | 外部 ROS 服务；现场核验 .srv | go2_accumulator 实际调用；其他 backend 为兼容占位，不据此要求启动 Go2 |
| `relocalization.yaml: ros.initial_pose_topic` | `/initialpose` | geometry_msgs/PoseWithCovarianceStamped（代码固定） | 发布初始位姿，定位器订阅；当前 enabled=false |
| `relocalization.yaml: ros.map_topic` | `/map_2d` | nav_msgs/OccupancyGrid（外部地图约定） | 地图话题就绪检查，内容另验；当前 enabled=false |
| `relocalization.yaml: ros.localization_health_topic` | `/localization/ok` | std_msgs/Bool（代码固定） | 接收；必须为新鲜真值；当前 enabled=false |
| `task_control.yaml: ros.command_topic` | `/epgeneral_task_control/execution_command` | epgeneral_task_control/TaskExecutionCommand（代码固定） | 协调器→适配器；根脚本未启动任务 |
| `task_control.yaml: ros.feedback_topic` | `/epgeneral_task_control/execution_feedback` | epgeneral_task_control/TaskExecutionFeedback（代码固定） | 适配器→协调器；根脚本未启动任务 |
| `task_control.yaml: ros.status_topic` | `/qrd/QRD_001/task_status` | std_msgs/String（代码固定） | 协调器发布，锁存摘要；根脚本未启动任务 |

建图坐标：map=`lio_odom`，preview=`odom`，body=`body_lio`，sensor=`body_lio`；最终 artifacts.frame=`lio_odom`。外参取本机标定，不能复制本表所属设备的标定用于其他设备。

<a id="documents-config-topic-reference-md-qrd_002--go2_robot2"></a>
### QRD_002 / go2_robot2

[配置原件](../devices/go2/profiles/go2_robot2/config) · [部署记录](devices/go2/DEPLOYMENT_RECORD.md#deploy-records-qrd-002-deployment-md)

| 文件与完整键 | 当前接口名 | ROS 类型 / 接口类别 | 方向、字段与生效条件 |
| --- | --- | --- | --- |
| `epgeneral_mqtav.yaml: ros.connection.topic` | `/go2/state/low_state` | go2_control/Go2LowState（message_type） | 接收；周期消息；超时 3.0s |
| `epgeneral_mqtav.yaml: ros.state.topic` | `/go2/control/enabled` | std_msgs/Bool（message_type） | 接收；字段 {"connected": null, "armed": "data", "system_status": null, "mode": null} |
| `epgeneral_mqtav.yaml: ros.battery.topic` | `/go2/battery_state` | sensor_msgs/BatteryState（message_type） | 接收；字段 {"percentage": "percentage", "voltage": "voltage", "current": "current"} |
| `epgeneral_mqtav.yaml: ros.mission.topic` | `/qrd/{device_id}/task_status` | std_msgs/String（message_type）；展开为 /qrd/QRD_002/task_status | 接收；字段 {"value": "data"} |
| `udp_telemetry.yaml: descriptors[global_pose].source.topic` | `/odom_nav` | nav_msgs/Odometry | ros_fields；字段 {'position': 'pose.pose.position', 'orientation': 'pose.pose.orientation'}；hold |
| `udp_telemetry.yaml: descriptors[imu].source.topic` | `/go2/imu` | sensor_msgs/Imu | ros_fields；字段 {'orientation': 'orientation', 'angular_velocity': 'angular_velocity', 'linear_acceleration': 'linear_acceleration'}；hold |
| `udp_telemetry.yaml: descriptors[livox_pointcloud].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 1.0s |
| `udp_telemetry.yaml: descriptors[livox_driver].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[fastlio2].source.topic` | `/odom_nav` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[localization].source.topic` | `/localization/ok` | std_msgs/Bool | value_status；读取 Bool 值；false=unavailable；hold 保留 latched 状态 |
| `udp_telemetry.yaml: descriptors[chassis].source.topic` | `/go2/diagnostics` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[pgm_mapping].source.topic` | `/ccs/relocalization/pgm_file` | 无 ROS 类型 | file_status；不订阅；state_file=/home/unitree/ccs_edge_ws/run/state/relocalization.json；map_root=/home/unitree/ccs_edge_ws/maps/download；path_template={map_id}/map.pgm |
| `udp_telemetry.yaml: runtime.link_status_topic` | `/qrd/{device_id}/link/udp_tx` | std_msgs/Bool | 输出；支持 {device_id} |
| `udp_telemetry.yaml: runtime.diagnostics_topic` | `/qrd/{device_id}/diagnostics` | diagnostic_msgs/DiagnosticArray | 输出；支持 {device_id} |
| `video.yaml: image_topic` | `/camera/color/image_raw` | sensor_msgs/Image（image_message_type） | 接收；输出 640×480@30；外部相机先就绪 |
| `video.yaml: runtime.status_topic` | `~status` | std_msgs/String JSON |
| `map_stream.yaml: ros.inputs.lidar.topic` | `/livox/lidar` | livox_ros_driver2/CustomMsg（message_type） | 接收；prepare 原始探测；frame=livox_frame |
| `map_stream.yaml: ros.inputs.imu.topic` | `/livox/imu` | sensor_msgs/Imu（message_type） | 接收；prepare 原始探测；frame=livox_frame |
| `map_stream.yaml: ros.stream.cloud.topic` | `/lio/cloud_registered_body` | sensor_msgs/PointCloud2（message_type） | 接收；建图运行时预览；frame=body_lio；coordinates=sensor |
| `map_stream.yaml: ros.stream.pose.topic` | `/lio/odometry` | nav_msgs/Odometry（message_type） | 接收；建图运行时预览；字段 pose.pose.position/pose.pose.orientation |
| `map_stream.yaml: integrations.map_accumulator.service` | `/go2_map_accumulator/save_map` | 外部 ROS 服务；现场核验 .srv | go2_accumulator 实际调用；其他 backend 为兼容占位，不据此要求启动 Go2 |
| `relocalization.yaml: ros.initial_pose_topic` | `/initialpose` | geometry_msgs/PoseWithCovarianceStamped（代码固定） | 发布初始位姿，定位器订阅；按需定位 |
| `relocalization.yaml: ros.map_topic` | `/map_2d` | nav_msgs/OccupancyGrid（外部地图约定） | 地图话题就绪检查，内容另验；按需定位 |
| `relocalization.yaml: ros.localization_health_topic` | `/localization/ok` | std_msgs/Bool（代码固定） | 接收；必须为新鲜真值；按需定位 |
| `task_control.yaml: ros.command_topic` | `/epgeneral_task_control/execution_command` | epgeneral_task_control/TaskExecutionCommand（代码固定） | 协调器→适配器 |
| `task_control.yaml: ros.feedback_topic` | `/epgeneral_task_control/execution_feedback` | epgeneral_task_control/TaskExecutionFeedback（代码固定） | 适配器→协调器 |
| `task_control.yaml: ros.status_topic` | `/qrd/QRD_002/task_status` | std_msgs/String（代码固定） | 协调器发布，锁存摘要 |
| `task_control.yaml: adapter.navigation_action` | `/move_base` | move_base_msgs/MoveBaseAction（代码固定） | action 客户端→导航服务器 |
| `task_control.yaml: adapter.odom_topic` | `/odom_nav` | nav_msgs/Odometry（代码固定） | 接收 pose.pose.position/orientation |
| `task_control.yaml: adapter.zero_velocity_topic` | `/cmd_vel_nav` | geometry_msgs/Twist（代码固定） | 发布零速度，配置中的停车接口 |
| `task_control.yaml: adapter.localization_ok_topic` | `/localization/ok` | std_msgs/Bool（代码固定） | 接收 data，新鲜且为 true |
| `task_control.yaml: adapter.control_enabled_topic` | `/go2/control/enabled` | std_msgs/Bool（代码固定） | 接收 data；锁存控制状态 |
| `task_control.yaml: adapter.control_diagnostics_topic` | `/go2/diagnostics` | diagnostic_msgs/DiagnosticArray（代码固定） | 接收新鲜诊断；GO2 SDK bridge / motion_enabled |
| `task_control.yaml: adapter.navigation_reset_service` | `/go2_navigation_supervisor/reset` | std_srvs/Trigger（代码固定） | 调用，success 必须 true；不是 Empty |
| `task_control.yaml: adapter.control_enable_service` | `/go2_sdk_bridge_real/enable` | std_srvs/SetBool（代码固定） | 调用 data=true/false；再确认真实状态 |

建图坐标：map=`lio_odom`，preview=`odom`，body=`body_lio`，sensor=`body_lio`；最终 artifacts.frame=`odom`。外参取本机标定，不能复制本表所属设备的标定用于其他设备。

<a id="documents-config-topic-reference-md-qrd_003--go2_robot3"></a>
### QRD_003 / go2_robot3

[配置原件](../devices/go2/profiles/go2_robot3/config) · [部署记录](devices/go2/DEPLOYMENT_RECORD.md#deploy-records-qrd-003-deployment-md)

| 文件与完整键 | 当前接口名 | ROS 类型 / 接口类别 | 方向、字段与生效条件 |
| --- | --- | --- | --- |
| `epgeneral_mqtav.yaml: ros.connection.topic` | `/go2/state/low_state` | go2_control/Go2LowState（message_type） | 接收；周期消息；超时 3.0s |
| `epgeneral_mqtav.yaml: ros.state.topic` | `/go2/control/enabled` | std_msgs/Bool（message_type） | 接收；字段 {"connected": null, "armed": "data", "system_status": null, "mode": null} |
| `epgeneral_mqtav.yaml: ros.battery.topic` | `/go2/battery_state` | sensor_msgs/BatteryState（message_type） | 接收；字段 {"percentage": "percentage", "voltage": "voltage", "current": "current"} |
| `epgeneral_mqtav.yaml: ros.mission.topic` | `/qrd/{device_id}/task_status` | std_msgs/String（message_type）；展开为 /qrd/QRD_003/task_status | 接收；字段 {"value": "data"} |
| `udp_telemetry.yaml: descriptors[global_pose].source.topic` | `/odom_nav` | nav_msgs/Odometry | ros_fields；字段 {'position': 'pose.pose.position', 'orientation': 'pose.pose.orientation'}；hold |
| `udp_telemetry.yaml: descriptors[imu].source.topic` | `/go2/imu` | sensor_msgs/Imu | ros_fields；字段 {'orientation': 'orientation', 'angular_velocity': 'angular_velocity', 'linear_acceleration': 'linear_acceleration'}；hold |
| `udp_telemetry.yaml: descriptors[livox_pointcloud].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 1.0s |
| `udp_telemetry.yaml: descriptors[livox_driver].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[fastlio2].source.topic` | `/odom_nav` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[localization].source.topic` | `/localization/ok` | std_msgs/Bool | value_status；读取 Bool 值；false=unavailable；hold 保留 latched 状态 |
| `udp_telemetry.yaml: descriptors[chassis].source.topic` | `/go2/diagnostics` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[pgm_mapping].source.topic` | `/ccs/relocalization/pgm_file` | 无 ROS 类型 | file_status；不订阅；state_file=/home/unitree/ccs_edge_ws/run/state/relocalization.json；map_root=/home/unitree/ccs_edge_ws/maps/download；path_template={map_id}/map.pgm |
| `udp_telemetry.yaml: runtime.link_status_topic` | `/qrd/{device_id}/link/udp_tx` | std_msgs/Bool | 输出；支持 {device_id} |
| `udp_telemetry.yaml: runtime.diagnostics_topic` | `/qrd/{device_id}/diagnostics` | diagnostic_msgs/DiagnosticArray | 输出；支持 {device_id} |
| `video.yaml: image_topic` | `/camera/color/image_raw` | sensor_msgs/Image（image_message_type） | 接收；输出 640×480@15；外部相机先就绪 |
| `video.yaml: runtime.status_topic` | `~status` | std_msgs/String JSON |
| `map_stream.yaml: ros.inputs.lidar.topic` | `/livox/lidar` | livox_ros_driver2/CustomMsg（message_type） | 接收；prepare 原始探测；frame=livox_frame |
| `map_stream.yaml: ros.inputs.imu.topic` | `/livox/imu` | sensor_msgs/Imu（message_type） | 接收；prepare 原始探测；frame=livox_frame |
| `map_stream.yaml: ros.stream.cloud.topic` | `/lio/cloud_registered_body` | sensor_msgs/PointCloud2（message_type） | 接收；建图运行时预览；frame=body_lio；coordinates=sensor |
| `map_stream.yaml: ros.stream.pose.topic` | `/lio/odometry` | nav_msgs/Odometry（message_type） | 接收；建图运行时预览；字段 pose.pose.position/pose.pose.orientation |
| `map_stream.yaml: integrations.map_accumulator.service` | `/go2_map_accumulator/save_map` | 外部 ROS 服务；现场核验 .srv | go2_accumulator 实际调用；其他 backend 为兼容占位，不据此要求启动 Go2 |
| `relocalization.yaml: ros.initial_pose_topic` | `/initialpose` | geometry_msgs/PoseWithCovarianceStamped（代码固定） | 发布初始位姿，定位器订阅；按需定位 |
| `relocalization.yaml: ros.map_topic` | `/map_2d` | nav_msgs/OccupancyGrid（外部地图约定） | 地图话题就绪检查，内容另验；按需定位 |
| `relocalization.yaml: ros.localization_health_topic` | `/localization/ok` | std_msgs/Bool（代码固定） | 接收；必须为新鲜真值；按需定位 |
| `task_control.yaml: ros.command_topic` | `/epgeneral_task_control/execution_command` | epgeneral_task_control/TaskExecutionCommand（代码固定） | 协调器→适配器 |
| `task_control.yaml: ros.feedback_topic` | `/epgeneral_task_control/execution_feedback` | epgeneral_task_control/TaskExecutionFeedback（代码固定） | 适配器→协调器 |
| `task_control.yaml: ros.status_topic` | `/qrd/QRD_003/task_status` | std_msgs/String（代码固定） | 协调器发布，锁存摘要 |
| `task_control.yaml: adapter.navigation_action` | `/move_base` | move_base_msgs/MoveBaseAction（代码固定） | action 客户端→导航服务器 |
| `task_control.yaml: adapter.odom_topic` | `/odom_nav` | nav_msgs/Odometry（代码固定） | 接收 pose.pose.position/orientation |
| `task_control.yaml: adapter.zero_velocity_topic` | `/cmd_vel_nav` | geometry_msgs/Twist（代码固定） | 发布零速度，配置中的停车接口 |
| `task_control.yaml: adapter.localization_ok_topic` | `/localization/ok` | std_msgs/Bool（代码固定） | 接收 data，新鲜且为 true |
| `task_control.yaml: adapter.control_enabled_topic` | `/go2/control/enabled` | std_msgs/Bool（代码固定） | 接收 data；锁存控制状态 |
| `task_control.yaml: adapter.control_diagnostics_topic` | `/go2/diagnostics` | diagnostic_msgs/DiagnosticArray（代码固定） | 接收新鲜诊断；GO2 SDK bridge / motion_enabled |
| `task_control.yaml: adapter.navigation_reset_service` | `/go2_navigation_supervisor/reset` | std_srvs/Trigger（代码固定） | 调用，success 必须 true；不是 Empty |
| `task_control.yaml: adapter.control_enable_service` | `/go2_sdk_bridge_real/enable` | std_srvs/SetBool（代码固定） | 调用 data=true/false；再确认真实状态 |

建图坐标：map=`lio_odom`，preview=`odom`，body=`body_lio`，sensor=`body_lio`；最终 artifacts.frame=`odom`。外参取本机标定，不能复制本表所属设备的标定用于其他设备。

<a id="documents-config-topic-reference-md-agv_001--ground_air_agv"></a>
### AGV_001 / ground_air_agv

[配置原件](../devices/ground_air_agv/profiles/ground_air_agv/config) · [部署记录](devices/ground_air_agv/DEPLOYMENT_RECORD.md#deploy-records-agv-001-deployment-md)

| 文件与完整键 | 当前接口名 | ROS 类型 / 接口类别 | 方向、字段与生效条件 |
| --- | --- | --- | --- |
| `epgeneral_mqtav.yaml: ros.state.topic` | `/mavros/state` | mavros_msgs/State（message_type） | 接收；字段 {"connected": "connected", "armed": "armed", "system_status": "system_status", "mode": "mode"} |
| `epgeneral_mqtav.yaml: ros.battery.topic` | `/mavros/battery` | sensor_msgs/BatteryState（message_type） | 接收；字段 {"percentage": "percentage", "voltage": "voltage", "current": "current"} |
| `udp_telemetry.yaml: descriptors[global_pose].source.topic` | `/mavros/local_position/pose` | geometry_msgs/PoseStamped | ros_fields；字段 {'position': 'pose.position', 'orientation': 'pose.orientation'}；hold |
| `udp_telemetry.yaml: descriptors[vision_pose].source.topic` | `/Odometry` | nav_msgs/Odometry | ros_fields；字段 {'position': 'pose.pose.position', 'orientation': 'pose.pose.orientation'}；hold |
| `udp_telemetry.yaml: descriptors[imu].source.topic` | `/mavros/imu/data` | sensor_msgs/Imu | ros_fields；字段 {'orientation': 'orientation', 'angular_velocity': 'angular_velocity', 'linear_acceleration': 'linear_acceleration'}；hold |
| `udp_telemetry.yaml: descriptors[livox_pointcloud].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 1.0s |
| `udp_telemetry.yaml: descriptors[livox_driver].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[fastlio2].source.topic` | `/Odometry` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[pgm_mapping].source.topic` | `/ground_air/mapping/status` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[octomap_mapping].source.topic` | `/octomap_binary` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[occupancy_grid_mapping].source.topic` | `/map` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[mapping_mode].source.topic` | `/mapping_mode` | std_msgs/String | ros_fields；字段 {'value': 'data'}；hold |
| `udp_telemetry.yaml: runtime.link_status_topic` | `/agv/{device_id}/link/udp_tx` | std_msgs/Bool | 输出；支持 {device_id} |
| `udp_telemetry.yaml: runtime.diagnostics_topic` | `/agv/{device_id}/diagnostics` | diagnostic_msgs/DiagnosticArray | 输出；支持 {device_id} |
| `video.yaml: image_topic` | `/a8_cam/image_raw` | sensor_msgs/Image（image_message_type） | 接收；输出 1280×720@30；外部相机先就绪 |
| `video.yaml: runtime.status_topic` | `~status` | std_msgs/String JSON |
| `video.yaml: capture.args.image_topic` | `/a8_cam/image_raw` | sensor_msgs/Image |
| `map_stream.yaml: ros.inputs.lidar.topic` | `/livox/lidar` | livox_ros_driver2/CustomMsg（message_type） | 接收；prepare 原始探测；frame=base_link |
| `map_stream.yaml: ros.inputs.imu.topic` | `/livox/imu` | sensor_msgs/Imu（message_type） | 接收；prepare 原始探测；frame=base_link |
| `map_stream.yaml: ros.stream.cloud.topic` | `/cloud_registered` | sensor_msgs/PointCloud2（message_type） | 接收；建图运行时预览；frame=camera_init；coordinates=map |
| `map_stream.yaml: ros.stream.pose.topic` | `/Odometry` | nav_msgs/Odometry（message_type） | 接收；建图运行时预览；字段 pose.pose.position/pose.pose.orientation |
| `map_stream.yaml: integrations.map_accumulator.service` | `/ground_air/mapping/save` | 外部 ROS 服务；现场核验 .srv | go2_accumulator 实际调用；其他 backend 为兼容占位，不据此要求启动 Go2 |
| `relocalization.yaml: ros.initial_pose_topic` | `/initialpose` | geometry_msgs/PoseWithCovarianceStamped（代码固定） | 发布初始位姿，定位器订阅；按需定位 |
| `relocalization.yaml: ros.map_topic` | `/map` | nav_msgs/OccupancyGrid（外部地图约定） | 地图话题就绪检查，内容另验；按需定位 |
| `task_control.yaml: ros.command_topic` | `/epgeneral_task_control/execution_command` | epgeneral_task_control/TaskExecutionCommand（代码固定） | 协调器→适配器 |
| `task_control.yaml: ros.feedback_topic` | `/epgeneral_task_control/execution_feedback` | epgeneral_task_control/TaskExecutionFeedback（代码固定） | 适配器→协调器 |
| `task_control.yaml: ros.status_topic` | `/epgeneral_task_control/task_status` | std_msgs/String（代码固定） | 协调器发布，锁存摘要 |
| `task_control.yaml: adapter.localization_param` | `/ground_air/localized` | ROS 参数 bool（代码固定） | 读取参数，不是话题 |
| `task_control.yaml: adapter.vehicle_status_topic` | `/ground_air/vehicle_status` | ground_air_msgs/VehicleStatus（代码固定） | 接收底盘真实状态 |
| `task_control.yaml: adapter.mission_status_topic` | `/ground_air/mission/status` | ground_air_msgs/MissionStatus（代码固定） | 接收任务状态/反馈 |
| `task_control.yaml: adapter.prepare_ground_service` | `/ground_air/prepare_ground` | std_srvs/Trigger（代码固定） | 调用并检查结果 |
| `task_control.yaml: adapter.mission_submit_service` | `/ground_air/mission/submit` | ground_air_msgs/SubmitMission（代码固定） | 调用并检查结果 |
| `task_control.yaml: adapter.mission_start_service` | `/ground_air/mission/start` | std_srvs/Trigger（代码固定） | 调用并检查结果 |
| `task_control.yaml: adapter.mission_cancel_service` | `/ground_air/mission/cancel` | std_srvs/Trigger（代码固定） | 调用并检查结果 |
| `task_control.yaml: adapter.emergency_stop_service` | `/ground_air/emergency_stop` | ground_air_msgs/SetEmergencyStop（代码固定） | 调用；保留持久锁存 |

建图坐标：map=`camera_init`，preview=`odom`，body=`body`，sensor=`body`；最终 artifacts.frame=`map`。外参取本机标定，不能复制本表所属设备的标定用于其他设备。

<a id="documents-config-topic-reference-md-ugv_001--scout_mini"></a>
### UGV_001 / scout_mini

[配置原件](../devices/scout_mini/profiles/scout_mini/config) · [部署记录](devices/scout_mini/DEPLOYMENT_RECORD.md#deploy-records-ugv-001-deployment-md)

| 文件与完整键 | 当前接口名 | ROS 类型 / 接口类别 | 方向、字段与生效条件 |
| --- | --- | --- | --- |
| `epgeneral_mqtav.yaml: ros.state.topic` | `/scout_status` | scout_msgs/ScoutStatus（message_type） | 接收；字段 {"connected": null, "armed": null, "system_status": "fault_code", "mode": "control_mode"} |
| `epgeneral_mqtav.yaml: ros.battery.topic` | `/BMS_status` | scout_msgs/ScoutBmsStatus（message_type） | 接收；字段 {"percentage": null, "voltage": "battery_voltage", "current": null} |
| `udp_telemetry.yaml: descriptors[vision_pose].source.topic` | `/scout/odom` | nav_msgs/Odometry | ros_fields；字段 {'position': 'pose.pose.position', 'orientation': 'pose.pose.orientation'}；hold |
| `udp_telemetry.yaml: descriptors[imu].source.topic` | `/livox/imu` | sensor_msgs/Imu | ros_fields；字段 {'orientation': 'orientation', 'angular_velocity': 'angular_velocity', 'linear_acceleration': 'linear_acceleration'}；hold |
| `udp_telemetry.yaml: descriptors[livox_pointcloud].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 1.0s |
| `udp_telemetry.yaml: descriptors[livox_driver].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[fastlio2].source.topic` | `/Odometry` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[pgm_mapping].source.topic` | `/ccs/relocalization/pgm_file` | 无 ROS 类型 | file_status；不订阅；state_file=/home/nvidia/.ros/ccs_edge_dev/state/relocalization.json；map_root=/home/nvidia/livox_fastlio/maps/ccs_download；path_template={map_id}/map.pgm |
| `udp_telemetry.yaml: runtime.link_status_topic` | `/ugv/{device_id}/link/udp_tx` | std_msgs/Bool | 输出；支持 {device_id} |
| `udp_telemetry.yaml: runtime.diagnostics_topic` | `/ugv/{device_id}/diagnostics` | diagnostic_msgs/DiagnosticArray | 输出；支持 {device_id} |
| `video.yaml: image_topic` | `/camera/color/image_raw` | sensor_msgs/Image（image_message_type） | 接收；输出 640×480@30；外部相机先就绪 |
| `video.yaml: runtime.status_topic` | `~status` | std_msgs/String JSON |
| `map_stream.yaml: ros.inputs.lidar.topic` | `/livox/lidar` | livox_ros_driver2/CustomMsg（message_type） | 接收；prepare 原始探测；frame=livox_frame |
| `map_stream.yaml: ros.inputs.imu.topic` | `/livox/imu` | sensor_msgs/Imu（message_type） | 接收；prepare 原始探测；frame=livox_frame |
| `map_stream.yaml: ros.stream.cloud.topic` | `/cloud_registered_body` | sensor_msgs/PointCloud2（message_type） | 接收；建图运行时预览；frame=body；coordinates=sensor |
| `map_stream.yaml: ros.stream.pose.topic` | `/fastlio_odom` | nav_msgs/Odometry（message_type） | 接收；建图运行时预览；字段 pose.pose.position/pose.pose.orientation |
| `map_stream.yaml: integrations.map_accumulator.service` | `/unused_scout_map_service` | 外部 ROS 服务；现场核验 .srv | go2_accumulator 实际调用；其他 backend 为兼容占位，不据此要求启动 Go2 |
| `relocalization.yaml: ros.initial_pose_topic` | `/initialpose` | geometry_msgs/PoseWithCovarianceStamped（代码固定） | 发布初始位姿，定位器订阅；按需定位 |
| `relocalization.yaml: ros.map_topic` | `/map_2d` | nav_msgs/OccupancyGrid（外部地图约定） | 地图话题就绪检查，内容另验；按需定位 |
| `task_control.yaml: ros.command_topic` | `/epgeneral_task_control/execution_command` | epgeneral_task_control/TaskExecutionCommand（代码固定） | 协调器→适配器 |
| `task_control.yaml: ros.feedback_topic` | `/epgeneral_task_control/execution_feedback` | epgeneral_task_control/TaskExecutionFeedback（代码固定） | 适配器→协调器 |
| `task_control.yaml: ros.status_topic` | `/epgeneral_task_control/task_status` | std_msgs/String（代码固定） | 协调器发布，锁存摘要 |
| `task_control.yaml: adapter.navigation_action` | `/move_base` | move_base_msgs/MoveBaseAction（代码固定） | action 客户端→导航服务器 |
| `task_control.yaml: adapter.odom_topic` | `/fastlio_odom` | nav_msgs/Odometry（代码固定） | 接收 pose.pose.position/orientation |
| `task_control.yaml: adapter.zero_velocity_topic` | `/cmd_vel` | geometry_msgs/Twist（代码固定） | 发布零速度，配置中的停车接口 |

建图坐标：map=`odom`，preview=`odom`，body=`base_link`，sensor=`body`；最终 artifacts.frame=`map`。外参取本机标定，不能复制本表所属设备的标定用于其他设备。

<a id="documents-config-topic-reference-md-ugv_003--wheeltec_r550p"></a>
### UGV_003 / wheeltec_r550p

[配置原件](../devices/wheeltec_r550p/profiles/wheeltec_r550p/config) · [部署记录](devices/wheeltec_r550p/DEPLOYMENT_RECORD.md#deploy-records-ugv-003-deployment-md)

| 文件与完整键 | 当前接口名 | ROS 类型 / 接口类别 | 方向、字段与生效条件 |
| --- | --- | --- | --- |
| `epgeneral_mqtav.yaml: ros.state.topic` | `/odom` | nav_msgs/Odometry（message_type） | 接收；字段 {"connected": null, "armed": null, "system_status": null, "mode": null} |
| `epgeneral_mqtav.yaml: ros.battery.topic` | `/PowerVoltage` | std_msgs/Float32（message_type） | 接收；字段 {"percentage": null, "voltage": "data", "current": null} |
| `udp_telemetry.yaml: descriptors[vision_pose].source.topic` | `/fastlio_odom` | nav_msgs/Odometry | ros_fields；字段 {'position': 'pose.pose.position', 'orientation': 'pose.pose.orientation'}；hold |
| `udp_telemetry.yaml: descriptors[imu].source.topic` | `/livox/imu` | sensor_msgs/Imu | ros_fields；字段 {'orientation': 'orientation', 'angular_velocity': 'angular_velocity', 'linear_acceleration': 'linear_acceleration'}；hold |
| `udp_telemetry.yaml: descriptors[livox_pointcloud].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 1.0s |
| `udp_telemetry.yaml: descriptors[livox_driver].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[fastlio2].source.topic` | `/Odometry` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[pgm_mapping].source.topic` | `/ccs/relocalization/pgm_file` | 无 ROS 类型 | file_status；不订阅；state_file=/home/nrc19/.ros/ccs_edge_dev_wheeltec_r550p/state/relocalization.json；map_root=/home/nrc19/livox_fastlio/maps/ccs_download；path_template={map_id}/map.pgm |
| `udp_telemetry.yaml: runtime.link_status_topic` | `/ugv/{device_id}/link/udp_tx` | std_msgs/Bool | 输出；支持 {device_id} |
| `udp_telemetry.yaml: runtime.diagnostics_topic` | `/ugv/{device_id}/diagnostics` | diagnostic_msgs/DiagnosticArray | 输出；支持 {device_id} |
| `video.yaml: image_topic` | `/camera/color/image_raw` | sensor_msgs/Image（image_message_type） | Gemini 336L 彩色输入；输出 640×360@30、2500 kbps；根脚本默认启动，可用 CCS_ENABLE_VIDEO=0 关闭 |
| `video.yaml: runtime.status_topic` | `~status` | std_msgs/String JSON |
| `map_stream.yaml: ros.inputs.lidar.topic` | `/livox/lidar` | livox_ros_driver2/CustomMsg（message_type） | 接收；prepare 原始探测；frame=livox_frame |
| `map_stream.yaml: ros.inputs.imu.topic` | `/livox/imu` | sensor_msgs/Imu（message_type） | 接收；prepare 原始探测；frame=livox_frame |
| `map_stream.yaml: ros.stream.cloud.topic` | `/cloud_registered_body` | sensor_msgs/PointCloud2（message_type） | 接收；建图运行时预览；frame=body；coordinates=sensor |
| `map_stream.yaml: ros.stream.pose.topic` | `/fastlio_odom` | nav_msgs/Odometry（message_type） | 接收；建图运行时预览；字段 pose.pose.position/pose.pose.orientation |
| `map_stream.yaml: integrations.map_accumulator.service` | `/unused_wheeltec_map_service` | 外部 ROS 服务；现场核验 .srv | go2_accumulator 实际调用；其他 backend 为兼容占位，不据此要求启动 Go2 |
| `relocalization.yaml: ros.initial_pose_topic` | `/initialpose` | geometry_msgs/PoseWithCovarianceStamped（代码固定） | 发布初始位姿，定位器订阅；按需定位 |
| `relocalization.yaml: ros.map_topic` | `/map_2d` | nav_msgs/OccupancyGrid（外部地图约定） | 地图话题就绪检查，内容另验；按需定位 |
| `task_control.yaml: ros.command_topic` | `/epgeneral_task_control/execution_command` | epgeneral_task_control/TaskExecutionCommand（代码固定） | 协调器→适配器 |
| `task_control.yaml: ros.feedback_topic` | `/epgeneral_task_control/execution_feedback` | epgeneral_task_control/TaskExecutionFeedback（代码固定） | 适配器→协调器 |
| `task_control.yaml: ros.status_topic` | `/epgeneral_task_control/task_status` | std_msgs/String（代码固定） | 协调器发布，锁存摘要 |
| `task_control.yaml: adapter.navigation_action` | `/move_base` | move_base_msgs/MoveBaseAction（代码固定） | action 客户端→导航服务器 |
| `task_control.yaml: adapter.odom_topic` | `/fastlio_odom` | nav_msgs/Odometry（代码固定） | 适配器接收定位 pose.pose.position/orientation，用于进度、反馈和位姿新鲜度 |
| `task_control.yaml: adapter.navigation_odom_topic` | `/odom` | nav_msgs/Odometry（launch 参数） | 只传给 move_base/TEB 读取轮式底盘速度；不替代适配器定位位姿 |
| `task_control.yaml: adapter.zero_velocity_topic` | `/wheeltec_driver/cmd_vel` | geometry_msgs/Twist（代码固定） | UGV_003 停车速度输出；导航速度由安全门控制 |
| `task_control.yaml: adapter.navigation_cmd_vel_topic` | `/wheeltec_driver/cmd_vel` | geometry_msgs/Twist（代码固定） | UGV_003 原生导航速度输出 |
| `task_control.yaml: adapter.localization_ok_topic` | `/wheeltec_control/localization_ok` | std_msgs/Bool（代码固定） | 活动地图与实时 `/fastlio_odom` 均有效时为 true |
| `task_control.yaml: adapter.control_enabled_topic` | `/wheeltec_control/enabled` | std_msgs/Bool（代码固定） | 协调器确认驱动与安全门后的控制状态 |
| `task_control.yaml: adapter.control_enable_service` | `/wheeltec_control/enable` | std_srvs/SetBool（代码固定） | 取得/归还自主控制权并确认真实状态 |
| `task_control.yaml: adapter.control_stop_service` | `/wheeltec_control/stop` | std_srvs/Trigger（代码固定） | 故障或急停时锁定停车 |
| `task_control.yaml: adapter.navigation_reset_service` | `/wheeltec_control/reset` | std_srvs/Trigger（代码固定） | 人工确认故障处理后复位控制链 |
| `task_control.yaml: adapter.control_enabled_topic` | `/wheeltec_control/enabled` | std_msgs/Bool（代码固定） | 控制权协调器真实启用状态 |
| `task_control.yaml: adapter.control_heartbeat_topic` | `/wheeltec_driver/control_heartbeat` | std_msgs/Empty（代码固定） | 自主状态 10 Hz 租约；0.5 秒过期锁定停车 |
| `task_control.yaml: adapter.control_authority.odom_topic` | `/fastlio_odom` | nav_msgs/Odometry | 控制权协调器的实时定位新鲜度输入 |
| `task_control.yaml: adapter.control_authority.driver_odom_topic` | `/odom` | nav_msgs/Odometry | 底盘驱动速度里程计 |
| `task_control.yaml: adapter.control_authority.localization_ok_topic` | `/wheeltec_control/localization_ok` | std_msgs/Bool | 控制权协调器定位状态输出 |
| `task_control.yaml: adapter.control_authority.enabled_topic` | `/wheeltec_control/enabled` | std_msgs/Bool | 控制权协调器自主状态输出 |
| `task_control.yaml: adapter.control_authority.driver_enabled_topic` | `/wheeltec_robot/control_enabled` | std_msgs/Bool | 驱动自主状态输入 |
| `task_control.yaml: adapter.control_authority.driver_enable_service` | `/wheeltec_robot/set_autonomous` | std_srvs/SetBool | 驱动自主/手动控制权切换 |
| `task_control.yaml: adapter.control_authority.driver_stop_service` | `/wheeltec_robot/stop` | std_srvs/Trigger | 驱动故障锁停 |
| `task_control.yaml: adapter.control_authority.driver_reset_service` | `/wheeltec_robot/reset_authority` | std_srvs/Trigger | 人工复位后返回手动控制权 |
| `task_control.yaml: adapter.control_authority.safety_arm_service` | `/wheeltec_safety/arm` | std_srvs/Trigger | 打开速度安全门 |
| `task_control.yaml: adapter.control_authority.safety_stop_service` | `/wheeltec_safety/stop` | std_srvs/Trigger | 关闭速度安全门并停车 |
| `task_control.yaml: adapter.control_authority.safety_reset_service` | `/wheeltec_safety/reset` | std_srvs/Trigger | 复位速度安全门状态 |
| `task_control.yaml: adapter.clear_costmaps_service` | `/move_base/clear_costmaps` | std_srvs/Empty | 自主接管前、控制仍停用时清理旧代价地图 |
| `task_control.yaml: adapter.clear_costmaps_settle_seconds` | `0.30` | 秒 | 清理后重新校验定位和手动状态的稳定期 |

UGV_003 专用导航 launch 固定 `TebLocalPlannerROS/max_vel_x=0.20`、`max_vel_theta=0.40`、`max_vel_x_backwards=0.10` 和前进权重 1000。安全门 0.1.2 使用完整周期串行快照，配置 `costmap_lethal_threshold=100`、`linear_deadband=0.02` 和 `allow_reverse=false`；已知致命单元只有与当前实测车体相交时才作为自体残留排除，未知单元仍阻断，微小负向求解漂移归零，明确倒车仍闭锁。`/fastlio_odom` 与 `/odom` 必须同时有新鲜数据，前者回答“机器人在地图哪里”，后者回答“轮式底盘当前速度是多少”。

建图坐标：map=`odom`，preview=`odom`，body=`base_link`，sensor=`body`；最终 artifacts.frame=`map`。外参取本机标定，不能复制本表所属设备的标定用于其他设备。

<a id="documents-config-topic-reference-md-ugv_004--wheeltec_r550p_02"></a>
### UGV_004 / wheeltec_r550p_02

[配置原件](../devices/wheeltec_r550p/profiles/wheeltec_r550p_02/config) · [部署记录](devices/wheeltec_r550p/DEPLOYMENT_RECORD.md#deploy-records-ugv-004-deployment-md)

| 文件与完整键 | 当前接口名 | ROS 类型 / 接口类别 | 方向、字段与生效条件 |
| --- | --- | --- | --- |
| `epgeneral_mqtav.yaml: ros.state.topic` | `/odom` | nav_msgs/Odometry（message_type） | 接收；字段 {"connected": null, "armed": null, "system_status": null, "mode": null} |
| `epgeneral_mqtav.yaml: ros.battery.topic` | `/PowerVoltage` | std_msgs/Float32（message_type） | 接收；字段 {"percentage": null, "voltage": "data", "current": null} |
| `udp_telemetry.yaml: descriptors[vision_pose].source.topic` | `/fastlio_odom` | nav_msgs/Odometry | ros_fields；字段 {'position': 'pose.pose.position', 'orientation': 'pose.pose.orientation'}；hold |
| `udp_telemetry.yaml: descriptors[imu].source.topic` | `/livox/imu` | sensor_msgs/Imu | ros_fields；字段 {'orientation': 'orientation', 'angular_velocity': 'angular_velocity', 'linear_acceleration': 'linear_acceleration'}；hold |
| `udp_telemetry.yaml: descriptors[livox_pointcloud].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 1.0s |
| `udp_telemetry.yaml: descriptors[livox_driver].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[fastlio2].source.topic` | `/Odometry` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[pgm_mapping].source.topic` | `/ccs/relocalization/pgm_file` | 无 ROS 类型 | file_status；不订阅；state_file=/home/nrc15/ccs_edge_ws/run/state/relocalization.json；map_root=/home/nrc15/ccs_edge_ws/maps/download；path_template={map_id}/map.pgm |
| `udp_telemetry.yaml: runtime.link_status_topic` | `/ugv/{device_id}/link/udp_tx` | std_msgs/Bool | 输出；支持 {device_id} |
| `udp_telemetry.yaml: runtime.diagnostics_topic` | `/ugv/{device_id}/diagnostics` | diagnostic_msgs/DiagnosticArray | 输出；支持 {device_id} |
| `video.yaml: image_topic` | `/camera/color/image_raw` | sensor_msgs/Image（image_message_type） | 接收；输出 640×480@30；视频按需启动 |
| `video.yaml: runtime.status_topic` | `~status` | std_msgs/String JSON |
| `map_stream.yaml: ros.inputs.lidar.topic` | `/livox/lidar` | livox_ros_driver2/CustomMsg（message_type） | 接收；prepare 原始探测；frame=livox_frame |
| `map_stream.yaml: ros.inputs.imu.topic` | `/livox/imu` | sensor_msgs/Imu（message_type） | 接收；prepare 原始探测；frame=livox_frame |
| `map_stream.yaml: ros.stream.cloud.topic` | `/cloud_registered_body` | sensor_msgs/PointCloud2（message_type） | 接收；建图运行时预览；frame=body；coordinates=sensor |
| `map_stream.yaml: ros.stream.pose.topic` | `/fastlio_odom` | nav_msgs/Odometry（message_type） | 接收；建图运行时预览；字段 pose.pose.position/pose.pose.orientation |
| `map_stream.yaml: integrations.map_accumulator.service` | `/unused_wheeltec_map_service` | 外部 ROS 服务；现场核验 .srv | go2_accumulator 实际调用；其他 backend 为兼容占位，不据此要求启动 Go2 |
| `relocalization.yaml: ros.initial_pose_topic` | `/initialpose` | geometry_msgs/PoseWithCovarianceStamped（代码固定） | 发布初始位姿，定位器订阅；按需定位 |
| `relocalization.yaml: ros.map_topic` | `/map_2d` | nav_msgs/OccupancyGrid（外部地图约定） | 地图话题就绪检查，内容另验；按需定位 |
| `relocalization.yaml: ros.localization_health_topic` | `/ccs/localization_valid` | std_msgs/Bool | UGV_004 定位健康状态 |
| `task_control.yaml: ros.command_topic` | `/epgeneral_task_control/execution_command` | epgeneral_task_control/TaskExecutionCommand（代码固定） | 协调器→适配器 |
| `task_control.yaml: ros.feedback_topic` | `/epgeneral_task_control/execution_feedback` | epgeneral_task_control/TaskExecutionFeedback（代码固定） | 适配器→协调器 |
| `task_control.yaml: ros.status_topic` | `/epgeneral_task_control/task_status` | std_msgs/String（代码固定） | 协调器发布，锁存摘要 |
| `task_control.yaml: adapter.navigation_action` | `/move_base` | move_base_msgs/MoveBaseAction（代码固定） | action 客户端→导航服务器 |
| `task_control.yaml: adapter.odom_topic` | `/fastlio_odom` | nav_msgs/Odometry（代码固定） | 接收 pose.pose.position/orientation |
| `task_control.yaml: adapter.zero_velocity_topic` | `/cmd_vel` | geometry_msgs/Twist（代码固定） | 发布零速度，配置中的停车接口 |
| `task_control.yaml: adapter.localization_health_topic` | `/ccs/localization_valid` | std_msgs/Bool | 导航准备时检查定位健康 |

建图坐标：map=`odom`，preview=`odom`，body=`base_link`，sensor=`body`；最终 artifacts.frame=`map`。外参取本机标定，不能复制本表所属设备的标定用于其他设备。

本设备为 V5.1：内部 launch 使用 `.launch.xml`，任务导航使用 CCS 二维兼容入口。外参 `base_link <- body` 取本机测量正向矩阵，平移(0.10,0,0.15)m、pitch=+20度；不能套用 UGV_003 的旧逆矩阵。

<a id="documents-config-topic-reference-md-配置外的固定接口与验收"></a>
## 配置外的固定接口与验收

| 适用 | 接口 | 类型 | 用途 |
| --- | --- | --- | --- |
| 原生 Go2 | /epgeneral_navigation_task_adapter/reset_emergency_stop | std_srvs/Trigger | 人工清锁，不使能；无执行/准备/控制过渡且有新鲜 disabled 证据才允许 |
| UGV_003 | /epgeneral_navigation_task_adapter/reset_emergency_stop | std_srvs/Trigger | 两个控制状态均为 false 且无执行/准备/控制过渡时人工清锁；同时复位 Wheeltec 控制链但不使能 |
| Ground-Air | /ground_air/localization/pose | geometry_msgs/PoseStamped | 任务适配器默认读取，可选 adapter.local_pose_topic 覆盖 |
| Ground-Air | /ground_air/system/stage | std_msgs/UInt8，锁存 | 0基础/1建图/2定位，状态不是服务 |
| Ground-Air | /ground_air/system/stage_detail | std_msgs/String，锁存 | 阶段诊断 |
| Ground-Air | /ground_air/system/set_stage | ground_air_msgs/SetSystemStage | caller/map_id 归属和 guard 契约 |
| Ground-Air | /ground_air/load_map | ground_air_msgs/LoadMap | 定位地图加载 |
| Ground-Air | /ground_air/relocalize | ground_air_msgs/Relocalize | initialpose 适配，use_initial_guess=true |

以下命令以已 source 同一 master 的 GO2_3 为例。只读查询不启动节点；带超时避免按需节点未运行时一直等待。类型/类可在离线核验，数据只能在已授权阶段采样。

~~~bash
rostopic type /go2/state/low_state
rosmsg show go2_control/Go2LowState
timeout 5 rostopic echo -n 1 /go2/control/enabled
timeout 5 rostopic echo -n 1 /go2/diagnostics
rostopic type /camera/color/image_raw
timeout 10 rostopic hz -w 30 /camera/color/image_raw
rosservice type /go2_sdk_bridge_real/enable
rossrv show std_srvs/SetBool
rossrv md5 std_srvs/Trigger
~~~

验收记录至少包含：profile 与配置键、实际 topic/service、类型/MD5、消息字段、frame、频率/新鲜度、发布者、检查时的生命周期阶段、命令及结论。相机 GO2_3 独立 readiness 还要求两帧递增且年龄≤3秒；只看到节点或一次 echo 不足以判 ready。SRT 参数为 UDP9000、120ms、2500kbps，帧率15；USB2.1/Right MIPI 历史告警不自动算已修复。

急停复位步骤见[使用手册的 UGV_003 步骤](USER_MANUAL.md#documents-user-manual-md-ugv_003-%E6%8C%AF%E8%8D%A1%E4%B8%8E%E4%BA%BA%E5%B7%A5%E6%80%A5%E5%81%9C%E5%A4%8D%E4%BD%8D)和[Go2 步骤](USER_MANUAL.md#documents-user-manual-md-go2-%E4%BA%BA%E5%B7%A5%E6%80%A5%E5%81%9C%E5%A4%8D%E4%BD%8D)。禁止通过接口联调命令意外使能、发布非零速度、运动目标或清除安全文件。

### UAV / uav_001

| 新增视频接口 | 话题 | 类型 |
| --- | --- | --- |
| `video.yaml: runtime.status_topic` | `~status` | std_msgs/String JSON |

| 配置字段 | 话题或服务 | 类型 |
| --- | --- | --- |
| `epgeneral_mqtav.yaml: ros.state.topic` | `/mavros/state` | mavros_msgs/State |
| `epgeneral_mqtav.yaml: ros.battery.topic` | `/mavros/battery` | sensor_msgs/BatteryState |
| `epgeneral_mqtav.yaml: ros.mission.topic` | `/uav/{device_id}/task_status` | std_msgs/String；展开为 /uav/UAV_001/task_status |
| `map_stream.yaml: ros.inputs.lidar.topic` | `/livox/lidar` | livox_ros_driver2/CustomMsg |
| `map_stream.yaml: ros.inputs.imu.topic` | `/livox/imu` | sensor_msgs/Imu |
| `map_stream.yaml: ros.stream.cloud.topic` | `/ducted/mapping/cloud_registered` | sensor_msgs/PointCloud2 |
| `map_stream.yaml: ros.stream.pose.topic` | `/ducted/localization/odom` | nav_msgs/Odometry |
| `map_stream.yaml: integrations.map_accumulator.service` | `/ducted/mapping/save_map` | — |
| `relocalization.yaml: ros.initial_pose_topic` | `/ducted/relocalization/initialpose` | — |
| `relocalization.yaml: ros.map_topic` | `/ducted/relocalization/global_map` | — |
| `relocalization.yaml: ros.localization_health_topic` | `/ducted/localization/map_ready` | — |
| `task_control.yaml: ros.command_topic` | `/uav/UAV_001/execution_command` | — |
| `task_control.yaml: ros.feedback_topic` | `/uav/UAV_001/execution_feedback` | — |
| `task_control.yaml: ros.status_topic` | `/uav/UAV_001/task_status` | — |
| `udp_telemetry.yaml: descriptors[global_pose].source.topic` | `/mavros/local_position/pose` | geometry_msgs/PoseStamped | ros_fields；字段 {'position': 'pose.position', 'orientation': 'pose.orientation'}；hold |
| `udp_telemetry.yaml: descriptors[vision_pose].source.topic` | `/ducted/localization/body_odom` | nav_msgs/Odometry | ros_fields；字段 {'position': 'pose.pose.position', 'orientation': 'pose.pose.orientation'}；hold |
| `udp_telemetry.yaml: descriptors[imu].source.topic` | `/mavros/imu/data` | sensor_msgs/Imu | ros_fields；字段 {'orientation': 'orientation', 'angular_velocity': 'angular_velocity', 'linear_acceleration': 'linear_acceleration'}；hold |
| `udp_telemetry.yaml: descriptors[livox_pointcloud].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 1.0s |
| `udp_telemetry.yaml: descriptors[livox_driver].source.topic` | `/livox/lidar` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[fastlio2].source.topic` | `/ducted/localization/odom` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[pgm_mapping].source.topic` | `/map_pgm` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[octomap_mapping].source.topic` | `/octomap_binary` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[occupancy_grid_mapping].source.topic` | `/map` | AnyMsg | topic_freshness；仅到达时间，超时 3.0s |
| `udp_telemetry.yaml: descriptors[mapping_mode].source.topic` | `/uav/{device_id}/stage_status` | std_msgs/String | ros_fields；字段 {'value': 'data'}；hold |
| `udp_telemetry.yaml: runtime.link_status_topic` | `/epgeneral_udp_telemetry/link/udp_tx` | std_msgs/Bool | 输出；支持 {device_id} |
| `udp_telemetry.yaml: runtime.diagnostics_topic` | `/epgeneral_udp_telemetry/diagnostics` | diagnostic_msgs/DiagnosticArray | 输出；支持 {device_id} |

视频 runtime.decoder_preload 仅 UAV ARM64 配置 libgomp，launch 保留兼容覆盖参数。/ctrl_cmd/state 是整数 ROS 参数。完整边界见 [UAV 指南](devices/uav/DEPLOYMENT_GUIDE.md)。

## 可选可信区域（重定位包 0.5.0）

[可信区域](INTERFACE_REFERENCE.md#可选可信区域接收) 说明接收开关、文件路径、XML 格式及协议。缺少区域文件不会改变原重定位流程。

## 可选可信区域接收

配套 CCS 0.26.0，`epgeneral_relocalization` 0.5.0，`epgeneral_device_config` 0.1.2。

### 配置与文件

在实际启动使用的 relocalization.yaml 中可增加：

```yaml
trusted_regions:
  enabled: true
  root: ~/.ros/ccs_edge_dev/trusted_regions
```

旧配置缺少此节时使用以上默认值；可设置 `enabled: false` 关闭接收。共享模板位于 `EPGeneral_device_config/config/relocalization.yaml`，使用设备 profile 的一键启动脚本时请修改对应 profile，重启重定位节点生效。

已接收文件为 `<root>/<map_id>/<device_id>.xml`，默认与地图 ZIP 安装目录分离。整组下发成功后原子替换旧文件；下载、校验或写盘失败保留旧文件，返回错误。空区域集合表示清空该设备该地图的区域。地面站删除区域不会立即修改此文件，须重新保存并下发。

可信区域文件不是重定位的必要输入；缺省、损坏或接收关闭不影响原有启动、初始位姿、TF 判定和状态上报。文件仅存储，不用于改变本版本定位或导航算法。

### 接口

继续使用 `ccs-relocalization-v1`。协商响应 `negotiation_status` 增加 `trusted_regions_v1` 布尔能力标识，旧地面站可忽略。

`trusted_regions_offer` 使用现有信封的 map_id、device_id、session_id、request_id，payload 为 `url`、`expires_at`、`byte_count`、`sha256`、`revision`。仅接收已配置地面站 IP、当前设备、当前地图和已成功定位会话的请求。

节点从现有地面站 HTTP 服务下载 XML，禁止重定向，检查下载大小、SHA-256、XML 身份、坐标系和 revision。异步工作线程在提交前再次检查会话和操作代际，拒绝迟到覆盖。`trusted_regions_status` 返回 `request_id`、`revision`、`sha256`、`state`、`reason`；state 为 `downloading`、`ready` 或 `error`，只有原子保存完成后返回 `ready`。区域失败不改变定位状态。重复请求复用结果。

### XML v1

```xml
<?xml version='1.0' encoding='utf-8'?>
<trusted_regions schema_version="1" map_id="map-1" device_id="UGV_001" frame_id="map" revision="revision-id">
  <region id="1">
    <point index="1" x="0.0" y="0.0" />
    <point index="2" x="4.0" y="0.0" />
    <point index="3" x="2.0" y="3.0" />
  </region>
</trusted_regions>
```

坐标单位为米，属于配置的 map_frame。每区至少三个不同且不共线的有序顶点，首尾隐式闭合，支持凹多边形，拒绝自交、重复点和重叠边。编号为唯一正整数；空集合有效。最大 1 MiB、128 区域、每区 512 顶点。拒绝非 UTF-8、DTD/实体声明、错误字段、非有限坐标、路径逃逸和身份不匹配。

测试：`python3 -m unittest discover -s EPGeneral_relocalization/test -v`。旧 profile、无区域配置、关闭接收和接收失败均应保持重定位可用。


## UGV_004 修复（2026-09-24）

UGV_004 使用现有 `EPGeneral_relocalization` 0.6.0 内的 `ccs_wheeltec_localizer`，任务控制版本为 0.6.4；未新增 ROS 功能包。其他设备默认不编译 Wheeltec C++ 目标，也不启用新的失败重试策略。

初始位姿触发 NDT，在不同的新鲜点云帧上通过收敛、fitness、位姿跳变和连续两帧确认后才报告成功；静止也能完成。可信区域不是初始定位或导航的前置条件。无区域时保留首次定位结果与里程计推算，持续发布有效 `map -> odom`，暂停后续自动 NDT 修正。健康输出 `/ccs/localization_valid` 及完整 `map -> odom -> base_link` 必须新鲜；默认单位变换和陈旧缓存不能代替真实接受结果。

定位成功后可按原流程下发可信区域 XML。UGV_004 的 `trusted_regions.apply_to_ndt: true` 启用消费者确认桥接：校验地图、设备、会话、版本、map 坐标系及多边形后，将原子替换请求发布到 `/ndt_gate/set_regions`（`fast_lio_localization/AllowedRegions`）。只有 `/ndt_gate/regions` 回显相同时间戳令牌和实际区域集合后，平台才收到 `ready`；`/ndt_gate/status` 提供算法状态。非空区域启用区域内自动修正；空区域清空约束并暂停自动修正，定位状态保留。失败返回错误并尝试恢复原集合，不清除定位成功。切换地图重新启动唯一定位器，清除旧区域；不会自动载入上一地图的区域。ROS 话题不承载平台会话，桥接在地图会话锁内完成校验与确认；只能由该桥接写入。

Gemini 336L 通过已安装的 `orbbec_camera/gemini_330_series.launch`（显式设置 RGB/深度 640×480、30 FPS，驱动旋转为 0） 启动 RGB/深度，不启动识别算法。根脚本监督相机与视频：检测新鲜 640×480 RGB/深度后启动 SRT 9000、30 FPS、180° 旋转。可复用经出图检查的外部相机，仅停止自己创建的子进程；缺失、超时、异常退出记为 `CAMERA_VIDEO_DEGRADED`，不停止其他服务。根脚本的重复启动由文件锁拒绝。优先使用根脚本；组合 bringup launch 仅用于手动集成，不提供根脚本的所有权/出图监督。

UGV_004 配置 `timeouts.preparation_retry_on_failure: false`。准备保留 25 秒超时，检查健康与完整 TF；失败后保存状态、错误原因和导航日志位置，查询、迟到反馈和进程重启不会自动恢复准备。重新下发完整任务才开启新准备。日志位于 `logs/navigation/navigation-<map_id>.log`。验收只发送 PREPARE，不发送 SCHEDULE 或 move_base 目标。
