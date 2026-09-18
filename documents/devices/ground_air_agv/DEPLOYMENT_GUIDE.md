# ground_air_agv 部署指南

整理基线：2026-09-18，CCS_dev dbe85904cdbae3d3b837f8816f29d1f030d7bd5a。设备工作空间路径保持不变。

| profile | 设备 ID | 示例连接 | 工作空间 |
| --- | --- | --- | --- |
| ground_air_agv | AGV_001 | bitcq@192.168.50.130 | /home/bitcq/ccs_edge_ws |

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

## Ground-Air 首次集成与阶段互斥

source /opt/ros/noetic/setup.bash → /home/bitcq/catkin_ws/devel/setup.bash → CCS devel/setup.bash。额外构建 epgeneral_ground_air_control，依赖设备外部 ground_air_msgs；仓库只记录代码使用字段，不能假定完整服务定义。

~~~bash
rospack find ground_air_msgs
rosservice list
# 对实际服务逐个执行：
rosservice type /实际服务名
rossrv show "$(rosservice type /实际服务名)"
~~~

首次安装除八包、七份 YAML，还要安装 profile/launch、overrides/car_bringup、用户 ccs-edge-dev.service。按使用手册的 Ground-Air 首次安装章节，核验 rospack find car_bringup 是预期 /home/bitcq/catkin_ws/src/car_bringup 后，备份并安装 mapping_coordinate_transforms.launch 与 manual_mapping_control.launch；不得覆盖已有 manual_mapping.launch。服务文件中的 bitcq 绝对路径须与现场一致。

保持用户服务禁用自启动，通过 systemctl --user start ccs-edge-dev 手动启动，systemctl --user stop ccs-edge-dev 停止。不要运行历史 deploy_stage_manager_update.sh 代替当前首次安装，它处理旧 underlay 阶段管理器且可能启用服务。定位、建图、任务阶段与 TF 发布者必须互斥；任务协调器、适配器和急停桥接启动并不表示任务执行层一直运行。

核验 systemctl --user status ccs-edge-dev、journalctl --user -u ccs-edge-dev、工作空间 log/ground_air_agv 与 ~/.ros/ccs_edge_dev_ground_air_agv/log。输入缺失或外部服务不匹配时先停服务、检查 source 与 ROS_MASTER_URI，再比对配置，不用重复启动绕过阶段守卫。

<a id="documents-ground-air-agv-deployment-md"></a>
<a id="documents-ground-air-agv-deployment-md-agv_001-文档已合并"></a>
<a id="documents-ground-air-agv-deployment-md-一键启动组件"></a>
<a id="documents-ground-air-agv-deployment-md-建图与重定位响应"></a>
<a id="documents-ground-air-agv-deployment-md-服务管理"></a>
<a id="documents-ground-air-agv-deployment-md-构建与日志"></a>
<a id="documents-ground-air-agv-deployment-md-空地-agv-端侧部署说明"></a>
<a id="documents-ground-air-agv-deployment-md-设备与边界"></a>
<a id="documents-ground-air-agv-deployment-md-静态验收"></a>

<a id="documents-ground-air-agv-deployment-log-md"></a>
<a id="documents-ground-air-agv-deployment-log-md-agv_001-文档已合并"></a>
<a id="documents-ground-air-agv-deployment-log-md-2026-08-31-a8-mini-srt-视频部署"></a>
<a id="documents-ground-air-agv-deployment-log-md-2026-08-31-基础部署"></a>
<a id="documents-ground-air-agv-deployment-log-md-2026-08-31-通信服务纳入一键启动"></a>
<a id="documents-ground-air-agv-deployment-log-md-2026-09-05-手动启动与建图兼容修复"></a>
<a id="documents-ground-air-agv-deployment-log-md-空地-agv-部署日志"></a>

<a id="documents-ground-air-agv-mapping-deployment-md"></a>
<a id="documents-ground-air-agv-mapping-deployment-md-agv_001-文档已合并"></a>
<a id="documents-ground-air-agv-mapping-deployment-md-ground-air-agv-建图部署说明"></a>
<a id="documents-ground-air-agv-mapping-deployment-md-产物与日志"></a>
<a id="documents-ground-air-agv-mapping-deployment-md-回滚"></a>
<a id="documents-ground-air-agv-mapping-deployment-md-增量部署"></a>
<a id="documents-ground-air-agv-mapping-deployment-md-实时预览坐标系契约"></a>
<a id="documents-ground-air-agv-mapping-deployment-md-建图指令流程"></a>
<a id="documents-ground-air-agv-mapping-deployment-md-手动启动顺序与所有权"></a>
<a id="documents-ground-air-agv-mapping-deployment-md-适用范围"></a>
<a id="documents-ground-air-agv-mapping-deployment-md-静态验收"></a>

