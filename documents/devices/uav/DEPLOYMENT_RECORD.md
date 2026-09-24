# UAV_001 部署记录

日期：2026-09-20；现有设备“金城涵道无人机”，IP 由 192.168.50.150 更新为 192.168.50.140。地面站 192.168.50.101。

基线：主项目 9365e741fa6cb7236ccd317d197a299a796f9c65；端侧仓库 561332fdf5081483c74994b3f403a7ef4248ebde，部署源码包含本轮未提交改动，以 deployed_manifest.json 为实际文件依据。原有平台配置改动在 before_*.json 和 before_changes.patch 中保留。

1. SSH 盘点 Ubuntu20.04/ARM64/Noetic、源工作空间、进程、端口、时钟、网络与标定哈希；保存原生文档和关键源码参考。初始没有 CCS 工作空间，也没有运行 ROS 控制栈。
2. 对相机候选地址实施有线 ARP 检查，发现真实 192.168.144.25；补充 eth0 地址并保存原 NetworkManager 地址快照。获取真实 H.265 RTSP 流。
3. 新建 uav_001 七份配置、新增 UAV 集成包，适配原生任务、建图、重定位；更新平台 UAV_001 记录及地图坐标配置。
4. 在独立 /home/nrc/ccs_edge_ws 传输八包、规范 LF/权限，按文件校验 SHA-256。第一次构建发现 catkin_python_setup 与 generate_messages 顺序错误，修复后八包构建通过。
5. 实机启动发现 msgpack/paho 缺失及 MQTT mission 字段错误；安装两个依赖并补足配置。遥测描述表保持平台完整公共描述，仅改 ROS 来源，修复 descriptor_hash 拒收。
6. A8 适配过程中发现自动硬件解码无帧、ARM64 libgomp TLS 冲突及 SRT 延迟单位混用；改显式软件解码、视频节点局部预加载和毫秒属性。120ms Wi-Fi 传输出现损坏包，对照500ms更稳定，因此调整设备及平台缓存。
7. 独立 ROS master 11327 运行模拟 MAVROS、真实原生 C++ 控制器及 CCS 适配器；11328 验证模拟保存服务、地图变换、定位初值及新鲜度。生产 master 11311 仅运行静态观察模式。
8. 采集真实 MAVROS、IMU、雷达、MQTT、UDP 和 SRT 证据；缺失真实位姿如实报告。测试 RTSP 中断16秒、超时重连，未触发云台运动、实机解锁、起飞或建图定位闭环。
9. 最终重新同步文件清单、执行回归、归档日志并停止本次自有进程。最终结果和限制保留在本记录及本地部署证据中。

证据统一位于主项目 artifacts/uav001_deployment_20260920/；build*.log 保留构建重试，isolated*.log 保留测试修复历史，最终结论使用报告指定的最终日志，不以失败前的中间结果替代。凭据未写入文件。

操作步骤及回滚见[部署说明](DEPLOYMENT_GUIDE.md)。

## 2026-09-20 启动脚本日志一致性维护

对照 Go2 robot3、WheelTec R550P_02 和 ground_air_agv 启动脚本，统一 UAV_001 的终端等级提示、带时间戳的 startup.log、监控明细及 logs/latest 会话入口。工作空间根目录 start_ccs_edge_dev.sh 继续转发至 UAV profile，兼容 --preflight 预检别名。后续独立建图模式修复将无参数默认行为调整为 mapping，见下一节。

裁剪预检内部 JSON、重复监控缺失列表和终端异常堆栈；监控重试及完整堆栈保存在 runtime_monitor.log，相同控制器保留告警每 30 秒提醒一次，状态变化立即记录。保留 roscore.log、bringup.log 和 ROS 子进程诊断；MQTT、建图、重定位日志归入本次会话，未修改公共包或原生驱动日志级别。未清空历史日志。重复启动输出明确错误；遗留已退出 PID 的停止请求不再打印堆栈。运行故障返回非零退出码，保留空中/未知状态禁止清理控制器的保护。

六个启动相关文件已备份至端侧 validation/logging_backup_20260920T144245/，本地副本位于 artifacts/uav001_deployment_20260920/logging_backup/。端侧部署清单包含 186 个文件，全部 SHA-256/权限一致。日志维护证据为 logging_deployment.json、logging_installed_tests.log、logging_verification.log。

验证：10 项 Linux 隔离测试通过（含异常退出、重复启动、监控恢复、空中停止保护），18 项本地配置/文档/分发检查通过；真实端侧 --check / --preflight 均通过且未改变 logs/、run/ 文件，launch 展开 12 个节点并正确传递会话日志路径。本次未启动或停止正式功能栈，新的会话输出在下一次启动时生效。

## 2026-09-20 建图协商拒绝修复（已部署并静态验收）

开启建图流程时，prepare_mapping 返回“mapping integration script is unavailable: rosrun”。根因是地图流包将配置中的裸命令 rosrun 当作文件路径，用 os.path.isfile 检查当前目录；端侧实际存在且可执行的 /opt/ros/noetic/bin/rosrun 因此被误判为不可用。修复改为：裸命令通过 PATH 查找，显式路径继续校验文件和执行权限，并将 UAV 离线集成检查纳入预检。

同时拆分建图权限与飞行执行权限。无参数和 --mapping 设置 mapping_enabled=true、execution_enabled=false，仅允许阶段管理器启动建图、保存地图和启动重定位；任务适配器与原生控制器继续拒绝执行。--static 将两项权限均关闭，作为纯观察模式；--flight 将两项权限均打开。profile launch 分别传递两个参数，避免为了建图而开放任务执行。飞行模式已有的空中或状态未知时保留控制器和定位的关停保护未改变。

