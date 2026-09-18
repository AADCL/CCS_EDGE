# go2 部署指南

整理基线：2026-09-18，CCS_dev dbe85904cdbae3d3b837f8816f29d1f030d7bd5a。设备工作空间路径保持不变。

| profile | 设备 ID | 示例连接 | 工作空间 |
| --- | --- | --- | --- |
| go2_edu | QRD_001 | nvidia@192.168.50.100 | /home/nvidia/ccs_edge_ws |
| go2_robot2 | QRD_002 | unitree@192.168.50.111 | /home/unitree/ccs_edge_ws |
| go2_robot3 | QRD_003 | unitree@192.168.50.112 | /home/unitree/ccs_edge_ws |

## 当前部署流程

先阅读 [通用使用手册](../../USER_MANUAL.md) 的依赖、备份与配置章节，以及 [接口参考](../../INTERFACE_REFERENCE.md)。从本仓库根目录选择上表 profile，生成空 staging：

~~~bash
python3 scripts/prepare_profile.py --profile PROFILE_NAME --output /tmp/ccs-stage
~~~

将 staging 传至设备，设置 WORKSPACE、PROFILE、STAGE。升级前停止 CCS，备份旧 src 包、config、launch、scripts 与服务文件；保留 maps、mission 和设备状态数据。以下仅是首次安装公共部分，同名源包存在时先停止并备份，不叠加复制：

~~~bash
WORKSPACE=/home/实际用户/ccs_edge_ws
PROFILE=实际profile
STAGE=/tmp/ccs-stage
PROFILE_SOURCE="$STAGE/deploy/$PROFILE"
install -d -m 0750 "$WORKSPACE/src" "$WORKSPACE/config/$PROFILE" "$WORKSPACE/launch" "$WORKSPACE/scripts"
for package in "$STAGE/src/"*; do
  name=$(basename "$package")
  test ! -e "$WORKSPACE/src/$name" || { echo "请先备份已有包: $name"; exit 1; }
  cp -a "$package" "$WORKSPACE/src/"
done
install -m 0640 "$PROFILE_SOURCE/config/"*.yaml "$WORKSPACE/config/$PROFILE/"
install -m 0750 "$PROFILE_SOURCE/start_ccs_edge_dev.sh" "$WORKSPACE/start_ccs_edge_dev.sh"
if [ -d "$PROFILE_SOURCE/launch" ]; then cp -a "$PROFILE_SOURCE/launch/." "$WORKSPACE/launch/"; fi
if [ -d "$PROFILE_SOURCE/scripts" ]; then cp -a "$PROFILE_SOURCE/scripts/." "$WORKSPACE/scripts/"; fi
if [ -f "$PROFILE_SOURCE/verify_ros_contract.py" ]; then install -m 0755 "$PROFILE_SOURCE/verify_ros_contract.py" "$WORKSPACE/scripts/"; fi
find "$WORKSPACE/src" "$WORKSPACE/scripts" -type f \( -name '*.sh' -o -path '*/scripts/*.py' \) -exec chmod 0755 {} +
# 先 source Noetic 和本机 underlay，然后：
cd "$WORKSPACE"
rosdep install --from-paths src --ignore-src -r -y
catkin_make -j2 -DPYTHON_EXECUTABLE=/usr/bin/python3
source devel/setup.bash
~~~

核对 profile 中 device_id、地址、frame、话题、外部命令及地图路径；这里的示例 IP 不是现场发现结果。包内配置只影响默认单包 launch，一键脚本读取工作空间 config/profile。修改后停止并重启，无热重载；deployment.enabled 等说明字段不能代替真实启停。

## 升级、失败处理与回滚

