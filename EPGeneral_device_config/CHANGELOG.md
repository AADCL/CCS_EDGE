# 更新记录

## 0.2.0 (2026-09-22)

- 新增 config/templates/udp_generic，配套 epgeneral_udp_telemetry 0.4.0 显式配置入口。
- 共享及八份 UDP profile 迁移 schema 2，明确来源模式、单位和历史 hold 策略；新模板启用过期失效。
- Go2 robot2/robot3 定位状态使用 Bool 值映射；文件状态的字段/相对路径、输出话题迁入配置。
- 九份配置的 descriptor_hash 保持不变；设备身份与 MQTT 配置入口保持共用。

## 0.1.4 (2026-09-22)

- 新增 config/templates/mqtav_generic 配置模板，设备身份文件保持 schema_version 1，MQTT 接入配置使用 schema_version 2。
- 八套设备 MQTT profile 统一声明连接模式与电池单位；运行配置继续由本包集中安装和分发。
- 配套 epgeneral_mqtav 0.5.0：须显式指定 config_dir 或完整文件对，不再隐式使用样例身份。

## 0.1.3 (2026-09-21)

- 为共享及设备 profile 建图配置增加同目录 OT 输出；占据图导出命令保持显式接入，不填写未验证的现场路径。

## 0.1.2 (2026-09-21)

- 新增可选可信区域 XML 接收与存储配置；区域缺省或失败不影响重定位。


## v0.1.1 - 2026-09-02

- 集中保存七类端侧公共运行配置。
- 作为六个主功能包的统一默认配置入口。
