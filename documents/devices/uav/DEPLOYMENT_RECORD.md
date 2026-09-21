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
9. 最终重新同步文件清单、执行回归、归档日志并停止本次自有进程。最终结果和限制见[部署结果报告](DEPLOYMENT_REPORT.md)。

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
