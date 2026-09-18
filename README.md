# CCS_EDGE 端侧功能包

CCS_EDGE 是 [CCS_dev](https://github.com/AADCL/CCS_dev/tree/dbe85904cdbae3d3b837f8816f29d1f030d7bd5a) 的独立 ROS Noetic 端侧仓库。兼容基线为 CCS 0.25.0；此次只迁移目录、部署资料和测试，产品与 ROS 包版本不变。源码来源及本地 UGV_004 增量见 [迁移清单](migration-manifest.json)。Apache-2.0 许可证保持原仓库历史。

## 功能包

| 路径 | ROS 包名 | 版本 |
| --- | --- | --- |
| [EPGeneral_device_config](EPGeneral_device_config/README.md) | epgeneral_device_config | 0.1.1 |
| [epgeneral_mqtav](epgeneral_mqtav/README.md) | epgeneral_mqtav | 0.4.1 |
| [EPGeneral_udp_telemetry](EPGeneral_udp_telemetry/README.md) | epgeneral_udp_telemetry | 0.3.1 |
| [EPGeneral_video_srt](EPGeneral_video_srt/README.md) | epgeneral_video_srt | 0.1.2 |
| [EPGeneral_map_stream](EPGeneral_map_stream/README.md) | epgeneral_map_stream | 0.13.2 |
| [EPGeneral_relocalization](EPGeneral_relocalization/README.md) | epgeneral_relocalization | 0.4.0 |
| [EPGeneral_task_control](EPGeneral_task_control/README.md) | epgeneral_task_control | 0.6.3 |
| [EPGeneral_go2_integration](devices/go2/EPGeneral_go2_integration/README.md) | epgeneral_go2_integration | 0.1.2 |
| [EPGeneral_ground_air_control](devices/ground_air_agv/EPGeneral_ground_air_control/README.md) | epgeneral_ground_air_control | 0.2.0 |

前七包依次提供共享配置、MQTT/MAVLink 通信、UDP 遥测、SRT 视频、地图传输/建图、重定位与任务控制。Go2 专用包对接原生控制和状态，Ground-Air 专用包协调地面任务、控制权和急停。公共包内已有设备后端保持原位置及接口。

## 设备与 profile

| 机型 | profiles | 专用包 | 部署资料 |
| --- | --- | --- | --- |
| Go2 | go2_edu、go2_robot2、go2_robot3 | Robot2/3 增加 EPGeneral_go2_integration | [指南](documents/devices/go2/DEPLOYMENT_GUIDE.md) · [记录](documents/devices/go2/DEPLOYMENT_RECORD.md) |
| Scout Mini | scout_mini | 无 | [指南](documents/devices/scout_mini/DEPLOYMENT_GUIDE.md) · [记录](documents/devices/scout_mini/DEPLOYMENT_RECORD.md) |
| Wheeltec R550P | wheeltec_r550p、wheeltec_r550p_02 | 无 | [指南](documents/devices/wheeltec_r550p/DEPLOYMENT_GUIDE.md) · [记录](documents/devices/wheeltec_r550p/DEPLOYMENT_RECORD.md) |
| Ground-Air AGV | ground_air_agv | EPGeneral_ground_air_control | [指南](documents/devices/ground_air_agv/DEPLOYMENT_GUIDE.md) · [记录](documents/devices/ground_air_agv/DEPLOYMENT_RECORD.md) |

七个公共包位于根目录；专用包位于 devices/机型/；配置、脚本、launch 和补丁位于 devices/机型/profiles/profile/。九包完整分发，但每台设备只构建七个公共包及所需专用包。不要将整个仓库递归放进 catkin src。

## 获取与使用

~~~bash
git clone https://github.com/AADCL/CCS_EDGE.git
cd CCS_EDGE
# 在新建的空临时目录准备指定设备，不连接设备、不启动节点。
python3 scripts/prepare_profile.py --profile go2_robot3 --output /tmp/ccs-go2-stage
~~~

在 Ubuntu 20.04 / ROS Noetic 设备上准备外部底盘、传感器和算法工作空间，按 Noetic → 设备 underlay → CCS 顺序 source。把 staging/src 中选定的完整包安装到 CCS 工作空间 src，运行 rosdep install 和 catkin_make。完整依赖、运行配置安装、启动验证、八类操作与升级回滚见 [使用手册](documents/USER_MANUAL.md)；跨工作空间话题、服务、TF、配置字段与授时见 [接口参考](documents/INTERFACE_REFERENCE.md)。各包 README 给出单包入口。

端侧 ZIP 解压后从 edge_side_pkg 目录执行相同命令。包级 launch 默认读取包内配置，一键脚本显式读取工作空间 config/profile；二者修改位置不同，均无热重载。deployment.enabled 等说明字段不等于启停开关。设备上的工作空间路径与 ROS 契约不变。

Go2 legacy profile 不启动任务，Robot2/3 按就绪状态启动协调器。UGV_003 可启动 Gemini 视频，UGV_004 默认不启动视频。Ground-Air 保持手动启动和阶段互斥，外部 ground_air_msgs 服务定义须在设备核验。本次迁移没有操作设备，不代表重新通过实机验收。

## 开发与验证

~~~bash
python3 -m pip install -r requirements-test.txt
python3 -m unittest discover -s tests -v
python3 scripts/check_packages.py
~~~

CCS_dev 通过 edge_side_pkg 子模块固定本仓库提交。克隆主项目使用 git clone --recurse-submodules；已有检出执行 git submodule update --init --recursive。升级在主项目显式更新子模块并提交，不在打包期间拉取远程最新版本。独立仓库测试不读取主项目现场 devices.json、地图或任务。
