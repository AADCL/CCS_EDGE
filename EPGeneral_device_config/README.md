# epgeneral_device_config

配套 CCS 0.23.1：[完整使用手册](../documents/USER_MANUAL.md#documents-user-manual-md) · [设备内接口与参数](../documents/INTERFACE_REFERENCE.md#documents-interface-reference-md)。多数包级 launch 默认读取共享配置包；epgeneral_mqtav 0.5.0 和 epgeneral_udp_telemetry 0.4.0 须显式选择 config_dir；一键脚本显式读取工作空间 `config/<profile>`，修改后需重启。

端侧公共配置的唯一入口。`config/` 保存设备身份以及 MQTT、UDP 遥测、视频、建图、重定位和任务配置；其他功能包不再携带运行 YAML。`device.yaml` 中的设备 ID 和 IP 必须与地面站 `config/devices.json` 对应记录完全一致。

当前包版本：`v0.2.0`。提供 MQTT 与 UDP 通用配置模板，UDP profile 升级配置 schema 2，配套 epgeneral_mqtav 0.5.0 / epgeneral_udp_telemetry 0.4.0 的显式目录入口。建图配置增加同目录 OT 输出与可选占据图导出器，见 [OT 接口](../documents/OCTOMAP.md)；未配置时保持现有设备生成流程。

多数单包默认入口使用本目录；MQTT、UDP 需显式指定本目录或设备 profile 配置目录。设备一键脚本使用 `<CCS工作空间>/config/<profile>`。部署前将 profile 同名 YAML 安装到实际入口。普通设备安装本包与六个业务包，Ground-Air 另加专用控制包及 ground_air_msgs；deploy/documents 不进入 catkin src。

MQTT 通用模板位于 `config/templates/mqtav_generic/`，只作起点，部署前替换设备身份、Broker 和消息源。设备身份仍使用 schema_version 1，MQTT 接入配置采用 schema_version 2；详见[MQTT 配置说明](../epgeneral_mqtav/README.md)。

UDP 通用模板位于 `config/templates/udp_generic/`，仅作起点；设备身份使用 schema_version 1，UDP 配置使用 schema_version 2，UDP 线协议仍为 schema 1。共享与八份 profile 的描述符哈希保留，来源差异由 YAML 指定。详见 [UDP 通用化与迁移](../documents/UDP_TELEMETRY_GENERIC.md)。
