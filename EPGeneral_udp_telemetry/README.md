# epgeneral_udp_telemetry

版本：**v0.4.0**。将 ROS 消息与文件状态转换为 CCS MessagePack UDP 遥测。运行配置统一由 `EPGeneral_device_config` 保存、安装和分发，功能包不携带设备 YAML。

[完整使用手册](../documents/USER_MANUAL.md#documents-user-manual-md) · [接口参数](../documents/INTERFACE_REFERENCE.md#documents-interface-reference-md-6-udp_telemetryyaml) · [重构与迁移说明](../documents/UDP_TELEMETRY_GENERIC.md)

## 安装

当前部署基线为 Ubuntu 20.04、ROS Noetic、Python 3，源码保持 Python 3.6 语法兼容。依赖 rospy、roslib、diagnostic_msgs、std_msgs、python3-yaml、python3-msgpack，以及配置中声明的 ROS 消息包。预检会拒绝未安装的消息类型或不存在的字段。

```bash
cd ~/catkin_ws
rosdep install --from-paths src --ignore-src -r -y
catkin_make --force-cmake -DPYTHON_EXECUTABLE=/usr/bin/python3
source devel/setup.bash
python3 -c 'import epgeneral_udp_telemetry; print(epgeneral_udp_telemetry.__version__)'
```

预期版本 `0.4.0`，配套 `epgeneral_device_config` 版本 `0.2.0`。

## 配置与启动

`device.yaml` 提供设备 ID/IP；`udp_telemetry.yaml` 提供目标 IP/端口、数据描述符、ROS 类型与字段、单位、新鲜度和文件路径。新建部署可从 [udp_generic 模板](../EPGeneral_device_config/config/templates/udp_generic) 开始，先修改样例身份、目标 IP 和输入话题，并在地面站登记对应描述符集合。模板不会自动启用。

与 MQTT 一致，必须显式选择一个配置目录，或者完整的配置文件对。配置文件不热加载，修改后需重启。

```bash
CFG="$(rospack find epgeneral_device_config)/config"
# 先在共享入口安装本设备的 device.yaml 和 udp_telemetry.yaml，再执行检查。
rosrun epgeneral_udp_telemetry epgeneral_udp_telemetry_node.py --config-dir "$CFG" --check-config
rosrun epgeneral_udp_telemetry epgeneral_udp_telemetry_node.py --config-dir "$CFG" --check-ros
roslaunch epgeneral_udp_telemetry epgeneral_udp_telemetry.launch config_dir:="$CFG"
```

`--check-config` 校验并输出展开后的有效配置，不需要 ROS、不连接网络；已构建环境可用 rosrun，源码环境直接用 `python3 EPGeneral_udp_telemetry/scripts/epgeneral_udp_telemetry_node.py`。`--check-ros` 额外加载 ROS 消息类、检查字段，不创建节点、订阅或 UDP socket。正常启动也会先执行类型/字段预检，全部通过后才建立运行资源。

兼容入口：`telemetry_config_file:=... device_config_file:=...`，不能与 `config_dir` 混用。`destination_host`、`destination_port`、`link_status_topic`、`diagnostics_topic` 均为空默认值，**只有显式非空传值才覆盖 YAML**。旧的单独私有 ROS 参数注入应迁移为上述 launch 参数或命令行参数。未选择配置时启动失败，退出码 2；运行异常退出码 1。

## 通用来源模式

| source.mode | 可用数据类型 | 行为 |
| --- | --- | --- |
| ros_fields | pose、imu、text_status | 动态加载消息类，提取点分字段或向量分量映射，转换声明的单位 |
| topic_freshness | availability、pointcloud_status | AnyMsg 仅检查消息到达时间，不读取消息中的 true/false |
| value_status | availability | 读取 Bool 或枚举字段，按 values 映射 available/unavailable/unknown |
| file_status | availability | 从状态 JSON 提取地图 ID，在限定根目录检测配置的相对文件路径 |
| disabled | 全部既有类型 | 不订阅或读文件，保留描述符并输出 valid=false |

位姿位置输入支持 m/cm/mm，IMU 角速度支持 rad/s、deg/s，加速度支持 m/s2、g；线协议统一输出米、rad/s、m/s2，姿态输出欧拉角度。四元数字段固定 x/y/z/w。`expected_frame` 可拒绝不同 frame，不执行 TF、轴交换或 ENU/NED 坐标变换；需要变换时在上游适配。

`aggregation` 为 mean 或 latest；mean 对每个发送窗口求均值并对齐、归一化平均四元数。`max_samples` 限制缓存，溢出淘汰最旧样本并记录 dropped_count。NaN/Inf、非数值及无效四元数被隔离。`stale_policy: invalidate` 在超过 `max_age_seconds` 后标记无效；`hold` 明确允许保留最近值，适用于已确认的 latched 状态。新模板使用 invalidate，迁移的历史 profile 保留显式 hold。text_status 的 hold 会保留文本，但到达 timeout_seconds 后 status 为 unavailable。

## 协议与诊断

配置 schema 升为 2，仍兼容 schema 1；**线协议保持 schema 1、ccs-udp-telemetry-v1**。Level 1 的 pose/imu 为 20 Hz，Level 2 的点云状态为 5 Hz，Level 3 的 availability/text_status 为 1 Hz；心跳和诊断为 1 Hz。点云只发送元数据，文本最多 128 字符。

`name/display_name/type/level` 共同决定 descriptor_hash，必须与地面站接受的集合一致。改来源、路径、单位、设备身份或禁用来源不会改 hash；增删或重命名描述符须同步地面站。`global_pose`、`vision_pose` 等既有名称还承担地面站业务含义，不能视为随意可改的字段。

诊断话题由 `runtime.diagnostics_topic` 配置，链路 Bool 由 `runtime.link_status_topic` 配置；支持 `{device_id}` 展开且保留大小写。逐来源诊断包含接收/有效/拒绝/丢弃计数、样本年龄、过期状态及拒绝原因。文件来源不依赖示例 topic。链路 Bool 表示本机 sendto 结果，端到端接收仍需地面站确认。

```bash
# 按有效配置替换诊断话题
rostopic echo /epgeneral_udp_telemetry/diagnostics
sudo tcpdump -ni any udp port 14560
```

## 测试

在本包目录执行 `PYTHONPATH=src python3 -m unittest discover -s test -v`。测试覆盖配置迁移哈希、显式选择、无副作用预检、Bool/枚举语义、字段/单位/frame、过期、窗口上限、文件约束与失败清理。真实 ROS 调度及设备联调仍需在部署环境验收。
