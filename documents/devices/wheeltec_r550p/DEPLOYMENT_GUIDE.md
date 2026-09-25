# Wheeltec R550P 部署指南：以 UGV_004 为模板

更新：2026-09-24。用户已确认 UGV_004 全部端侧测试完成。本文整理时只核对运行状态和导出安装模板，没有重复执行运动测试；实机当前日志确认时间偏差 -0.002 s、必需服务启动成功、RGB/深度30 FPS，定位状态为 localized。早期记录中的待验收描述是当时状态，不替代此次最终验收结论。

本页包含安装来源、环境制备、复制/构建命令、启动与外部接口、验收和回滚，不要求先阅读其他文档。适用的是 **Ubuntu 20.04.6/aarch64 + ROS Noetic + Wheeltec V5.1 + MID360 + Gemini 336L倒装**。同型号底盘仍须核对固件、原生软件、标定与网络；不承诺未知环境可无条件复制。

## 1. 选择模板和部署边界

| 项目 | 已验收模板值 | 换车时的要求 |
| --- | --- | --- |
| profile/身份 | wheeltec_r550p_02 / UGV_004 | profile作为V5.1模板名保留，ID必须唯一 |
| CCS路径 | /home/nrc15/ccs_edge_ws | 本机普通用户的ccs_edge_ws |
| 原生underlay | /home/nrc15/livox_fastlio | 已装且已编译的相同V5.1环境 |
| LAN | wlan0，192.168.50.123/24 | 分配唯一IP，脚本和YAML一起替换 |
| 平台/NTP | 192.168.50.101 | MQTT、UDP、地图、任务、NTP一起替换 |
| 雷达网络 | eth0=192.168.123.5/24，MID360=192.168.123.124 | 固定模板契约；不同IP或网卡须另行适配 |
| 底盘串口 | /dev/wheeltec_controller → ttyACM0 | 稳定udev别名、普通用户读写权限 |
| ROS master | http://127.0.0.1:11311 | 本机master，ROS_IP为本机LAN地址 |
| 相机 | Gemini 336L倒装，640×480/30 FPS RGBD | 型号、USB、安装标定一致 |

CCS安装、修改和构建仅在CCS工作空间；不改原生源码、launch、标定、二进制，不重编译外部工作空间。系统依赖、网络、udev和 `/etc/systemd/timesyncd.conf.d/ccs.conf` 属于设备镜像/管理员制备项，不能当作CCS目录内修改。

**运行数据与代码修改须区分：**重定位FAST-LIO经bubblewrap将原生固定Log/PCD目录绑定至CCS的 `run/native-fastlio-{log,pcd}`。当前建图链仍使用原生 `<native>/maps`，且建图FAST-LIO不走该重定位sandbox；原样复刻保留此业务数据契约。若现场禁止运行期对外部工作空间的任何写入，当前建图流程不满足该限制，须先在CCS内另行适配并验收，不能仅改一个YAML就宣称隔离完成。本次指南整理没有修改这些算法或外部目录。

UGV_003的 `wheeltec_r550p` 与本V5.1模板不可混用；其控制权、导航和速度链说明保留在本文末尾。后面的UGV_003历史补丁命令不属于UGV_004安装步骤。

## 2. 固定交付来源和版本

已从最终实机导出源码模板，逐项验证189个CCS文件：

- 文件：`/home/nrc15/ccs_edge_ws/backups/ugv004-template-20260924/ugv004-ccs-template-20260924.tar.gz`。
- SHA-256：`71c75670c29727b2609c7a8f9e64711a6320293910fa73bc349770beadf8149d`。
- 内容：七个实体源码包、实际 `config/wheeltec_r550p_02`、scripts、launch、根启动脚本、timesyncd模板，以及 `evidence/template-manifest.json`、`native-manifest.json`、`system-packages.txt`。
- 不含密码、地图、任务、状态、日志、build/devel或原生源码；外部指纹清单有1019项，**不是原生依赖安装包**。
- 仓库修复参考提交：`73cd5b0490b24582d53982390cde4f0178f194f6`。实机保留旧协议包/默认配置，不能只checkout该提交就当作完整实机快照。