<a id="documents-ground-air-agv-mapping-deployment-log-md"></a>
<a id="documents-ground-air-agv-mapping-deployment-log-md-agv_001-文档已合并"></a>
<a id="documents-ground-air-agv-mapping-deployment-log-md-2026-09-01-epgeneral_map_stream-v0130-增量部署"></a>
<a id="documents-ground-air-agv-mapping-deployment-log-md-2026-09-02-fast-lio-后置坐标转换-launch-增量部署"></a>
<a id="documents-ground-air-agv-mapping-deployment-log-md-2026-09-02-stage-manager-后置启动与指控接入"></a>
<a id="documents-ground-air-agv-mapping-deployment-log-md-2026-09-02-tf-改为自启动常驻管理"></a>
<a id="documents-ground-air-agv-mapping-deployment-log-md-2026-09-02-坐标转换改为开机常驻"></a>
<a id="documents-ground-air-agv-mapping-deployment-log-md-2026-09-03-建图预览坐标系契约修复与端侧验收"></a>
<a id="documents-ground-air-agv-mapping-deployment-log-md-2026-09-03-静态-tf-改由自启动-launch-直接管理"></a>
<a id="documents-ground-air-agv-mapping-deployment-log-md-2026-09-05-guard-版本不匹配诊断与兼容修复"></a>
<a id="documents-ground-air-agv-mapping-deployment-log-md-ground-air-agv-建图部署日志"></a>

<a id="documents-ground-air-agv-relocalization-deployment-md"></a>
<a id="documents-ground-air-agv-relocalization-deployment-md-agv_001-文档已合并"></a>
<a id="documents-ground-air-agv-relocalization-deployment-md-ground-air-agv-重定位部署说明"></a>
<a id="documents-ground-air-agv-relocalization-deployment-md-tf-上报"></a>
<a id="documents-ground-air-agv-relocalization-deployment-md-回滚"></a>
<a id="documents-ground-air-agv-relocalization-deployment-md-增量验收"></a>
<a id="documents-ground-air-agv-relocalization-deployment-md-运行契约"></a>
<a id="documents-ground-air-agv-relocalization-deployment-md-部署边界"></a>

<a id="documents-ground-air-agv-relocalization-deployment-log-md"></a>
<a id="documents-ground-air-agv-relocalization-deployment-log-md-agv_001-文档已合并"></a>
<a id="documents-ground-air-agv-relocalization-deployment-log-md-2026-09-04-实施记录"></a>
<a id="documents-ground-air-agv-relocalization-deployment-log-md-2026-09-05-建图兼容回归修正"></a>
<a id="documents-ground-air-agv-relocalization-deployment-log-md-ground-air-agv-重定位部署日志"></a>
<a id="documents-ground-air-agv-relocalization-deployment-log-md-问题与修正"></a>
<a id="documents-ground-air-agv-relocalization-deployment-log-md-验收结果"></a>

<a id="documents-ground-air-agv-task-deployment-md"></a>
<a id="documents-ground-air-agv-task-deployment-md-agv_001-文档已合并"></a>
<a id="documents-ground-air-agv-task-deployment-md-ground-air-agv-地面任务部署"></a>

<a id="documents-ground-air-agv-task-deployment-log-md"></a>
<a id="documents-ground-air-agv-task-deployment-log-md-agv_001-文档已合并"></a>
<a id="documents-ground-air-agv-task-deployment-log-md-2026-09-08-本地故障修订尚未部署"></a>
<a id="documents-ground-air-agv-task-deployment-log-md-2026-09-08-连续两轮实车复验通过"></a>
<a id="documents-ground-air-agv-task-deployment-log-md-ground-air-agv-地面任务部署记录"></a>
<a id="documents-ground-air-agv-task-deployment-log-md-回滚"></a>
<a id="documents-ground-air-agv-task-deployment-log-md-待完成验收"></a>
<a id="documents-ground-air-agv-task-deployment-log-md-构建与增量测试"></a>
<a id="documents-ground-air-agv-task-deployment-log-md-部署结果"></a>
<a id="documents-ground-air-agv-task-deployment-log-md-静态验收"></a>

<a id="deploy-ground-air-agv-deployment-md"></a>
<a id="deploy-ground-air-agv-deployment-md-agv_001-文档已合并"></a>
<a id="deploy-ground-air-agv-deployment-md-ground-air-agv-ccs-edge-deployment"></a>

原各 profile 的部署、验证与阶段材料已归入 [部署记录](DEPLOYMENT_RECORD.md)；历史命令只在其原日期背景下解释。
