<p align="center">
  <img src="https://raw.githubusercontent.com/AADCL/CCS_dev/9365e741fa6cb7236ccd317d197a299a796f9c65/icons/lab_logo/logo.png" alt="AADCL" width="96">
</p>

<h1 align="center">CCS_EDGE · 多异构智能体端侧功能包</h1>

<p align="center">设备接入 · 实时遥测 · 视频传输 · 联合建图 · 重定位 · 任务执行</p>

<p align="center">
  <img alt="兼容 CCS 0.25.0" src="https://img.shields.io/badge/CCS-0.25.0-1677ff">
  <img alt="ROS Noetic" src="https://img.shields.io/badge/ROS-Noetic-22314E">
  <img alt="Ubuntu 20.04" src="https://img.shields.io/badge/Ubuntu-20.04-E95420">
  <img alt="Python 3" src="https://img.shields.io/badge/Python-3-3776AB">
  <img alt="许可证 Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-blue">
</p>

CCS_EDGE 是 [CCS 地面站](https://github.com/AADCL/CCS_dev)配套的独立 ROS 端侧仓库，
为四足机器人、无人车和 Ground-Air 设备提供统一的通信、地图与任务接口。
通过 MQTT、UDP、SRT 通道与地面站协作，并接入设备已有的底盘、传感器和算法工作空间。

**快速入口：** [快速开始](#快速开始) · [设备与 profile](#设备与-profile) ·
[使用手册](documents/USER_MANUAL.md) · [接口与配置](documents/INTERFACE_REFERENCE.md) ·
[功能包](#功能包) · [文档导航](#文档导航)

## 核心能力

| 能力 | 功能 |
| --- | --- |
| 设备接入 | 共享设备身份与配置，对接 MQTT/MAVLink 和设备原生状态 |
| 实时遥测 | 通过 UDP 上报位姿、IMU、状态描述及子系统信息 |
| 视频传输 | 通过 SRT 传输低延迟视频，按设备 profile 选择相机与编码参数 |
| 地图与建图 | 地图传输、建图流程协调、点云预览与结果归档 |
| 重定位 | 地图切换、初始位姿接入、定位状态与 TF 上报 |
| 任务与控制 | 任务接收和执行协调、导航适配、控制权与急停处理 |

**仓库规模：9 个 ROS 包 · 4 类机型 · 7 套 profile。**
七个公共包直接放在仓库根目录，Go2 与 Ground-Air 专用包放在对应的 `devices/` 目录。
每台设备选择七个公共包及所需专用包；公共包内部已有的设备后端继续保留。

## 选择获取方式

| 方式 | 适合场景 | 操作入口 |
| --- | --- | --- |
| 独立 CCS_EDGE 仓库 | 端侧开发、部署资料维护、profile 定制 | 从本仓库根目录操作 |
| CCS_dev 子模块 | 地面站与端侧配套开发、固定版本构建 | 初始化后进入 `edge_side_pkg/` |
| 端侧配套 ZIP | 从地面站发行产物获取端侧源码与部署资料 | 解压后进入 `edge_side_pkg/` |

端侧 ZIP 完整分发九个包，仍需在设备上选择包并进行 catkin 构建。
地面站 Windows/Ubuntu 安装包不能代替 ROS 端侧部署。源码与 ZIP 使用相同的 profile 准备入口。

<a id="获取与使用"></a>

## 快速开始

### 1. 获取源码并选择 profile

在准备部署资料的计算机上执行，以下为 Bash 示例：

~~~bash
git clone https://github.com/AADCL/CCS_EDGE.git
cd CCS_EDGE

# 示例：为第三台 Go2 准备部署资料。
# 输出目录必须为空，且位于源码仓库之外。
PROFILE=go2_robot3
STAGING=$(mktemp -d)
python3 scripts/prepare_profile.py --profile "$PROFILE" --output "$STAGING"
~~~

该工具只生成 staging，不连接设备或启动 ROS 节点。输出包含：

| 路径 | 内容 |
| --- | --- |
| `src/` | 当前设备所需的完整公共包与专用包，已应用 profile 配置 |
| `deploy/<profile>/` | 所选配置、启动脚本、适配 launch 及部署辅助文件 |
| `staging-manifest.json` | 所选 profile、包清单与文件 SHA-256 |

> **包选择边界：** 不要将整个仓库递归放进 catkin `src/`。
> 使用 staging 中已选定的包，避免把其他机型的专用包和部署资料加入构建。

### 2. 在设备安装与构建

先按对应[机型指南](#设备与-profile)准备底盘、传感器和算法工作空间，
再把 staging 中的完整包及部署文件安装到设备 CCS 工作空间。
已有同名包时，先停止相关入口并备份旧包、配置和启动文件。

ROS 环境加载顺序为：

~~~text
ROS Noetic → 设备外部工作空间（underlay）→ CCS 工作空间
~~~

在设备上完成包安装并 source 正确 underlay 后执行：

~~~bash
cd /home/实际用户/ccs_edge_ws
rosdep install --from-paths src --ignore-src -r -y
catkin_make -j2 -DPYTHON_EXECUTABLE=/usr/bin/python3
source devel/setup.bash
rospack find epgeneral_device_config
~~~

继续按机型指南安装运行配置、辅助脚本、launch 或用户服务，然后核验输入、启动和日志。
完整依赖、各包操作、故障排查、升级与回滚见[使用手册](documents/USER_MANUAL.md)。

### 3. 确认配置修改位置

| 启动方式 | 实际读取位置 | 修改后的生效方式 |
| --- | --- | --- |
| 包级 launch 默认入口 | `epgeneral_device_config/config/` 中的包内配置 | 停止并重新启动对应节点 |
| 设备一键脚本 | CCS 工作空间的 `config/<profile>/`，由脚本显式传入 | 停止并重新启动对应入口 |
| 显式指定配置的单包调试 | launch 参数指定的配置文件 | 核验参数后重新启动 |

修改仓库中的 profile 原件后，还需安装到设备实际读取的位置。各包的配置覆盖方式不同，均无热重载；
`deployment.enabled` 等说明性字段不能代替实际启停开关。参数、launch 参数和 `CCS_*` 环境变量见[接口参考](documents/INTERFACE_REFERENCE.md)。

## 设备与 profile

| 机型 | 可选 profile | 构建包选择 | 部署资料 |
| --- | --- | --- | --- |
| Go2 | `go2_edu`、`go2_robot2`、`go2_robot3` | 七公共包；Robot2/3 另加 Go2 integration | [部署指南](documents/devices/go2/DEPLOYMENT_GUIDE.md) · [部署记录](documents/devices/go2/DEPLOYMENT_RECORD.md) |
| Scout Mini | `scout_mini` | 七公共包 | [部署指南](documents/devices/scout_mini/DEPLOYMENT_GUIDE.md) · [部署记录](documents/devices/scout_mini/DEPLOYMENT_RECORD.md) |
| Wheeltec R550P | `wheeltec_r550p`、`wheeltec_r550p_02` | 七公共包 | [部署指南](documents/devices/wheeltec_r550p/DEPLOYMENT_GUIDE.md) · [部署记录](documents/devices/wheeltec_r550p/DEPLOYMENT_RECORD.md) |
| Ground-Air AGV | `ground_air_agv` | 七公共包，另加 Ground-Air control | [部署指南](documents/devices/ground_air_agv/DEPLOYMENT_GUIDE.md) · [部署记录](documents/devices/ground_air_agv/DEPLOYMENT_RECORD.md) |

配置、部署脚本、适配 launch、补丁与校验文件统一位于 `devices/<机型>/profiles/<profile>/`。
每种机型保留一份部署指南和一份部署记录；指南描述当前流程，记录保留各设备的历史证据。

| 设备差异 | 使用说明 |
| --- | --- |
| Go2 legacy | `go2_edu` 一键脚本不启动任务包 |
| Go2 Robot2/Robot3 | 按就绪状态启动任务协调器，增加原生 Go2 工作空间依赖 |
| Wheeltec UGV_003 / UGV_004 | UGV_003 可启动 Gemini 视频；UGV_004 默认不启动视频，两者使用各自的导航适配入口 |
| Ground-Air | 保持手动启动与阶段互斥；外部 `ground_air_msgs` 服务定义须在设备上核验 |

## 功能包

包目录名与 ROS 包名分别列出；`roslaunch`、`rosrun` 使用 ROS 包名。各包独立维护版本。

| 包文档 / 目录 | ROS 包名 | 版本 | 职责 |
| --- | --- | --- | --- |
| [EPGeneral_device_config](EPGeneral_device_config/README.md) | `epgeneral_device_config` | 0.1.1 | 设备身份与共享配置 |
| [epgeneral_mqtav](epgeneral_mqtav/README.md) | `epgeneral_mqtav` | 0.4.1 | MQTT/MAVLink 通信与状态接入 |
| [EPGeneral_udp_telemetry](EPGeneral_udp_telemetry/README.md) | `epgeneral_udp_telemetry` | 0.3.1 | UDP 遥测与状态描述 |
| [EPGeneral_video_srt](EPGeneral_video_srt/README.md) | `epgeneral_video_srt` | 0.1.2 | 相机接入与 SRT 视频传输 |
| [EPGeneral_map_stream](EPGeneral_map_stream/README.md) | `epgeneral_map_stream` | 0.13.2 | 地图传输与建图流程 |
| [EPGeneral_relocalization](EPGeneral_relocalization/README.md) | `epgeneral_relocalization` | 0.4.0 | 重定位与定位状态上报 |
| [EPGeneral_task_control](EPGeneral_task_control/README.md) | `epgeneral_task_control` | 0.6.3 | 任务与导航执行协调 |
| [EPGeneral_go2_integration](devices/go2/EPGeneral_go2_integration/README.md) | `epgeneral_go2_integration` | 0.1.2 | Go2 原生控制、状态与流程适配 |
| [EPGeneral_ground_air_control](devices/ground_air_agv/EPGeneral_ground_air_control/README.md) | `epgeneral_ground_air_control` | 0.2.0 | Ground-Air 地面任务、控制权与急停 |

## 目录结构

~~~text
CCS_EDGE/
├── EPGeneral_device_config/          # 共享配置
├── epgeneral_mqtav/                  # MQTT/MAVLink
├── EPGeneral_udp_telemetry/          # UDP 遥测
├── EPGeneral_video_srt/              # SRT 视频
├── EPGeneral_map_stream/             # 地图与建图
├── EPGeneral_relocalization/         # 重定位
├── EPGeneral_task_control/           # 任务控制
├── devices/
│   ├── go2/                         # 专用包 + 三套 profile
│   ├── scout_mini/                  # 一套 profile
│   ├── wheeltec_r550p/              # 两套 profile
│   └── ground_air_agv/              # 专用包 + 一套 profile
├── documents/
│   ├── USER_MANUAL.md
│   ├── INTERFACE_REFERENCE.md
│   └── devices/<机型>/              # 部署指南 + 部署记录
├── scripts/                         # staging 与检查工具
├── tests/                           # 独立端侧检查
├── edge-layout.json                 # 包与 profile 选择规则
└── migration-manifest.json          # 来源哈希与目录映射
~~~

## 平台与运行要求

- 端侧基线：Ubuntu 20.04、ROS Noetic、系统 Python 3 与 catkin。
- 先准备设备底盘、相机、雷达、定位与导航等 underlay；各机型所需包见部署指南。
- 按 profile 核验设备身份、通信地址、话题、TF、地图路径及外部命令。
- 配置和日志目录需具备相应用户的读写权限；多设备同步任务需要统一授时。
- 地面站兼容基线为 CCS 0.25.0，地面站与各 ROS 包的版本分别维护。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [使用手册](documents/USER_MANUAL.md) | 从零部署、各包使用、启停、日志、排障、升级与回滚 |
| [接口与配置参考](documents/INTERFACE_REFERENCE.md) | 跨工作空间接入、话题/消息/服务/action/TF、配置字段、launch 参数与授时 |
| [设备部署资料](#设备与-profile) | 四类机型、七套 profile 的当前指南与历史记录 |
| [地面站接口总册](https://github.com/AADCL/CCS_dev/blob/dbe85904cdbae3d3b837f8816f29d1f030d7bd5a/docs/EDGE_DEVICE_INTERFACES.md) | 配套源码基线中的网络消息、通道与协议约束 |
| [布局清单](edge-layout.json) | 公共包、专用包及 profile 的机器可读选择规则 |
| [迁移清单](migration-manifest.json) | 来源提交、原文件哈希与新目录映射 |
| [迁移验证记录](validation-migration.json) | 已完成检查、审核修复与实机验证边界 |

## 开发与验证

安装测试依赖后，在仓库根目录执行独立端侧检查：

~~~bash
python3 -m pip install -r requirements-test.txt
python3 -m unittest discover -s tests -v
python3 scripts/check_packages.py
~~~

独立仓库测试不读取主项目的现场 `devices.json`、地图或任务。
历史部署记录和迁移检查不代表当前设备已重新通过实机验收。

### 与 CCS_dev 协同

CCS_dev 通过 `edge_side_pkg` 子模块固定本仓库提交：

~~~bash
git clone --recurse-submodules https://github.com/AADCL/CCS_dev.git

# 在已有的 CCS_dev 检出中初始化固定提交：
git submodule update --init --recursive
~~~

端侧升级应在主项目中显式更新子模块及源码锁，并提交对应变更；
打包期间不自动拉取端侧远程最新版本。迁移来源基线为
[CCS_dev dbe8590](https://github.com/AADCL/CCS_dev/tree/dbe85904cdbae3d3b837f8816f29d1f030d7bd5a)，
设备上的工作空间路径、ROS 接口及协议约定保持兼容。

---

CCS_EDGE 使用 [Apache License 2.0](LICENSE)。各功能包的独立版本和历史变更见包级 README 与 CHANGELOG。