记录 git rev-parse HEAD、所选 profile、修改配置的 SHA-256、构建输出及运行日志。先核验 ROS 包唯一性、source 顺序、话题新鲜度和 TF 唯一发布者，再做现场许可范围内的功能测试。首次部署和历史记录不等于当前设备验收。失败先停入口和其子进程，再恢复备份整包与配置，重新构建并核验；不删除地图、任务和现场状态。新增证据按设备 ID、日期追加到 [部署记录](DEPLOYMENT_RECORD.md)，包含失败、未验收项目、哈希和回滚结果。

## Go2 差异与核验

go2_edu 为 legacy 接口，保留七公共包、重定位禁用、不启动任务。go2_robot2/3 增加 Go2 integration 包，先 source /opt/ros/noetic/setup.bash、/home/unitree/go2_nav_ws/devel/setup.bash，再 source CCS；原生状态、控制权和输入新鲜度通过预检后才启动任务协调器。建图与定位互斥，急停锁存必须按现场流程解除。

Robot2/3 必须安装 profile/scripts 全部助手到工作空间 scripts；Robot3 另安装 verify_ros_contract.py，包含 ccs_go2_preflight、ccs_ros_readiness、ccs_sntp_sync，不能只复制根启动脚本。Robot3 的 map_stream 包须提供 mapping_prerequisites_go2_robot3.launch。D435i 参数以对应 video_srt.yaml 为准，不能套用另一台设备的帧率。

在设备上核对 rospack find epgeneral_go2_integration、rosnode list 和配置中原生输入话题；先执行静态核验，再在受控环境验证任务、急停和建图。启动用工作空间根 start_ccs_edge_dev.sh；停止按 Ctrl-C 并确认其子进程退出。日志位置由脚本输出和 ~/.ros 中该 profile 的目录确认。授时权限与失败回退见通用接口参考。

<a id="documents-go2-deployment-lessons-md"></a>

<a id="documents-go2-deployment-lessons-md-go2-端侧部署与故障恢复经验"></a>
# GO2 端侧部署与故障恢复经验

