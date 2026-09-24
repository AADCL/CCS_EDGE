# wheeltec_r550p 部署指南

整理基线：2026-09-18，CCS_dev dbe85904cdbae3d3b837f8816f29d1f030d7bd5a。设备工作空间路径保持不变。

| profile | 设备 ID | 示例连接 | 工作空间 |
| --- | --- | --- | --- |
| wheeltec_r550p | UGV_003 | nrc19@192.168.50.122 | /home/nrc19/ccs_edge_ws |
| wheeltec_r550p_02 | UGV_004 | nrc15@192.168.50.123 | /home/nrc15/ccs_edge_ws |

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

## Wheeltec 两套 profile 的边界

UGV_003 保留远程 main 已合入的导航、控制权、视频和倒车安全修复：二维导航采用 wheeltec_ccs_2d_navigation.launch，里程计 /odom，导航速度 /nav_cmd_vel；设备算法工作空间位于 /home/nrc19。不要用 UGV_004 的 launch 覆盖它。安装 profile 中 manage_ccs_video.sh、driver_patch、safety_patch 以及 launch，具体补丁和回滚流程见本页后半部分。Gemini 336L/SRT 可启动，CCS_ENABLE_VIDEO=0 可以关闭本次视频入口。

UGV_004 使用 V5.1 underlay，独立入口 wheeltec_ccs_2d_navigation_v51.launch 与本 profile 的 task_control.yaml 配套，保留 /fastlio_odom 和 /cmd_vel 约定；include 路径为外部包的 launch/include/*.launch.xml。不得混用 UGV_003 的外部启动契约。默认不启动视频，所有辅助 scripts、launch 和根目录 timesyncd 配置按对应文件安装。此配置源自本地增量，记录中的历史验收边界不因迁移而扩大。

source Noetic → 对应用户 livox_fastlio/设备导航工作空间 → CCS。UGV_004 先执行 start_ccs_edge_dev.sh --check，再按设备指南核对输入和控制权后运行。UGV_003 日志通常位于 ~/.ros 中 profile 目录，UGV_004 以工作空间 logs 和脚本打印路径为准。停止后确认底盘命令停止发布及导航子进程退出；任何运动验收必须另行在现场受控执行。

<a id="documents-wheeltec-r550p-deployment-md"></a>
<a id="documents-wheeltec-r550p-deployment-md-ugv_003-文档已合并"></a>
<a id="documents-wheeltec-r550p-deployment-md-wheeltech-r550p-端侧部署说明"></a>
<a id="documents-wheeltec-r550p-deployment-md-安全边界"></a>
<a id="documents-wheeltec-r550p-deployment-md-设备基线"></a>
<a id="documents-wheeltec-r550p-deployment-md-设备接口"></a>
<a id="documents-wheeltec-r550p-deployment-md-部署方法"></a>
<a id="documents-wheeltec-r550p-deployment-md-部署结构"></a>

<a id="documents-wheeltec-r550p-deployment-log-md"></a>
<a id="documents-wheeltec-r550p-deployment-log-md-ugv_003-文档已合并"></a>
<a id="documents-wheeltec-r550p-deployment-log-md-2026-08-28-epgeneral_map_stream-v0120-联合建图部署验证"></a>
<a id="documents-wheeltec-r550p-deployment-log-md-wheeltech-r550p-部署日志"></a>
<a id="documents-wheeltec-r550p-deployment-log-md-实机静态验收"></a>
<a id="documents-wheeltec-r550p-deployment-log-md-工作空间外变更"></a>
<a id="documents-wheeltec-r550p-deployment-log-md-建图坐标系错误修复2026-08-27"></a>
<a id="documents-wheeltec-r550p-deployment-log-md-未验证项"></a>
<a id="documents-wheeltec-r550p-deployment-log-md-约束与基线"></a>
<a id="documents-wheeltec-r550p-deployment-log-md-自动化测试"></a>
<a id="documents-wheeltec-r550p-deployment-log-md-部署流程"></a>

<a id="deploy-wheeltec-r550p-deployment-md"></a>
<a id="deploy-wheeltec-r550p-deployment-md-ugv_003-文档已合并"></a>
<a id="deploy-wheeltec-r550p-deployment-md-wheeltech-r550p-ccs-端侧部署"></a>
<a id="deploy-wheeltec-r550p-deployment-md-启动"></a>
<a id="deploy-wheeltec-r550p-deployment-md-工作空间"></a>
<a id="deploy-wheeltec-r550p-deployment-md-静态验证"></a>

<a id="deploy-wheeltec-r550p-driver-patch-readme-md"></a>

<a id="deploy-wheeltec-r550p-driver-patch-readme-md-ugv_003-wheeltec-driver-control-authority-patch"></a>
# UGV_003 Wheeltec driver control-authority patch

This patch is specific to the verified `UGV_003` source baseline in
`/home/nrc19/livox_fastlio/src/turn_on_wheeltec_robot`.

`baseline.sha256` and `patched.sha256` cover every changed source or build file.
`manage_driver_patch.sh check` reports `BASELINE`, `PATCHED`, or fails for an
unknown tree. `apply` refuses a running `/wheeltec_robot`, creates a timestamped
archive under `~/.deployment_backups`, performs a dry run, applies the patch,
verifies target hashes, and rebuilds only `turn_on_wheeltec_robot`.

After stopping the one-click stack:

~~~bash
cd /home/nrc19/ccs_edge_ws/driver_patch
./manage_driver_patch.sh check
./manage_driver_patch.sh apply
~~~

To roll back, stop the stack and pass the archive printed by `apply`:

~~~bash
./manage_driver_patch.sh rollback \
  /home/nrc19/livox_fastlio/src/turn_on_wheeltec_robot \
  /home/nrc19/livox_fastlio \
  /home/nrc19/.deployment_backups/<timestamp>_ugv003_control_authority/turn_on_wheeltec_robot.tar.gz
~~~

The patch starts in manual authority and suppresses periodic serial velocity
writes while continuing the normal serial read loop. Autonomous mode requires
the private `~set_autonomous` service and a 10 Hz heartbeat on
`/wheeltec_driver/control_heartbeat`; 0.5 seconds without heartbeat latches a
zero-output fault. `~stop` latches the same fault and `~reset_authority` returns
to manual authority after an operator reset.

<a id="deploy-wheeltec-r550p-safety-patch-readme-md"></a>

<a id="deploy-wheeltec-r550p-safety-patch-readme-md-ugv_003-wheeltech-safety-gate-patch"></a>
# UGV_003 WheelTech safety-gate patch

This patch targets the verified wheeltec_safety 0.1.0 source baseline in
/home/nrc19/livox_fastlio/src/wheeltec_safety.

The original optimistic snapshot check can be invalidated continuously by the
classified cloud, raw cloud, and costmap callbacks. The gate then publishes
zero with input_generation_changed_during_check even though all inputs are
healthy. The patch serializes snapshot, collision evaluation, and publication
with the package's existing reentrant output lock. It also raises the UGV_003
linear deadband to 0.02 m/s for measured TEB solver drift and guarantees that
no negative linear velocity reaches the chassis while reverse is disabled.

The 0.1.2 update handles the second field failure: OccupancyGrid value 99 is
already inflated by move_base, so sweeping the full measured body over it
inflated obstacles twice. The gate now uses source lethal cells (value 100)
and ignores only known lethal grid squares whose area overlaps the current
measured chassis body. Unknown cells and both fresh point-cloud checks remain
blocking. Task control clears move_base costmaps while control is disabled
before it arms the gate.

baseline.sha256 and patched.sha256 cover every changed file.
manage_safety_patch.sh check reports BASELINE, PATCHED, or rejects an unknown
tree. apply refuses a running /wheeltec_safety, creates a timestamped archive
under ~/.deployment_backups, performs a dry run, applies the patch, runs the
package tests, verifies target hashes, and rebuilds the package.

After stopping the navigation process or the one-click stack:

~~~bash
cd /home/nrc19/ccs_edge_ws/safety_patch
./manage_safety_patch.sh check
./manage_safety_patch.sh apply
~~~

To roll back, stop /wheeltec_safety and pass the archive printed by apply:

~~~bash
./manage_safety_patch.sh rollback \
  /home/nrc19/livox_fastlio/src/wheeltec_safety \
  /home/nrc19/livox_fastlio \
  /home/nrc19/.deployment_backups/<timestamp>_ugv003_safety/wheeltec_safety.tar.gz
~~~

原各 profile 的部署、验证与阶段材料已归入 [部署记录](DEPLOYMENT_RECORD.md)；历史命令只在其原日期背景下解释。


## UGV_004 修复（2026-09-24）

UGV_004 使用现有 `EPGeneral_relocalization` 0.6.0 内的 `ccs_wheeltec_localizer`，任务控制版本为 0.6.4；未新增 ROS 功能包。其他设备默认不编译 Wheeltec C++ 目标，也不启用新的失败重试策略。

初始位姿触发 NDT，在不同的新鲜点云帧上通过收敛、fitness、位姿跳变和连续两帧确认后才报告成功；静止也能完成。可信区域不是初始定位或导航的前置条件。无区域时保留首次定位结果与里程计推算，持续发布有效 `map -> odom`，暂停后续自动 NDT 修正。健康输出 `/ccs/localization_valid` 及完整 `map -> odom -> base_link` 必须新鲜；默认单位变换和陈旧缓存不能代替真实接受结果。

定位成功后可按原流程下发可信区域 XML。UGV_004 的 `trusted_regions.apply_to_ndt: true` 启用消费者确认桥接：校验地图、设备、会话、版本、map 坐标系及多边形后，将原子替换请求发布到 `/ndt_gate/set_regions`（`fast_lio_localization/AllowedRegions`）。只有 `/ndt_gate/regions` 回显相同时间戳令牌和实际区域集合后，平台才收到 `ready`；`/ndt_gate/status` 提供算法状态。非空区域启用区域内自动修正；空区域清空约束并暂停自动修正，定位状态保留。失败返回错误并尝试恢复原集合，不清除定位成功。切换地图重新启动唯一定位器，清除旧区域；不会自动载入上一地图的区域。ROS 话题不承载平台会话，桥接在地图会话锁内完成校验与确认；只能由该桥接写入。

Gemini 336L 通过已安装的 `wheeltec_yolo11/camera_rgbd.launch camera_fps:=30` 启动 RGB/深度，不启动识别算法。根脚本监督相机与视频：检测新鲜 640×480 RGB/深度后启动 SRT 9000、30 FPS、180° 旋转。可复用经出图检查的外部相机，仅停止自己创建的子进程；缺失、超时、异常退出记为 `CAMERA_VIDEO_DEGRADED`，不停止其他服务。根脚本的重复启动由文件锁拒绝。优先使用根脚本；组合 bringup launch 仅用于手动集成，不提供根脚本的所有权/出图监督。

UGV_004 配置 `timeouts.preparation_retry_on_failure: false`。准备保留 25 秒超时，检查健康与完整 TF；失败后保存状态、错误原因和导航日志位置，查询、迟到反馈和进程重启不会自动恢复准备。重新下发完整任务才开启新准备。日志位于 `logs/navigation/navigation-<map_id>.log`。验收只发送 PREPARE，不发送 SCHEDULE 或 move_base 目标。


UGV_004 需要设备现有 `bwrap`（bubblewrap）：原生 FAST-LIO 只读运行，固定 Log/PCD 路径通过 mount namespace 映射到 CCS `run/native-fastlio-{log,pcd}`。请勿去原生工作空间修改路径或重新编译。启动指控平台 NTP 服务后再执行根脚本；无 NTP 响应不会跳过时间校验。
