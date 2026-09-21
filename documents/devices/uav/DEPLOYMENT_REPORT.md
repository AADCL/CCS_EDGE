# UAV_001 部署结果报告

验收日期：2026-09-20。结论：**八包部署完成，构建和模拟功能验收通过；真实通信、传感器及 A8 视频通过，实机定位条件未满足，不能据此认定可实飞。**

## 设备与交付版本

| 项目 | 结果 |
| --- | --- |
| 设备 | 现有 UAV_001“金城涵道无人机”，保留名称及其他设备记录 |
| 端侧 / 地面站 | nrc@192.168.50.140 / 192.168.50.101 |
| 系统 | Ubuntu 20.04 ARM64、ROS Noetic |
| CCS 工作空间 | /home/nrc/ccs_edge_ws |
| 原生工作空间 | /home/nrc/catkin_ws，未改源码或标定 |
| 部署内容 | 七个公共包 + epgeneral_uav_integration 0.1.0，uav_001 profile |
| 启动方式 | 手动；默认独立建图模式，--static 保留纯观察，未新增自启；本次启动的栈已停止 |
| 版本追溯 | 主项目 9365e741、端侧仓库 561332fd 加本轮源码修改；实际文件以 deployed_manifest.json 为准 |

操作与回滚见[部署说明](DEPLOYMENT_GUIDE.md)，问题修正过程见[部署记录](DEPLOYMENT_RECORD.md)。完整本地证据位于主项目 artifacts/uav001_deployment_20260920/；端侧运行证据位于 ccs_edge_ws/validation 和 logs。

## 分项验收

| 范围 | 状态 | 证据和边界 |
| --- | --- | --- |
| 八包源码、配置、权限及依赖 | 已安装 | 最终文件 SHA-256/权限清单；仅补装 msgpack 和 paho-mqtt |
| 八包 Catkin | 构建通过 | build_retry.log，包含 C++ 视频节点、任务消息及 UAV 服务生成 |
| 只读预检 / launch / Bash | 通过 | --check 返回0且不新增日志，launch 展开成功，Bash 语法通过 |
| 建图协商与飞行门禁 | 实机静止通过 | 建图 PREPARE 四项检查可用并接受，随后 ABORT 清理；飞行任务 PREPARE/SCHEDULE 与 controller_start 仍被拒绝，setpoint 发布者数0 |
| MAVROS连接、锁定及落地状态 | 实机静止通过 | connected=true、armed=false、STABILIZED、landed_state=1 |
| MAVROS本地位姿 / 速度 | **实机静止失败** | 连续65秒均0条，正式遥测保留未知 |
| 飞控任务健康条件 | **阻塞** | MQTT原始 system_status=8，不满足执行门禁所需 STANDBY(3)/ACTIVE(4)；需原生飞控健康确认 |
| MAVROS IMU / 电池、Livox点云/IMU | 实机静止通过 | 下表列出频率及消息年龄 |
| MQTT / UDP 平台接收 | 实机静止通过 | 正式平台接收器运行150秒；少量 UDP 乱序被拒收并记录 |
| A8真实输入、转码、SRT解码 | 实机通过 | 最终 a8_delivery.ts：15秒225帧、640×480@15、H.264 Constrained Baseline；接收及截图解码无损坏告警 |
| A8断流重连 | 实机通过 | RTSP阻断16秒后检测无帧，重建并恢复，reconnects=1；最终规则已删除 |
| 完整任务控制 | 模拟通过 | 真实 UDP 分片→公共协调器→CCS适配器→原生C++控制器→模拟MAVROS→平台完成反馈 |
| 飞行异常与生命周期 | 模拟通过 | 重复请求、起飞悬停确认、完成/取消悬停、急停落地锁定、服务拒绝、定位过期、适配器重启不续飞、空中卸载拒绝 |
| 原生地图保存与三维变换 | 模拟通过 | 固定点云与模拟原生服务，验证非单位 odom←camera_init 变换、PCD/PGM/YAML及空/拒绝成果失败 |
| 重定位初值与持续健康 | 模拟通过 | 真实ROS初值接口、实时TF/健康成功；过期TF及健康失败；重协商不恢复缓存成功 |
| 地图打包、下载、协议兼容 | 公共包回归通过 | 地图/重定位公共包测试；未宣称实机建图下载闭环通过 |
| 真实建图、重定位闭环、实飞 | **未测** | 按授权范围未启动实机算法闭环、解锁、起飞或运动 |
| 重复启动、端口冲突、退出 | 通过 | 锁拒绝重复启动；端口占用时启动失败且未遗留栈；退出后端口释放 |
| 原生源码/标定与其他设备 | 通过 | 264个原生文件 SHA-256 全部一致；其他设备记录及原有device_types配置未变 |

## 实机静止数据

观测时长65.07秒，使用真实话题，无模拟数据混入生产master。