| 源目录 / ROS包 | 锁定版本 |
| --- | --- |
| EPGeneral_device_config / epgeneral_device_config | 0.1.1 |
| epgeneral_mqtav / epgeneral_mqtav | 0.4.1 |
| EPGeneral_udp_telemetry / epgeneral_udp_telemetry | 0.3.1 |
| EPGeneral_video_srt / epgeneral_video_srt | 0.1.2 |
| EPGeneral_map_stream / epgeneral_map_stream | 0.13.2 |
| EPGeneral_relocalization / epgeneral_relocalization | 0.6.0 |
| EPGeneral_task_control / epgeneral_task_control | 0.6.4 |

MQTT0.4.1、UDP0.3.1和包内实际配置必须成套使用，不混用main的新schema。视频0.1.1不处理rotation_degrees；必须源码和二进制一起更新至0.1.2。重定位直接适配现有包，独立可执行文件/库为 `ccs_wheeltec_localizer` / `ccs_wheeltec_ndt`，不增加ROS功能包；第三方许可证、NOTICE及来源哈希随源码保留。

在部署电脑获取并校验，再传目标机（使用SSH交互/密钥，不记录口令）：

~~~bash
scp nrc15@192.168.50.123:/home/nrc15/ccs_edge_ws/backups/ugv004-template-20260924/ugv004-ccs-template-20260924.tar.gz .
printf '%s  %s\n' 71c75670c29727b2609c7a8f9e64711a6320293910fa73bc349770beadf8149d ugv004-ccs-template-20260924.tar.gz | sha256sum -c -
# 替换下面的用户/IP。
ssh TARGET_USER@TARGET_IP 'mkdir -p "$HOME/ccs_edge_ws/backups"'
scp ugv004-ccs-template-20260924.tar.gz TARGET_USER@TARGET_IP:ccs_edge_ws/backups/
~~~

将模板和本指南一并存入部署交付存储，不长期依赖UGV_004在线。本次部署电脑副本在 `CCS_dev/artifacts/ugv004_fix_20260924/`。模板丢失应重新从已验收基线封存并更新哈希，不用任意旧备份补齐。仓库 `scripts/prepare_profile.py` 只生成staging，会选择当前仓库包并覆盖device_config默认配置，不安装、不构建、不启动，不能代替上述实机版本组合。

## 3. 环境、外部依赖、标定和授时

Noetic → 原生underlay → CCS，始终按此顺序source；最后一层决定ROS包与Python导入优先级。不要让 `.bashrc` 额外source其他设备工作空间。读原生Python前设置 `PYTHONDONTWRITEBYTECODE=1` 避免写pyc。七个epgeneral包最终必须解析到CCS实体源码，不能软链接到外部包。

| 外部组件 | 必需入口/版本 | 配合方式 |
| --- | --- | --- |
| turn_on_wheeltec_robot | launch/include/base_serial.launch | 根入口仅串口底盘，odom_frame_id=wheel_odom |
| livox_ros_driver2 | 1.0.0，launch_ROS1/msg_MID360.launch | 原始CustomMsg雷达/IMU |
| orbbec_camera | 2.9.3，gemini_330_series.launch | 直接RGBD，不调用YOLO |
| fast_lio、wheeltec_system_bringup | V5.1；fastlio_local_odom.launch.xml、fastlio_mapping_wheeltec.launch.xml | 业务阶段启动，不与根入口重复 |
| fast_lio_localization | map_loader可执行文件、AllowedRegions已生成消息 | 只复用地图加载/消息，不拉起原生全局定位器 |
| wheeltec_tf_manager、wheeltec_pose_adapter | tf_manager.launch.xml、pose_adapter.launch.xml | 标定与FAST-LIO位姿转换 |
| wheeltec_cloud_adapter | cloud_adapter.launch.xml及include | 定位和地形点云使用不同节点名 |
| wheeltec_pointcloud_mapper、wheeltec_map_tools | mapper0.1.0、pointcloud_mapper.launch.xml、可执行scripts/finalize_map.py | 建图与PCD/PGM/YAML导出 |
| wheeltec_terrain_filter、wheeltec_navigation | include下terrain filter launch及costmap/TEB/global planner YAML | 局部障碍与导航参数 |
| map_server、move_base及规划/代价地图插件 | Noetic中可加载 | CCS二维导航入口自行组装，不能调用原生整车导航重复拉驱动 |

