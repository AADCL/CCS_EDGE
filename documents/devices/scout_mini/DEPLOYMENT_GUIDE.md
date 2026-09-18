# scout_mini 部署指南

整理基线：2026-09-18，CCS_dev dbe85904cdbae3d3b837f8816f29d1f030d7bd5a。设备工作空间路径保持不变。

| profile | 设备 ID | 示例连接 | 工作空间 |
| --- | --- | --- | --- |
| scout_mini | UGV_001 | nvidia@192.168.50.120 | /home/nvidia/ccs_edge_ws |

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

## Scout Mini 差异与核验

underlay 顺序为 Noetic → RealSense 工作空间 → github_upload/AADCL_UAV_UGV/Scout_mini 导航工作空间 → livox_fastlio → CCS；使用设备实际路径。将 profile/launch 全部复制到工作空间 launch，适配 base launch 是首次安装必需输入。

执行工作空间 start_ccs_edge_dev.sh，核验底盘里程计、雷达点云、TF、视频以及八个预期节点，节点与话题详见接口参考。任务依赖外部导航栈，先确认 move_base action 再操作任务。Ctrl-C 停止并核对进程；日志在 ~/.ros/ccs_edge_dev_scout_mini/log。地图描述文件哈希、地面站坐标与重定位配置应一致。

<a id="documents-scout-mini-deployment-md"></a>
<a id="documents-scout-mini-deployment-md-ugv_001-文档已合并"></a>
<a id="documents-scout-mini-deployment-md-v0190-现场记录2026-08-25"></a>
<a id="documents-scout-mini-deployment-md-v0190-遥测修复验收"></a>
<a id="documents-scout-mini-deployment-md-v0191-重复重定位验收"></a>
<a id="documents-scout-mini-deployment-md-启动与停止"></a>
<a id="documents-scout-mini-deployment-md-安装与构建"></a>
<a id="documents-scout-mini-deployment-md-故障排查"></a>
<a id="documents-scout-mini-deployment-md-松灵-scout-mini-端侧部署说明"></a>
<a id="documents-scout-mini-deployment-md-设备与目录"></a>
<a id="documents-scout-mini-deployment-md-验证"></a>

<a id="documents-scout-mini-deployment-log-md"></a>
<a id="documents-scout-mini-deployment-log-md-ugv_001-文档已合并"></a>
<a id="documents-scout-mini-deployment-log-md-2026-08-24-epgeneral_map_stream-真机部署与验收"></a>
<a id="documents-scout-mini-deployment-log-md-2026-08-24-计划与环境盘点"></a>
<a id="documents-scout-mini-deployment-log-md-2026-08-25-v0190-遥测与活动地图增量部署"></a>
<a id="documents-scout-mini-deployment-log-md-2026-08-25-v0191-重复重定位增量部署"></a>
<a id="documents-scout-mini-deployment-log-md-2026-08-27-epgeneral_map_stream-v0110-增量部署"></a>
<a id="documents-scout-mini-deployment-log-md-2026-08-27-v040-源码增量"></a>
<a id="documents-scout-mini-deployment-log-md-2026-08-27-v041-执行会话修复部署"></a>
<a id="documents-scout-mini-deployment-log-md-2026-08-27-v042-tf-listener-修复部署"></a>
<a id="documents-scout-mini-deployment-log-md-2026-08-27-v043-航点可达性修复部署"></a>
<a id="documents-scout-mini-deployment-log-md-2026-08-28-epgeneral_map_stream-v0120-联合建图部署验证"></a>
<a id="documents-scout-mini-deployment-log-md-scout-mini-部署日志"></a>
<a id="documents-scout-mini-deployment-log-md-v0210-scout-task-adapter-deployment"></a>
<a id="documents-scout-mini-deployment-log-md-v0211-任务失败修复"></a>
<a id="documents-scout-mini-deployment-log-md-待处理的设备问题"></a>
<a id="documents-scout-mini-deployment-log-md-部署执行记录"></a>

原各 profile 的部署、验证与阶段材料已归入 [部署记录](DEPLOYMENT_RECORD.md)；历史命令只在其原日期背景下解释。