本轮通过清单漂移闸门后原子部署 16 个文件，原文件及 deployed_manifest.json 备份到 validation/mapping_fix_backup_20260920T074349965735Z/。地图流包升级为 0.13.3；工作空间八包重建通过，--check / --preflight 均通过且未改变 logs/、run/，launch 展开 12 个节点，186 项部署清单 SHA-256、字节数和权限零差异。端侧 Bash、15 项定向地图流回归、真实 UAV 配置 CommandRunner 检查及 10 项 Linux 启动生命周期测试通过。

无参数入口实测进入 mapping 模式，mapping_enabled=true、execution_enabled=false；10 个必需节点齐全，/mavros/setpoint_position/local 发布者为 0。阶段服务对 controller_start 返回“mapping mode: flight control disabled”，未生成 controller_process.json。地面站 192.168.50.101 随后发送唯一 prepare_mapping；端侧记录 pointcloud、imu、artifact_storage、map_generation 四项 available=True，并返回 accepted=True。6 秒后同会话 abort_mapping 返回 accepted=True，记录“session aborted without artifacts”。本轮没有发送 start_mapping、没有创建 mapping_process.json、没有调用地图保存，也没有触发解锁、起飞或运动。

最初一次端侧全量地图流测试把 UAV 生产 YAML 强制注入多设备通用夹具，导致 Scout/Ground-Air 用例因 profile 前置条件不成立而失败；该结果保留在 mapping_fix_static_tests.log。修正后的 mapping_fix_static_tests_corrected.log 仅运行本次改动直接相关的端侧用例并通过；全仓布局下的完整地图流回归在本地通过。最终停止本次功能栈，相关进程和监听端口全部释放，最终审计写入 validation/mapping_fix_final_audit.json。

## 2026-09-22 启动结构对齐 UGV_004

读取 UGV_004 端侧交付文档和 `wheeltec_r550p_02` 启动入口后，将 UAV_001 收敛为相同的工作空间根启动形式：先执行 `./start_ccs_edge_dev.sh --check`，再无参数前台启动，使用 `Ctrl+C` 有序停止。UAV 的 `--static`、`--mapping`、`--flight` 权限门禁继续保留；无参数仍为不开放飞行控制的 mapping 模式。

运行文件从 `deploy/uav_001` 平铺到 `config/uav_001`、`launch` 和 `scripts`。根 launch 向 MQTT、UDP、视频、地图、重定位、任务协调器和 UAV 任务适配器显式传入同一 profile 配置，避免运行副本与包内共享配置分叉。PID、锁和启动记录统一放入 `run/managed`，会话目录采用 UGV_004 的 UTC 纳秒时间加 PID 命名。

端侧旧嵌套 profile 和三份重复 UAV 文档在备份后从活动工作空间移除，改为单一 `docs/uav_001/DEPLOYMENT.md`。仓库保留当前指南与本历史记录，删除内容重复的独立结果报告；完整历史证据仍在 `artifacts/uav001_deployment_20260920` 和 `artifacts/uav001_update_20260922`。

实际迁移于 2026-09-22 完成。覆盖和删除前的文件及部署清单备份到端侧
`validation/startup_alignment_backup_20260922T034932484192Z`。安装 14 个平铺启动文件，
移除 13 个旧 profile 文件、三份端侧重复 UAV 文档和旧 `run/supervisor.lock`；部署清单
仍为 190 项。端侧 `--check` 通过且 `logs`、`run` 内容和时间戳摘要不变，launch 静态展开
12 个节点并保持 `mapping_enabled=true`、`execution_enabled=false`，10 项 Linux 隔离生命
周期测试通过。验收结束后没有 UAV CCS 进程，未启动真实建图、重定位或飞行控制。

## 2026-09-22 重定位与任务功能启用

按运行授权执行 `./start_ccs_edge_dev.sh --flight`，将 UAV_001 从默认建图模式有序切换到
同时开放重定位阶段管理和任务执行的 flight 模式。切换前验证飞控未解锁、已落地、控制器
未运行且无飞行/急停锁；旧会话通过根启动脚本有序停止后启动新会话。旧运行记录和陈旧的
建图进程记录备份到
`validation/feature_enable_backup_20260922T042704.411642654Z`，未配置自启动。

启用后启动记录为 `mode=flight`、`mapping_enabled=true`、`execution_enabled=true`，10 个必需
ROS 节点正常，任务控制 UDP 14563 和重定位控制 UDP 14565 正常监听。最终只读审计确认
MAVROS 已连接、飞控保持未解锁、`landed_state=1`、阶段为空闲、控制器未运行，且
`/mavros/setpoint_position/local` 发布者为 0。端侧可访问地面站 192.168.50.101 和平台重定位
HTTP 14601。本次仅启用功能通道，未创建重定位会话、未准备或执行任务、未触发解锁或运动。

指控平台新增 `ducted_uav` 重定位 profile（`vision_pose`、`odom`），将 UAV_001 设置为可用并
保留活动地图 `7c48e462-a66d-4030-aacf-0a08abd8b5c9`。平台重启后任务 UDP 14564、重定位 UDP
14566 和重定位 HTTP 14601 正常监听；重定位、设备配置、任务服务、任务协议和任务页面共
60 项定向测试通过。完整启用和安全审计证据位于
`artifacts/uav001_startup_alignment_20260922/enable_features_*.log`。

端侧唯一启动文档同步后，原文档和部署清单备份到
`validation/feature_enable_doc_backup_20260922T045106.698840694Z`。最终审计逐项验证部署清单
中的 190 个文件，SHA-256、字节数和权限全部一致；指控平台日志确认 UAV_001 MQTT 会话已
重新连接并持续收到遥测。