原生大量包版本为0.0.0，包名/版本不足以复刻，须检查模板中的源码/库指纹和launch契约。外部目录由设备镜像提供；本模板不负责重新安装Orbbec/Livox SDK、Patchwork++等厂商依赖。

UGV_004安装标定：`base_link <- body` 为 `(0.10,0,0.15)` m、pitch=+20°，四元数 `(0,0.17364817766693033,0,0.984807753012208)`。原生extrinsics.yaml的publish_inverse=true只控制实际TF方向，不能再反转profile中的矩阵。wheeltec_geometry.yaml是odom→camera_init的唯一配置源。相机安装TF平移 `(0.16,0,0.08)` m、roll=π。不同安装角度须实测并建立新基线，不能照抄或加单位TF掩盖。

系统依赖由管理员制备，缺失时补齐，不能由CCS安装器偷偷升级原生算法：

~~~bash
sudo apt-get update
sudo apt-get install -y build-essential cmake python3-catkin-pkg python3-rospkg \
  python3-yaml python3-msgpack python3-paho-mqtt python3-numpy python3-rosdep \
  bubblewrap util-linux libpcl-dev libomp-dev libopencv-dev \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev gstreamer1.0-tools \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly gstreamer1.0-libav python3-gi gir1.2-gstreamer-1.0 \
  ros-noetic-pcl-ros ros-noetic-pcl-conversions ros-noetic-tf-conversions \
  ros-noetic-cv-bridge ros-noetic-image-transport ros-noetic-map-server \
  ros-noetic-move-base ros-noetic-teb-local-planner
~~~

这只是依赖补齐列表，不是重建厂商镜像脚本。实机PCL1.10.0、GStreamer1.16.x、bubblewrap0.4.0、paho-mqtt1.5.0、msgpack0.6.2；准确apt版本见system-packages.txt，不全局pip升级ROS/MQTT依赖。先核对 `ip -o -4 addr show dev wlan0/eth0`（分别执行）和 `ping -I eth0 -c 1 192.168.123.124`，串口/相机权限和原生自动启动服务也须检查。

| 通道 | 方向及端口 |
| --- | --- |
| NTP、MQTT | 设备→平台UDP123、TCP1883 |
| 遥测 | 设备→平台UDP14560 |
| 建图控制/数据 | 平台→设备UDP14561；设备→平台UDP14562 |
| 任务控制/反馈 | 平台→设备UDP14563；设备→平台UDP14564 |
| 重定位控制/反馈 | 平台→设备UDP14565；设备→平台UDP14566 |
| 地图HTTP | 平台→设备TCP14600；下载还须放通平台返回的实际URL |
| SRT | 平台caller→设备listener UDP9000 |

地面站先启用NTP并放通UDP123。第4节展开模板后，安装已替换站点地址的授时配置：

~~~bash
sudo install -d /etc/systemd/timesyncd.conf.d
sudo install -m 0644 "$HOME/ccs_edge_ws/timesyncd-ccs.conf" /etc/systemd/timesyncd.conf.d/ccs.conf
sudo systemctl enable --now systemd-timesyncd
sudo systemctl restart systemd-timesyncd
timedatectl show -p NTP -p NTPSynchronized
timedatectl show-timesync -p ServerName -p ServerAddress
~~~

仅restart不保证开机启用。服务负责校时，ccs_sntp_sync.py负责验证，45秒内偏差≤0.5秒才允许启动。CCS_NTP_SERVER只改变验证目标，必须同时改系统NTP源；ping通、服务active、日期看起来正确都不能代替实测偏差。--check不自行修改时钟。

