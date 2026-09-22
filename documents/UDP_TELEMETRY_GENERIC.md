# UDP 遥测通用化重构与迁移

本次发布 `epgeneral_udp_telemetry 0.4.0`、`epgeneral_device_config 0.2.0`。运行包只负责配置加载、ROS/文件采集、聚合、协议编码和发送；设备身份、消息来源、状态语义及部署路径均由配置决定。

## 配置归属

共享运行入口为 `EPGeneral_device_config/config`，新部署模板为其中的 `templates/udp_generic`。设备 profile 的同名 YAML 保留为版本化部署样例；安装到共享入口，或由现有一键脚本分发到 `<工作空间>/config/<profile>` 后显式选择。它们不是功能包私有配置，不应同时维护两份实际生效配置。

| 部分 | 内容 |
| --- | --- |
| device.yaml | 设备 ID/IP，保持身份 schema 1；与 MQTT 共用 |
| udp_telemetry.yaml network | 地面站 IPv4/IPv6 字面地址、端口及数据报大小 |
| udp_telemetry.yaml runtime | 链路状态与诊断输出话题，可包含 {device_id} |
| descriptors 的公共定义 | 地面站显示、路由与哈希契约 |
| descriptors.source | 来源模式、输入话题/消息/字段、单位、缓存和过期策略、文件状态路径 |

功能代码不再默认选择示例设备，也不保留固定地面站地址或设备 profile 分支。协议 ID、数据类型、频率和诊断字段仍是公共协议契约。Go2/UAV/Scout/Wheeltec 的实际话题、用户名目录、IP 和设备 ID 保留在各自配置或部署脚本，不能直接复制到其他设备使用。

## 本次行为变更

- 修复包级 launch 的固定目标 IP/端口覆盖 YAML；覆盖参数默认空，只有显式传值生效。现有 profile 启动脚本明确传入的参数仍有更高优先级。
- Go2 robot2/robot3 的 `/localization/ok` 从消息到达检测迁移到 `std_msgs/Bool` 值检测。收到 false 为 unavailable，true 为 available；当前配置使用 hold 保留 latched 状态。其他仍采用 topic_freshness 的来源只表示消息活动性。
- PGM 专用检测扩展为 file_status。旧 `kind: pgm_file` 兼容，原有 state_file/map_root 语义保留；新 state_field/path_template 支持例如 `active.id` 与 `{map_id}/occupancy.ot`。状态文件上限 1 MiB，拒绝路径穿越、非法地图 ID、符号链接及非普通成果文件；无文件时报告 unavailable。
- 共享和八份 profile 全部迁移配置 schema 2，显式声明来源模式、单位和历史采样策略。既有 pose/imu/text 保留 hold，避免静默改变已部署行为；新通用模板使用 invalidate，部署时应按实际发布频率确定 max_age_seconds。
- 新增动态消息预检、分量映射、有限单位转换、frame 一致性检查、有界采样、禁用来源，以及部分启动失败/退出后的定时器、订阅、发布者和 socket 清理。

## 配置示例

以下是来源片段，应放入完整 `udp_telemetry.yaml` 的匹配 descriptor 中。完整起点见[通用模板](../EPGeneral_device_config/config/templates/udp_generic)。

```yaml
# type: availability, level: 3
source:
  mode: value_status
  topic: /devices/{device_id}/localization_ok
  message_type: std_msgs/Bool
  mapping: {value: data}
  values: {true: available, false: unavailable}
  stale_policy: invalidate
  max_age_seconds: 3.0
```

values 的键按 YAML 标量类型精确匹配；数字 1 不等于布尔 true，未匹配值输出 unknown。不要在一个映射中混用 YAML/Python 会合并的键（如 true 与 1）；布尔与枚举来源应分别配置。

```yaml
# type: pose, level: 1；输入分量单位为毫米
source:
  mode: ros_fields
  topic: /devices/{device_id}/pose
  message_type: example_msgs/PositionState
  mapping:
    position: {x: position.east, y: position.north, z: position.up}
    orientation: quaternion
  units: {position: mm}
  expected_frame: map
  aggregation: latest
  max_samples: 100
  stale_policy: invalidate
  max_age_seconds: 1.0
```

示例消息包须由设备提供；路径是公开点分字段，不支持表达式、函数执行或数组下标。坐标系转换由上游节点完成。

## 升级步骤与兼容边界

1. 备份实际生效的 device.yaml、udp_telemetry.yaml；升级两个包并重新构建、source 工作空间。
2. 按 profile 迁移说明更新来源模式与单位；检查真实话题类型、Bool/枚举含义、frame 和数据时效。保留 descriptor 公共定义及设备 ID 大小写。
3. 显式选择共享配置目录或完整文件对，执行 --check-config 与 --check-ros；检查输出的设备、目标、展开后话题和哈希。
4. 启动节点并核对逐来源诊断，再在地面站确认心跳、三个等级、false 状态和过期行为。改变配置后重启节点。

schema 1 配置仍可读取，旧 availability 默认仍是 topic_freshness，旧 pose/imu 保留最近值；仅升级程序不会自动把所有状态话题变成 Bool。旧 launch 的完整文件对和显式覆盖仍可用；无配置直接启动、只传一个文件、同时传目录与文件对会失败。直接注入私有 ROS 参数的启动方式须迁移为 CLI/launch 参数。

线协议保持 schema 1、ccs-udp-telemetry-v1，以及原 20/5/1 Hz、心跳 1 Hz、五种数据类型。共享和八份 profile 的 descriptor_hash 与重构前相同。修改 source 不要求修改地面站；增删、重命名、改显示名或等级会改变 hash，需要先在地面站登记。禁用来源保留公共描述符并输出 valid=false。单 pose 的通用模板是新描述符集合，不能假设现有地面站自动接受。

## 验证记录

回归测试包含旧 profile 哈希基线、离线/ROS 类型预检、状态取值与过期、单位和 frame、缓存上限、文件约束、发送隔离和资源清理。发布时另以本地 CCS 地面站实际解码器验证八套 profile 的有效三级报文及心跳；具体执行结果见 PR。Windows 环境未执行真实 ROS/catkin、硬件、线上网络与实际调度验收，部分符号链接/平台专属测试按条件跳过。

[包使用说明](../EPGeneral_udp_telemetry/README.md) · [完整参数表](INTERFACE_REFERENCE.md#documents-interface-reference-md-6-udp_telemetryyaml)
