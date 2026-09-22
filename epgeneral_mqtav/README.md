# epgeneral_mqtav

<!-- epgeneral_mqtav_VERSION: 0.5.0 -->

当前版本：`v0.5.0`

ROS1 通用健康状态 MQTT 上报包。相同代码可服务于不同设备；设备身份、消息类型、字段和单位差异由配置提供，不设设备白名单或按设备名判断的代码分支。

[完整使用手册](../documents/USER_MANUAL.md#documents-user-manual-md) · [设备内接口与参数](../documents/INTERFACE_REFERENCE.md#documents-interface-reference-md) · [重构说明](REFACTOR_REPORT.md)

## 部署入口

本包要求显式选择配置目录，其中必须同时存在 `device.yaml` 和 `epgeneral_mqtav.yaml`。配置的部署归属仍是 `EPGeneral_device_config`，设备 profile 是安装时覆盖共享配置的源文件。新增设备不需要修改本包代码。

```bash
source /opt/ros/noetic/setup.bash
source ~/ccs_edge_ws/devel/setup.bash
CFG="$(rospack find epgeneral_device_config)/config"
# 先在 CFG 中放入当前设备的配置，不要直接使用仓库的示例身份。
rosrun epgeneral_mqtav epgeneral_mqtav_node.py --config-dir "$CFG" --check-config
rosrun epgeneral_mqtav epgeneral_mqtav_node.py --config-dir "$CFG" --check-ros
roslaunch epgeneral_mqtav epgeneral_mqtav.launch config_dir:="$CFG"
```

`--check-config` 只解析配置并显示展开后的设备、Broker、话题、接入模式；无需 ROS、MQTT Broker，不创建日志或连接。`--check-ros` 还校验已安装的 ROS 消息类及字段路径，不连接 ROS master 或 Broker。失败返回 2。正常启动也会在订阅及 MQTT 连接前执行消息类和字段校验。

兼容旧启动脚本的显式文件对：

```bash
roslaunch epgeneral_mqtav epgeneral_mqtav.launch \
  config_file:="$CFG/epgeneral_mqtav.yaml" device_config_file:="$CFG/device.yaml"
```

文件对必须完整，不能与 `config_dir` 混用。**无参数启动不再隐式读取示例设备身份**；原来只运行裸 `roslaunch` 的部署须补上 `config_dir`。文件对模式允许两个文件位于不同目录，操作者须保证属于同一部署。新部署优先使用目录模式。

默认日志：`~/.ros/log/epgeneral_mqtav/<device_id>/epgeneral_mqtav.log`。可用 `log_dir` 显式覆盖；文件达到 10 MiB 后轮转，保留 5 份历史日志，每条记录同步刷盘并输出到控制台。

## 配置版本与设备身份

`device.yaml` 保持共享配置版本 1：

```yaml
schema_version: 1
device:
  id: DEVICE_A
  ip: 192.0.2.20
```

示例 IP 属于文档用途，部署前应替换。ID 长度 1–64，只允许 ASCII 字母、数字、下划线、连字符，首字符为字母或数字；大小写原样保留、区分大小写，不自动改名。ID 应在同一 Broker 的部署范围内唯一；本机校验不能检测另一台正在使用相同 ID 的设备。

新 `epgeneral_mqtav.yaml` 使用 `schema_version: 2`。省略版本或使用 1 仍兼容旧配置：从独立 connection、connected_on_message 推导模式，电量沿用 `legacy_auto`；启动日志会提示迁移。共享目录中的旧 MAVROS 样例保留用于兼容，八个实际设备 profile（含 UAV_001） 已升级为版本 2。

通用模板在 [EPGeneral_device_config/config/templates/mqtav_generic](../EPGeneral_device_config/config/templates/mqtav_generic/epgeneral_mqtav.yaml)。模板关闭状态、电池、任务订阅，以独立周期消息判断连接；需配置实际设备和 Broker 后才能使用。

```yaml
schema_version: 2
mqtt:
  ground_station_ip: 192.0.2.10
  port: 1883
  client_id_prefix: mqtav-
  qos: 1
  keepalive_seconds: 10
  heartbeat_hz: 1
  telemetry_hz: 1
  topics:
    presence: mqtav/{device_id}/presence
    heartbeat: mqtav/{device_id}/heartbeat
    status: mqtav/{device_id}/status
ros:
  node_name: epgeneral_mqtav
  connection_mode: heartbeat
  connection:
    topic: /devices/{device_id}/heartbeat
    message_type: std_msgs/Empty
    timeout_seconds: 3.0
  state:
    enabled: false
  battery:
    enabled: false
  mission:
    enabled: false
```

MQTT 三个话题必须不同，版本 2 强制包含 `{device_id}`；MQTT 和 ROS 话题仅允许这一占位符，无格式说明符、属性访问或二次展开。ROS 展开结果还须是合法绝对话题名；例如含连字符的设备 ID 可用于 MQTT，但不能直接插入 ROS 名称，可为它配置固定合法 ROS 话题。版本 2 拒绝未知配置键，便于发现拼写错误。

## 四种连接模式

| ros.connection_mode | 连接依据 | 必要配置 | 适用情形 |
| --- | --- | --- | --- |
| field | 状态消息映射的 connected 值 | 启用 state，mapping.connected 非 null | MAVROS 或提供显式连接标志的接口 |
| freshness | 最近一条状态消息的到达时间 | 启用周期 state，timeout_seconds | 里程计、底盘状态、雷达数据等持续消息 |
| heartbeat | 独立周期消息的到达时间 | connection.topic/message_type/timeout_seconds | armed 等来自锁存或低频变化消息 |
| disabled | 不判断设备连接，保持 null | 可关闭所有 ROS 数据源 | 仅报告 MQTT 进程在线状态 |

`heartbeat` 首条周期消息前为 false，超时为 false，恢复后为 true；不会被 state 覆盖。`freshness` 首次计时器检查前可为 null，随后无数据为 false。超时范围 0.1–3600 秒，使用单调时钟；检测间隔为 min(1 秒, 超时/2)。`field` 仅信任发布者的连接字段，不额外推断消息超时。

版本 2 以 connection_mode 为准；保留的旧 connected_on_message 仅供兼容，迁移后不决定模式。只有 heartbeat 模式允许 connection 段。周期模式表示“配置的数据源在持续发布”，不等同于整台设备所有功能健康，不能用锁存或仅变化时发布的话题判断在线。

## 字段映射与单位

state、battery 支持 `enabled: false`。启用时配置 topic、message_type 和 mapping；message_type 为 `package/Message`。state 输出 connected、armed、system_status、mode；battery 输出 percentage、voltage、current。mapping 省略时采用旧同名字段，显式 null 表示不可用。

字段可为安全点分路径，或下列结构（用于实际消息中存在的字段）：

```yaml
mapping:
  percentage: {field: power.soc, invalid_values: [-1, 255]}
  voltage: {field: power.millivolts, scale: 0.001, offset: 0}
  current: {field: power.milliamps, scale: 0.001, invalid_values: [-9999]}
percentage_unit: percent
```

转换顺序：取字段 → 检查 invalid_values → 可选 values 枚举查表 → scale/offset 换算。查表未命中输出不可用；查表键按 YAML 原始类型匹配，请将字符串键明确加引号。例如模式 `mode: {field: control_mode, values: {0: MANUAL, 1: AUTO}}`。不支持表达式执行、数组索引或任意脚本。

版本 2 启用电池时必须填写 percentage_unit：fraction（0–1）、percent（0–100），或显式 legacy_auto（旧兼容行为：≤1 当比例，否则当百分数并封顶）。单位转换在字段换算之后执行；新配置应选择前两种明确单位。百分数模式的 0.5 表示 0.5%，比例模式的 0.5 表示 50%。无效、非有限数值和超范围比例/百分数输出 null；电压、电流输出有限值或 null，负电流保留以支持充放电方向。

connected/armed 接受 bool、0/1、字符串 true/false/0/1，其他值输出 null，避免将字符串 false 误判为 true。system_status 归一为有限数值或 null；模式为字符串或 unknown。NaN/Inf 不进入 JSON 数值。

任务摘要配置：`mission.enabled: true`、topic、message_type、field_path，例如 std_msgs/String 的 data。未收到或读取失败时为 unknown。String.data 内的 JSON 仍作为字符串上报，不自动解析 JSON 内部字段。

## MQTT 协议与生命周期

沿用线协议 schema_version `"1.0"`，presence/heartbeat/status、session_id、递增 sequence、device.id/ip 和 health 字段保持兼容。配置版本 2 不改变线协议版本。

- Client ID 为 client_id_prefix + device.id；默认 mqtav-。
- 连接成功发送 retained online presence 和当前状态；Last Will 为 retained offline，正常退出也请求发布 offline。
- 心跳和状态频率独立配置，默认各 1 Hz；QoS 可配置 0/1，默认 1。
- 保留现有 Paho 自动重连及 1–60 秒退避逻辑；断线时跳过新的状态发布，不保证 Paho 内部已排队消息的清空。
- 启动失败及正常退出均清理计时器、ROS 订阅和 MQTT 线程。

当前传输仍为内网明文 MQTT，不提供 TLS、账号密码、下行控制或飞行控制；本次重构没有扩展传输协议。

## 构建与验证

本包保持 Python 3.6+ 源码兼容；ROS 环境须使用匹配的 Python 3 依赖。ROS Noetic 示例：

```bash
sudo apt install python3-yaml python3-paho-mqtt python3-rospkg
cd ~/ccs_edge_ws
rosdep install --from-paths src --ignore-src -r -y
catkin_make -DPYTHON_EXECUTABLE=/usr/bin/python3
source devel/setup.bash
```

按配置安装实际消息包；不使用 MAVROS 的部署不需要 mavros_msgs。开发机执行：

```bash
cd epgeneral_mqtav
PYTHONPATH=src python3 -m unittest discover -s test -v
python3 scripts/check_version.py
```

上线验收应覆盖目标 ROS 消息字段检查、正常数据、超时/恢复、设备重命名、Broker 断线重连和 Last Will。静态与模拟测试不能替代设备实测。