## 4. 可复制的首次安装脚本

将下面块保存为install_ugv004_template.sh，在目标机以普通用户运行 `bash install_ugv004_template.sh`。先修改四类参数：设备ID、设备IP、站点IP、两工作空间路径。脚本不安装系统依赖、不启动底盘、不修改underlay；已有部署时拒绝覆盖，升级见第9节。只改参数不能适配V6、不同网卡/雷达或标定。

~~~bash
#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
export CCS_INSTALL_WS="$HOME/ccs_edge_ws"
export CCS_INSTALL_NATIVE="$HOME/livox_fastlio"
export CCS_INSTALL_DEVICE_ID=UGV_004  # 新车例如UGV_005，不能与在线设备重复
export CCS_INSTALL_DEVICE_IP=192.168.50.123
export CCS_INSTALL_STATION_IP=192.168.50.101
ARCHIVE="$CCS_INSTALL_WS/backups/ugv004-ccs-template-20260924.tar.gz"
EXPECTED=71c75670c29727b2609c7a8f9e64711a6320293910fa73bc349770beadf8149d
[[ $(id -u) -ne 0 ]] || { echo '请使用目标普通用户'; exit 1; }
[[ -r "$CCS_INSTALL_NATIVE/devel/setup.bash" ]] || { echo '缺少原生underlay'; exit 1; }
printf '%s  %s\n' "$EXPECTED" "$ARCHIVE" | sha256sum -c -
export CCS_INSTALL_STAGE
CCS_INSTALL_STAGE=$(mktemp -d "$CCS_INSTALL_WS/backups/stage.XXXXXXXX")
tar --no-same-owner -xzf "$ARCHIVE" -C "$CCS_INSTALL_STAGE"
python3 - <<'PY'
import hashlib,ipaddress,json,os,re
from pathlib import Path
s=Path(os.environ['CCS_INSTALL_STAGE'])
w=Path(os.environ['CCS_INSTALL_WS']).resolve()
n=Path(os.environ['CCS_INSTALL_NATIVE']).resolve()
identity=os.environ['CCS_INSTALL_DEVICE_ID']
assert re.fullmatch(r'UGV_[0-9]+',identity) and identity!='UGV_003'
for key in ['CCS_INSTALL_DEVICE_IP','CCS_INSTALL_STATION_IP']:
    ipaddress.IPv4Address(os.environ[key])
assert w.name=='ccs_edge_ws' and n!=w and w not in n.parents and n not in w.parents
for name in ['src','config','scripts','launch','start_ccs_edge_dev.sh','build','devel']:
    assert not (w/name).exists(), '已有部署，先按第9节备份隔离：'+str(w/name)
m=json.loads((s/'evidence/template-manifest.json').read_text())
for rel,digest in m['sha256'].items():
    assert hashlib.sha256((s/rel).read_bytes()).hexdigest()==digest,rel
external=json.loads((s/'evidence/native-manifest.json').read_text())
bad=[rel for rel,digest in external.items() if not (n/rel).is_file()
     or hashlib.sha256((n/rel).read_bytes()).hexdigest()!=digest]
(w/'backups/native-baseline-differences.json').write_text(json.dumps(bad,indent=2))
assert not bad, '原生基线不同，先审查backups/native-baseline-differences.json；禁止自动略过或打补丁'
print('源码/原生基线校验通过')
PY
for name in src config scripts launch; do cp -a "$CCS_INSTALL_STAGE/$name" "$CCS_INSTALL_WS/"; done
cp -a "$CCS_INSTALL_STAGE/start_ccs_edge_dev.sh" "$CCS_INSTALL_STAGE/timesyncd-ccs.conf" "$CCS_INSTALL_WS/"
python3 - <<'PY'
import hashlib,json,os
from pathlib import Path
w=Path(os.environ['CCS_INSTALL_WS']); n=Path(os.environ['CCS_INSTALL_NATIVE'])
pairs=[('/home/nrc15/ccs_edge_ws',str(w)),('/home/nrc15/livox_fastlio',str(n)),
       ('~/ccs_edge_ws',str(w)),
       ('UGV_004',os.environ['CCS_INSTALL_DEVICE_ID']),
       ('192.168.50.123',os.environ['CCS_INSTALL_DEVICE_IP']),
       ('192.168.50.101',os.environ['CCS_INSTALL_STATION_IP'])]