| 数据 | 收到条数 | 平均Hz | 最大源消息年龄 |
| --- | ---: | ---: | ---: |
| /mavros/state | 66 | 1.01 | 0.109s |
| /mavros/extended_state | 325 | 4.99 | 0.039s |
| /mavros/local_position/pose | 0 | 0 | 无数据 |
| /mavros/local_position/velocity_local | 0 | 0 | 无数据 |
| /mavros/imu/data | 3252 | 49.98 | 0.084s |
| /mavros/battery | 33 | 0.51 | 0.055s |
| /livox/lidar | 650 | 9.99 | 0.210s |
| /livox/imu | 13003 | 199.83 | 0.083s |

平台记录 MQTT heartbeat/status 各144条，有效接收跨度141.94秒；UDP Level1 2990条、Level2 745条、Level3 150条及heartbeat150条，有效跨度145.09秒。记录12次UDP乱序丢弃，平台未接纳这些乱序数据；最终描述哈希匹配。接收计数不是网络丢包率测量，不能据此宣称零丢包。

原生基座观察模式没有提供有效定位估计，且本次不允许运行实机重定位闭环。上述位姿缺失保留为失败；需在后续独立定位验收中确认外部里程计输入、FCU状态及 MAVROS/native odom 一致性，满足门禁后再进行飞行验收。

## 视频适配与现场调整

相机实际地址192.168.144.25，输入 rtsp://192.168.144.25:8554/main.264，HEVC Main 1280×720@30。端侧eth0添加192.168.144.140/24，保留雷达和无线/ZeroTier配置。

输出配置640×480、15fps、2000kbps、UDP9000。**SRT缓存从初始120ms调整为500ms**：120ms现场Wi-Fi偶发过期包/损坏，500ms最终样本无相关告警。FFmpeg接收参数为 latency=500000（微秒），GStreamer属性为 latency=500（毫秒）。这增加接收缓存延迟；本次未测端到端玻璃到玻璃时延。

显式HEVC软件解码，视频节点局部预加载ARM64 libgomp，修复ROS Python/libav静态TLS冲突。连接时请求关键帧；8秒无帧重连。未依赖云台姿态驱动提供图像，也未发送云台运动。

## 回归与证据

公共包及UAV单元回归326项通过；平台受影响六组回归75项通过；布局/文档回归101项中91项通过、10项因Windows无原生Bash跳过（这些为既有Go2看门狗测试）。UAV Bash、只读预检及生命周期已在真实Ubuntu端侧另行验证。

主要证据：
- build_retry.log、deployed_manifest.json、integrity_result.json。
- isolated_release.log：最终完整控制隔离验收。
- maps_isolated.log：地图保存和定位健康隔离验收。
- static_final.log、platform_evidence.json：实机传感器与地面站接收。
- a8_delivery.ts、a8_delivery.png、a8_delivery_metadata.json、a8_delivery.log。
- video_reconnect_final.log、lifecycle.log、final_audit.log。
- package_tests_final.log、platform_regressions.log、edge_layout_tests.log。
- remote_evidence.tar.gz：端侧日志、配置、模拟反馈和原生输出的本地归档。
- COMMAND_LOG.md、before_*.json、baseline.json：命令索引、已有配置和版本基线。

最终本次ROS进程均停止，11311/11327/11328、9000、14561/14563/14565监听端口释放，时钟显示NTP同步。原生源码/标定聚合SHA-256：
ec1d5a1a24e435d7a36b0b79484479e2ff284c4fa09690536541e760f3c45553。

**direct不提供自动避障；静态及模拟验收不等同于实飞验收。设备未被标记为可实飞。**

## 后续维护：启动日志一致性

2026-09-20 已对齐其他设备启动脚本的摘要输出与会话日志组织；10 项端侧隔离测试及 18 项本地检查通过，真实只读预检、重复启动拒绝与部署哈希核验通过。维护后的部署清单为 186 个文件。详见部署记录的“启动脚本日志一致性维护”；本次没有重做实机运行或飞行验收，原报告的实机限制继续适用。

## 后续维护：建图协商修复

2026-09-20 已将 epgeneral_map_stream 升级到 0.13.3，修复裸命令 rosrun 被 os.path.isfile 误判为文件缺失的问题。无参数一键启动现为独立 mapping 模式：允许建图和重定位阶段，飞行任务与控制器权限保持关闭。端侧重建、只读预检、Bash、定向回归、真实 CommandRunner 路径及 PREPARE→ABORT 网络协商均通过；四项 readiness 全部 available=True。测试后功能栈、原生建图和控制进程均已停止，186 项清单零差异。

本轮只验证建图准备与无成果取消，没有发送 start_mapping、没有保存真实地图，也没有执行真实重定位闭环或实飞。证据为 mapping_fix_deployment.json、mapping_fix_build.log、mapping_fix_static_verification.log、mapping_fix_static_tests_corrected.log、mapping_fix_runtime_check.log、mapping_fix_prepare_abort_tx.json、mapping_fix_prepare_abort_remote.log 和 mapping_fix_final_audit.log。