维护日期：2026-09-12；适用当前 CCS 0.24.0 源码。本文用于后续部署和问题排查，配合[从零部署指南](../../USER_MANUAL.md#documents-deployment-guide-md)、[接口清单](../../INTERFACE_REFERENCE.md#documents-config-topic-reference-md)和[使用手册](../../USER_MANUAL.md#documents-user-manual-md)。设备事实只追加到 [QRD_002](DEPLOYMENT_RECORD.md#deploy-records-qrd-002-deployment-md)、[QRD_003](DEPLOYMENT_RECORD.md#deploy-records-qrd-003-deployment-md)，本文不复制其完整日志与哈希表。

<a id="documents-go2-deployment-lessons-md-1-先确定证据对应的版本与时间"></a>
## 1. 先确定证据对应的版本与时间

2026-09-12 已完成两台相同任务模块的增量部署、服务人工复位、受控退出重启及联合下发验收。随后用户确认“落地测试已完成”；此为用户现场确认，未另提供执行次数、轨迹、速度或逐项日志。保留先前工具验收“未发送 execute/SCHEDULE、底盘 disabled、定位 standby”的原始记录；它描述当时状态，不是后续现场的实时结论。

当前工作树还包含后续普通卸载后重新准备的修复；既有记录仅证明它完成本地测试、尚未部署。用户的总体现场确认不改变该修订的部署身份，也不表示 QRD_003 其他存储/启动锁改动已安装。每次实际发布都要比对本地文件、端侧实际导入路径、SHA-256 和进程启动时间，不能用“源码已修复”代替“运行进程已加载”。

<a id="documents-go2-deployment-lessons-md-2-联合下发拒绝先查锁存时间再查通信"></a>
## 2. 联合下发拒绝：先查锁存时间，再查通信

| 现象 | 已确认原因或判断 | 下一步 |
| --- | --- | --- |
| prepare 很快返回 EMERGENCY_STOP_LATCHED | 协调器读取已有安全文件；此拒绝分支不调用底盘 enable 服务 | 读取 recorded_at/reason，关联该时刻的退出日志，而不是当前 task_prepare 时间 |
| 更新代码、重启后仍拒绝 | 急停文件持久保留；QRD_002 曾保留前一天停用超时的标记 | 修复原因后按服务复位流程处理，重传不能清锁 |
| 退出时 enable 返回 no response/超时 | master/bridge 先退出，或协调器内部卸载先于适配器关闭信号造成重复停用 | 检查进程组、清理顺序、实际适配器版本及重复终止入口 |
| commit accepted，但任务 failed | 保存与导航准备是不同阶段 | 读取 execution_feedback.error_code；LOCALIZATION_UNAVAILABLE 不等于急停 |

只读检查至少保存：安全文件原文、关联启动/退出日志、任务状态及反馈、底盘诊断、PID/PPID/PGID/SID、启动命令与源码哈希。不要删除损坏标记；损坏状态同样按锁存拒绝。无法确定停用结果时保留锁存和证据。

<a id="documents-go2-deployment-lessons-md-3-幂等关闭不能变成绕过停用或永久禁止复用"></a>
## 3. 幂等关闭不能变成绕过停用或永久禁止复用

根脚本将自有 roscore/roslaunch 放入独立会话并验证归属，避免终端 Ctrl+C 同时杀掉所有子进程。清理顺序固定为：任务消费与适配器 → 确认底盘停用 → 逆序停止其他自有组件 → 最后停止自建 master。共享 master 不归本脚本清理。

协调器内部 `UNLOAD/request_id=shutdown-unload` 可以早于适配器的 ROS 关闭信号。两个入口必须共用串行、幂等的收尾：先设置关闭/停止标志并停止监控，再取消目标、发布零速、确认停用、清理自有导航。一次关闭的首次失败结果不能被后续重复入口覆盖；关闭中拒绝新 PREPARE/SCHEDULE/复位，watchdog 和旧回调不再重复终止。不要持有状态锁等待控制 RPC 或工作线程结束。

新鲜 disabled 的快捷确认仅用于收尾上下文，包括内部 shutdown-unload；不能只判断 `rospy.is_shutdown()`，还要覆盖 `is_shutdown_requested()` 回调阶段。快捷成功必须同时排除未完成的控制过渡和 RPC，否则仍按有界等待及严格停用处理。缓存 false 不能证明迟到的 enable 已结束；超时仍锁存，保留迟到 enable 的补偿停用。普通 STOP/UNLOAD 仍要求服务成功和新鲜状态确认。

后续源码将“协调器卸载但适配器继续存活”和“永久 close/ROS 退出”区分：前者收尾完成后，新 PREPARE 可在重新通过安全、地图、定位检查后恢复监控；后者不得重新接收任务。失败锁存仍需人工复位。该后续修订的部署状态见第1节，不纳入旧部署哈希。后续回归必须覆盖卸载后复用，防止关闭幂等修复引入永久 BUSY。

<a id="documents-go2-deployment-lessons-md-4-人工复位与退出验收"></a>
## 4. 人工复位与退出验收

在本次操作已获授权、根因已修复、无准备/执行/控制过渡且持续新鲜 disabled 的条件下，按[人工急停复位](../../USER_MANUAL.md#documents-user-manual-md-go2-%E4%BA%BA%E5%B7%A5%E6%80%A5%E5%81%9C%E5%A4%8D%E4%BD%8D)调用 `/epgeneral_navigation_task_adapter/reset_emergency_stop`（std_srvs/Trigger）。检查 success、标记解除以及底盘仍 disabled；失败保留响应，不直接删除文件或反复强制复位。

每台复位后观察至少三个原重试周期；2026-09-12 的证据为每台18条连续诊断、约17秒，motion_enabled=false、运动指令为零。再分别验证 SIGINT/TERM 的有序退出和重启，检查自有节点及 master 归属清理、无新锁存。不要把隔离测试的“生产服务调用=0”误写成正常启动/清理完全没有停用调用。

<a id="documents-go2-deployment-lessons-md-5-联合下发必须验证完整传输而非只看-ack"></a>
## 5. 联合下发必须验证完整传输，而非只看 ACK

读取实际 `timeouts.transfer_seconds`；两台本次配置均为10秒。先准备好原任务内容、设备地址、接收证据和检查程序，再使用新请求 ID 连续完成两台 prepare/chunk/commit。不要在阶段之间停下来人工读日志，以免让会话超时。

`sendto` 成功只证明数据报交给本机；ACK accepted 还应核对请求 ID、缺失分片以及端侧结果。会话超时后，相同 revision/CRC 的已有任务仍可幂等接受 commit，因此单看该 ACK 无法证明本轮分片实际落盘。完整传输验收应同时取得以下证据：

1. 同一批新请求的 prepare/commit 接受，无缺失分片，端侧收到全部 chunk。
2. 本轮 `trajectory XML committed` 日志；保存的 task/subtask/device ID、revision、CRC、航点数与原任务一致。
3. 传输后底盘状态与导航准备反馈。若验收范围仅下发，不发送 execute/SCHEDULE 或运动目标。

本次首轮人工分步检查导致会话超时，只证明幂等提交；改为约0.6秒连续发送后，两台均实际落盘 revision=5、4个原航点。失败尝试和最终成功证据均保留。原平台占用 UDP 14564 时，不应为了测试另行抢占该端口；使用正式客户端回执或带请求 ID 的端侧 ACK/落盘证据。仅有端侧证据时，不宣称平台 UI 或持久存储也已验收。

<a id="documents-go2-deployment-lessons-md-6-下发定位与执行分别判定"></a>
## 6. 下发、定位与执行分别判定

`received/commit accepted` 表示轨迹保存；`ready` 表示导航准备完成；执行还需独立调度及运动验收。重启会使定位回到 standby，旧地图状态文件不能替代实时定位/TF/里程计。`LOCALIZATION_UNAVAILABLE` 属于可恢复准备错误，保留按配置重试；`EMERGENCY_STOP_LATCHED` 不自动重试，服务复位后重新下发。

根脚本的 SNTP 可用性检查与任务 UTC 调度容差是两层约束。取消启动阶段的时差门控，不代表可以移除同步执行的时间检查；填写配置时分别核对，不能用增大容差掩盖授时故障。

<a id="documents-go2-deployment-lessons-md-7-首次部署中其他已出现的问题"></a>
## 7. 首次部署中其他已出现的问题

| 问题 | 可复用处理 | 验收证据 |
| --- | --- | --- |
| `/usr/bin/env: bash\r`，建图返回127 | 在 staging 统一所有直接及间接脚本为 UTF-8 无 BOM/LF；保留权限，规范化后重新算哈希 | 目标 bash -n、LF、可执行位、调用路径均通过；不只检查根脚本 |
| D435i 驱动能独立工作，一键入口失败 | 默认单设备自动选择，不传 device_type；CCS_D435_SERIAL 原样传 serial_no，不加下划线；先核对旧驱动占用 | 节点注册后独立检查至少两帧 RGB，时间戳递增、年龄≤3秒，最多等30秒；通过后才 camera ready/SRT |
| 相机规格被复制错 | 保留各 profile 参数：Robot2 RGB 640×480@30，Robot3 640×480@15；关闭深度/红外/相机IMU/TF | 按实际分辨率/帧率验收；USB2.1、Right MIPI 旧告警照实记录，不宣称修复硬件 |
| generate_pgm 缺少 export/public_map.pcd | 先确认 accumulator 本次保存成功，从 current 的新鲜非空 PCD 生成会话快照，再导出并生成 PGM/YAML | save响应、PCD时间/点数、会话来源和成果；不能拿上次文件填补本次失败 |
| bridge exited 导致整栈退出 | 区分真实进程退出和临时 ROS master 查询失败，检查 LAN/DDS/雷达网卡及默认 disabled 启动参数 | PID/退出码/组件日志和新鲜诊断；不能屏蔽真实故障或靠使能排障 |
| 日志/状态混用或重复启动干扰 | 日志按 profile；Robot3 为启动时间目录并设置 ROS_LOG_DIR，任务/地图/锁/安全状态留原路径 | --check 前后节点/PID及 latest 不变；旧记录保留，回滚不覆盖最新安全状态 |

参考 profile 不等于整机复制。设备 ID、namespace、IP、工作空间、外参、话题类型/字段、Trigger/SetBool 契约、地图绑定及安全文件均须逐机确认。不要复制另一设备的 mission、地图绑定或急停状态。

<a id="documents-go2-deployment-lessons-md-8-以后每次增量交付的最小闭环"></a>
## 8. 以后每次增量交付的最小闭环

- 冻结文件列表与本地哈希，保存受影响文件/权限、日志、进程及安全原文；保留既有工作树修改。
- 跑受影响任务单测、两个 profile/信号进程回归、文档检查、语法及 LF。隔离 ROS master 使用独立端口和全部隔离的话题/服务/配置，准备完整 fixture；结束确认测试节点与端口全部释放。
- 仅安装已验证增量，核对实际导入路径与目标哈希；Python/文档更新不默认 catkin 重建。新源码要由正常重启的进程加载，不能只证明磁盘文件更新。
- --check 比较前后生产节点/PID、日志 latest 和安全文件；正常启动检查最终 ready、数据新鲜度及停用状态。验收失败时保存证据，仅恢复匹配的代码/配置，最新安全状态不回滚。
- 按设备 ID 追加实测与用户反馈，明确确认来源、日期、范围、源码身份和未提供的细节；历史清单及哈希不事后改写。端侧同步文档时按[离线交付层级](../../USER_MANUAL.md#documents-deployment-guide-md-9-%E6%97%A5%E5%BF%97%E4%B8%8E%E4%BA%A4%E4%BB%98)携带依赖链接，并重新生成该文档批次清单。

后续现场确认不能推断设备此刻在线、定位成功或运行着某个源码修订；下一次实机操作仍先重新盘点。

<a id="deploy-go2-edu-deployment-md"></a>
<a id="deploy-go2-edu-deployment-md-qrd_001-文档已合并"></a>
<a id="deploy-go2-edu-deployment-md-go2-edu-端侧部署"></a>
<a id="deploy-go2-edu-deployment-md-发布内容"></a>
<a id="deploy-go2-edu-deployment-md-安装"></a>
<a id="deploy-go2-edu-deployment-md-数据源"></a>
<a id="deploy-go2-edu-deployment-md-验证与回滚"></a>

<a id="deploy-go2-robot2-deployment-md"></a>
<a id="deploy-go2-robot2-deployment-md-qrd_002-文档已合并"></a>
<a id="deploy-go2-robot2-deployment-md-failure-analysis-and-compatibility"></a>
<a id="deploy-go2-robot2-deployment-md-go2-robot-2-deployment"></a>
<a id="deploy-go2-robot2-deployment-md-incremental-acceptance"></a>
<a id="deploy-go2-robot2-deployment-md-migration-and-clock-service"></a>
<a id="deploy-go2-robot2-deployment-md-source-of-truth-and-layout"></a>
<a id="deploy-go2-robot2-deployment-md-startup-and-native-parameters"></a>

<a id="deploy-go2-robot2-readme-md"></a>
<a id="deploy-go2-robot2-readme-md-qrd_002-文档已合并"></a>
<a id="deploy-go2-robot2-readme-md-go2-robot-2-端侧部署"></a>

<a id="deploy-go2-robot2-validation-md"></a>
<a id="deploy-go2-robot2-validation-md-qrd_002-文档已合并"></a>
<a id="deploy-go2-robot2-validation-md-go2-robot-2-部署与增量验证记录"></a>
<a id="deploy-go2-robot2-validation-md-udp-真机接收"></a>
<a id="deploy-go2-robot2-validation-md-增量测试"></a>
<a id="deploy-go2-robot2-validation-md-备份与载荷"></a>
<a id="deploy-go2-robot2-validation-md-已完成结果"></a>
<a id="deploy-go2-robot2-validation-md-控制状态与安全边界"></a>
<a id="deploy-go2-robot2-validation-md-旧状态说明"></a>
<a id="deploy-go2-robot2-validation-md-迁移与回滚用法"></a>
<a id="deploy-go2-robot2-validation-md-验证范围与版本"></a>

<a id="deploy-go2-robot3-deployment-md"></a>
<a id="deploy-go2-robot3-deployment-md-qrd_003-文档已合并"></a>
<a id="deploy-go2-robot3-deployment-md-acceptance-evidence"></a>
<a id="deploy-go2-robot3-deployment-md-emergency-latch-and-per-start-log-increment"></a>
<a id="deploy-go2-robot3-deployment-md-installation"></a>
<a id="deploy-go2-robot3-deployment-md-mapping-script-line-ending-increment"></a>
<a id="deploy-go2-robot3-deployment-md-qrd_003-deployment-procedure"></a>
<a id="deploy-go2-robot3-deployment-md-rollback"></a>
<a id="deploy-go2-robot3-deployment-md-runtime-monitor-increment"></a>

<a id="deploy-go2-robot3-readme-md"></a>
<a id="deploy-go2-robot3-readme-md-qrd_003-文档已合并"></a>
<a id="deploy-go2-robot3-readme-md-daily-operation"></a>
<a id="deploy-go2-robot3-readme-md-go2-robot-3-qrd_003"></a>
<a id="deploy-go2-robot3-readme-md-hardware-and-services"></a>
<a id="deploy-go2-robot3-readme-md-runtime-layout"></a>
<a id="deploy-go2-robot3-readme-md-runtime-monitoring"></a>

<a id="deploy-go2-robot3-validation-md"></a>
<a id="deploy-go2-robot3-validation-md-qrd_003-文档已合并"></a>
<a id="deploy-go2-robot3-validation-md-build-and-static-validation"></a>
<a id="deploy-go2-robot3-validation-md-camera-and-one-click-startup"></a>
<a id="deploy-go2-robot3-validation-md-emergency-stop-recovery-and-per-start-logs-2026-09-10"></a>
<a id="deploy-go2-robot3-validation-md-live-sensor-sample"></a>
<a id="deploy-go2-robot3-validation-md-local-pre-pr-review-follow-up-2026-09-11"></a>
<a id="deploy-go2-robot3-validation-md-mapping-negotiation-line-ending-repair-2026-09-10"></a>
<a id="deploy-go2-robot3-validation-md-platform-reload-and-mqtt-capture"></a>
<a id="deploy-go2-robot3-validation-md-qrd_003-validation-record"></a>
<a id="deploy-go2-robot3-validation-md-result-summary"></a>
<a id="deploy-go2-robot3-validation-md-runtime-first-map-export-repair-2026-09-10-1558"></a>
<a id="deploy-go2-robot3-validation-md-runtime-watchdog-correction-2026-09-10"></a>
<a id="deploy-go2-robot3-validation-md-safe-shutdown-and-remaining-acceptance"></a>
<a id="deploy-go2-robot3-validation-md-source-payload-and-backup"></a>
<a id="deploy-go2-robot3-validation-md-startup-script-incremental-update-2026-09-10"></a>
<a id="deploy-go2-robot3-validation-md-startup-time-service-availability-update-2026-09-10"></a>
<a id="deploy-go2-robot3-validation-md-target-preflight-and-contracts"></a>
<a id="deploy-go2-robot3-validation-md-udp-capture"></a>

原各 profile 的部署、验证与阶段材料已归入 [部署记录](DEPLOYMENT_RECORD.md)；历史命令只在其原日期背景下解释。