paths=[w/'start_ccs_edge_dev.sh',w/'timesyncd-ccs.conf']
for name in ['src','config','scripts','launch']:
    paths.extend(p for p in (w/name).rglob('*') if p.is_file())
for p in paths:
    data=p.read_text(encoding='utf-8')
    for old,new in pairs: data=data.replace(old,new)
    p.write_text(data.replace('\r\n','\n'),encoding='utf-8')
    if p.suffix=='.sh' or (p.suffix=='.py' and data.startswith('#!')):
        p.chmod(p.stat().st_mode | 0o111)
manifest={str(p.relative_to(w)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
(w/'backups/installed-template-sha256.json').write_text(json.dumps(manifest,indent=2))
PY
# ROS setup可能读取未定义变量，source前关闭nounset。
set +u
source /opt/ros/noetic/setup.bash
source "$CCS_INSTALL_NATIVE/devel/setup.bash" --extend
cd "$CCS_INSTALL_WS"
catkin_make -j2 -l2 -DCMAKE_BUILD_TYPE=Release \
  -DPYTHON_EXECUTABLE=/usr/bin/python3 -DCCS_BUILD_WHEELTEC_LOCALIZER=ON \
  2>&1 | tee backups/install-build.log
source devel/setup.bash --extend
for package in epgeneral_device_config epgeneral_mqtav epgeneral_udp_telemetry \
 epgeneral_video_srt epgeneral_map_stream epgeneral_relocalization epgeneral_task_control; do
    rospack find "$package"
done
test -x devel/lib/epgeneral_relocalization/ccs_wheeltec_localizer
test -x devel/lib/epgeneral_video_srt/epgeneral_video_srt_node
printf '%s\n' '构建完成；安装授时配置后执行 ./start_ccs_edge_dev.sh --check，再启动。'
~~~

本文脚本已在UGV_004的CCS备份目录中试展开：189项哈希、原生指纹、新身份UGV_099/IP替换及已有部署拒绝覆盖均通过；Bash语法和嵌入Python语法检查通过。试展开没有重新构建或启动ROS，不能当作新设备的全新安装验收。

默认严格核对原生指纹；用户名/构建路径差异也可能改变二进制，须逐项审查并建立验收后的新模板，不能关闭全部检查。新设备只修改device.yaml不够：根脚本硬编码的ID、诊断话题、预检常量、所有YAML地址/路径必须一起替换。以上脚本为此同步替换模板文本并保存本机指纹。

可选定位目标默认OFF，遗漏 `CCS_BUILD_WHEELTEC_LOCALIZER=ON` 可能只装好Python节点而缺C++程序。可选依赖由CMake分支引入，普通rosdep不替代原生fast_lio_localization消息生成。只在CCS运行catkin_make，`-j2 -l2`限制内存压力。不要复制跨机器build/devel，不只改package.xml伪造二进制版本。

## 5. 一键启动的设计与使用

推荐唯一入口为CCS根start_ccs_edge_dev.sh；组合bringup.launch不具有同等锁、所有权、出图监督和停止逻辑。

1. 加载环境，设置ROS_HOME于CCS；运行模式取得run/managed/startup.lock拒绝重复启动。
2. 预检七包真实路径、YAML解析器、消息、外部launch/可执行文件、二维costmap插件、身份/地图路径/标定、端口、串口、网卡、雷达和授时。
3. 检查冲突的底盘、雷达、FAST-LIO、全局定位器、move_base；不擅自杀外部实例。可复用master，仅停止自有master。
4. setsid roslaunch拉起串口与雷达，确认新鲜/odom、/imu、/PowerVoltage、/livox/lidar、/livox/imu；发零速并确认轮速为零。
5. 依次启动MQTT、UDP、建图管理、重定位管理、任务控制及适配器；保存PID/独立输出，检查节点实际注册。根入口不提前启动全部算法。
6. 最后启动可选相机监督，出图合格后开SRT；失败仅视频降级，无限重试不属于正常策略。
7. 循环检查进程父PID/组/会话所有权与必需ROS节点，连续失败统一退出，不仅检查PID存活。
8. SIGINT/TERM/退出统一清理：相机→任务取消导航→零速和轮速确认→反序业务/驱动→自有master。禁止pkill ros/killall；不误停外部相机。

~~~bash
cd "$HOME/ccs_edge_ws"
./start_ccs_edge_dev.sh --check
./start_ccs_edge_dev.sh
~~~

--check/--preflight不启动ROS节点，但会实际检测网络/NTP并建立CCS ROS_HOME；通过不等于相机已出图、NDT已定位。先前台验收再决定会话/服务托管，模板没有安装CCS开机服务，不要叠加另一套无限重启supervisor。

| CCS相对路径 | 用途 |
| --- | --- |
| config/wheeltec_r550p_02/*.yaml | 根脚本显式读取的配置；包内默认配置不替代它 |
| scripts/ccs_wheeltec_preflight.py | 配置、包、消息、launch契约 |
| scripts/ccs_sntp_sync.py | 偏差验证，不能校时 |
| scripts/ccs_wheeltec_readiness.py | 输入新鲜、实测零速 |
| scripts/ccs_camera_supervisor.py | 可选RGBD/SRT生命周期 |
| run/managed | PID/锁；停机时核对命令防止PID重用 |
| logs/latest | 当前运行的startup/base/mqtav/udp_telemetry/map_stream/relocalization/task_control/camera_supervisor/camera/video/ros日志 |
| logs/navigation/navigation-<map_id>.log | 导航启动输出 |
| maps/download、run/state/relocalization.json、mission | 地图、定位状态、任务，不给新车复制旧成功状态/任务 |

## 6. CCS与原生功能包的协作规则

底盘/雷达只启动一次，根base launch不include原生整车bringup。/odom用于底盘原始状态，/fastlio_odom用于定位/导航，不通过重命名互相冒充；idle无FAST-LIO是正常的。

重定位阶段：FAST-LIO本地里程计→安装/几何TF→pose/cloud adapter→外部map_loader和CCS localizer→/map_2d地图服务器。同一时刻仅一个全局定位器。`map → odom → base_link` 表示连通的完整链，中间可有camera_init/body，不要求odom直接连接base_link。

初始位姿必须来自当前地图真实位置/朝向，NDT收敛、fitness≤2.0、位移跳变≤1m、角度跳变约30°、连续两个新点云帧通过后才成功；静止可确认。默认原点失败不能用放宽阈值/伪造单位TF解决。成功后持续广播有效map→odom，并检查新鲜/ccs/localization_valid和TF链。

可信区域不是首次定位/导航前置条件。无区域/清空区域保留接受结果及里程计推算，只暂停后续自动NDT修正。定位后平台下发XML；支持端 trusted_regions.apply_to_ndt=true，桥接校验地图/设备/会话/版本/map坐标系/多边形，经/ndt_gate/set_regions下发AllowedRegions；消费者在/ndt_gate/regions回显实际集合和令牌后才报成功，/ndt_gate/status提供算法状态。传输失败保留原有效区域和定位状态，切地图清除旧区域。运维不绕过桥接手工写区域话题。

导航只在任务准备时拉起。task_control YAML、预检与代码一致使用 `epgeneral_task_control/wheeltec_ccs_2d_navigation_v51.launch`。该入口加载二维地图、实时地形障碍、TEB，不重复启动传感器/定位，不要求额外terrain地图文件；全局插件为StaticLayer+InflationLayer，保留局部障碍检查。输入/fastlio_odom，输出/cmd_vel。

各消费者共享maps/download/<map_id>下public_map.pcd、map.pgm、map.yaml，以及run/state/relocalization.json；map.yaml的image能解析到对应PGM。UDP pgm_mapping、重定位storage和任务adapter的路径必须一致。准备保留25秒超时，先定位健康/TF再action；preparation_retry_on_failure=false保存失败、原因和日志，查询/迟到反馈不覆盖为空received，仅新完整任务重新下发开启准备。

建图沿用managed_finalize和原生mapper/finalize，native/maps的数据写入边界见第1节。不要把原生一键整车命令当成某个CCS阶段的启动命令，否则很容易出现重复驱动、双TF和不同map源。

## 7. RGB启动与180°旋转

正确驱动命令如下，仅供停止自有相机后的单独诊断；根脚本已调用它，运行时不重复执行：

~~~bash
roslaunch orbbec_camera gemini_330_series.launch \
  camera_name:=camera enable_color:=true enable_depth:=true \
  color_width:=640 color_height:=480 color_fps:=30 color_rotation:=0 \
  depth_width:=640 depth_height:=480 depth_fps:=30 depth_rotation:=0 \
  depth_registration:=true align_mode:=SW align_target_stream:=COLOR \
  enable_frame_sync:=true enable_point_cloud:=false enable_colored_point_cloud:=false \
  enable_left_ir:=false enable_right_ir:=false enable_accel:=false enable_gyro:=false \
  enable_image_transport_plugins:=false
~~~

安装TF处理几何，视频旋转处理观看方向：驱动RGB/深度rotation=0，SRT rotation_degrees=180，不双重翻转。视频订阅/camera/color/image_raw，640×480/30 FPS、2500kbps、UDP9000 listener、120ms latency。摄像头已经安装驱动，不意味着CCS视频二进制支持旋转。

就绪使用采集时间戳算帧率：至少2秒实际接收窗口、≥30帧、采集跨度≥1.5秒、帧年龄≤2秒、20–40FPS窗口，最多等30秒。启动缓存突发会让半秒回调抵达测速错误得到49.8FPS并误杀相机，不能再使用旧判定。复用外部相机也要检查新鲜尺寸/帧率，停止时保留外部所有权。外部视频节点/端口占用时不抢占。

接收端真正拉流核对，不只看参数：

~~~bash
ffprobe -v error -rw_timeout 15000000 -select_streams v:0 \
  -show_entries stream=codec_name,width,height,r_frame_rate -of json \
  'srt://192.168.50.123:9000?mode=caller&latency=120000'
ffplay 'srt://192.168.50.123:9000?mode=caller&latency=120000'
~~~

换车替换URL；关闭其他接收端避免单连接占用。实测60.07秒RGB1799帧、深度1800帧，均29.96FPS，H.264 640×480/30FPS；原RGB旋转180°后与解码图平均像素差15.18，未旋转76.47，证明补偿真实生效。

## 8. 逐机验收与故障对照

每个稳定状态观察至少60秒，保存模板/配置哈希、构建输出、版本、原生差异和日志目录。新车必须独立验收，不能借用模板机通过结论。

1. 预检、必需节点、输入、NTP偏差通过，重复启动被拒绝。
2. RGBD新鲜、SRT实际解码且180°正确；相机故障时必需业务仍在。外部复用和停止所有权单独验证。
3. 正确地图/初始位姿，无可信区域完成初始定位，健康持续且TF无陈旧/断链，静止确认有效。
4. 平台下发完整轨迹并PREPARE达到ready，查action和导航日志；静止安装验收不发SCHEDULE或move_base目标。
5. 定位后区域应用/替换/清空，消费者确认，再次PREPARE正常；错地图/旧会话拒绝但不清除定位成功。
6. 准备失败保持具体原因，周期查询不退回received；新任务重新下发可恢复准备。
7. Ctrl+C后取消导航、零速、自有进程清理，外部master/相机不误停。现场运动测试另行记录。

只读辅助命令（先source CCS）：

~~~bash
python3 "$HOME/ccs_edge_ws/scripts/ccs_wheeltec_readiness.py" inputs --timeout 30
rosnode list
rostopic info /cmd_vel
rostopic echo -n 1 /ccs/localization_valid
# 完成定位后观察；静态TF的0时间戳不能机械判陈旧。
timeout 10 rosrun tf tf_echo map base_link
rostopic info /move_base/status
timeout 60 rostopic hz /camera/color/image_raw
~~~

timeout退出124可表示观察窗口结束，仍需判断期间输出；action话题存在不等于业务ready。相机启动帧率以监督程序采集时间戳判定为准。

| 故障 | 根因检查与处理 |
| --- | --- |
| 时间未同步 | 查平台UDP123、timesyncd源/自启和真实偏差，不只看active |
| new node registered with same name | 查其他终端/厂商自启动/节点所有者，停止冲突入口，不跨工作空间乱杀 |
| 缺ccs_wheeltec_localizer | 可选编译开关ON，CCS内重新构建 |
| NDT不成功/等待区域 | 查是否旧原生定位器、真实初始位姿、fitness/输入新鲜；首次不依赖区域 |
| move_base超时 | 查navigation日志、健康、TF、地图/插件，修根因后重新下发，不延长超时掩盖 |
| 驱动30FPS却被停 | 使用已修复时间戳窗口，移除旧半秒回调测频脚本 |
| 串流倒置 | 查实际0.1.2二进制与rotation=180，驱动保持0 |
| YAML报错/遥测缺失 | 查包版本、schema与真实import路径，整套恢复模板，不只替换YAML |
| bwrap失败 | 查namespace权限、绑定目标和编译固定路径，不回退直接写原生源码目录 |

## 9. 升级、回滚与自动安装约定

升级先停止当前根入口，核对PID/命令及退出状态，只停止其拥有的进程。停止后备份CCS七包/config/scripts/launch/根脚本/timesyncd模板/build/devel，保存哈希：

~~~bash
cd "$HOME/ccs_edge_ws"
BACKUP="$PWD/backups/upgrade-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
tar -czf "$BACKUP/ccs-code-build.tar.gz" src config scripts launch start_ccs_edge_dev.sh timesyncd-ccs.conf build devel
sha256sum "$BACKUP/ccs-code-build.tar.gz" > "$BACKUP/ccs-code-build.tar.gz.sha256"
~~~

将旧代码/构建目录移入该CCS备份目录隔离，保留maps/mission/run业务数据，再走首次安装。不要叠加复制遗留旧模块/so。失败先停新入口，把新文件按部署清单移入CCS隔离目录；校验备份，在原路径恢复整套旧代码和匹配build/devel，再预检。不同机器/路径只恢复源码并重建。数据另行备份，旧地图/任务/成功状态不复制给新车；系统授时如被改变单独备份恢复，原生目录不作为回滚对象。

历史before.tar.gz、before-camera-fix-1438.tar.gz是故障回滚旧状态，不是最终模板。未来一键安装固定为：校验归档→核对镜像/契约→拒绝覆盖→替换参数/记录指纹→CCS构建→预检→明确启动/验收。分别报告安装、启动、定位和导航ready，不吞错、不同步时不启动、不自动修改原生代码、不自动发运动任务。

---

## UGV_003 保留说明（不属于上述安装流程）

UGV_003 当前使用 V6 原生集成包 `epgeneral_wheeltec_integration`，保留控制权、急停、受保护速度链和 Gemini 336L/SRT。2026-09-24 已按 UGV_004 实机入口改用 Bash 直接管理 `setsid roslaunch`、PID 数组及 trap，删除 Python 启动监控；不替换其 V6 导航为 UGV_004 的 V5.1 二维导航。`CCS_ENABLE_VIDEO=0` 可关闭本次视频。当前细节、对比、验证及回滚见 [UGV_003 Bash 启动说明](../../../devices/wheeltec_r550p/profiles/wheeltec_r550p/UGV_003_BASH_STARTUP.md)。
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
