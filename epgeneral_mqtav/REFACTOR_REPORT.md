# epgeneral_mqtav 0.5.0 重构交付说明

日期：2026-09-22。修改对象：独立 CCS_EDGE 仓库；发布分支基于远程 main 的 d9a35ee，保留已合入的 UAV、可信区域与 OT 地图更新。版本：epgeneral_mqtav 0.5.0、epgeneral_device_config 0.1.4。

本次将 MQTT 接入统一为配置驱动的四种连接模式，补齐字段转换、身份校验、明确配置选择及生命周期管理。新增设备在已有 ROS 接口能够用字段映射表达时，只需提供配置，不需要按设备名修改程序。

## 变更对应关系

| 原有问题 | 实现 | 位置 |
| --- | --- | --- |
| 连接字段与消息超时混用 | field/freshness/heartbeat/disabled 四种模式；版本 2 显式声明 | src/epgeneral_mqtav/config.py、ros_bridge.py |
| QRD_002 锁存 Bool 被用于在线超时 | 使用已有 /go2/state/low_state 周期源，Bool 只更新 armed | devices/go2/profiles/go2_robot2/config/epgeneral_mqtav.yaml |
| 电池单位依赖自动猜测 | fraction/percent，保留显式 legacy_auto；支持 scale/offset/invalid_values | fields.py、state.py |
| 自定义状态枚举难以复用 | values 查表及安全点分字段提取 | fields.py |
| ID 字符无限制，话题重复格式化 | ID 长度/字符校验，大小写保留，严格单次话题展开 | config.py |
| 任务订阅含固定设备 ID | 从 device.yaml 展开订阅话题；与任务发布方配置做回归匹配 | QRD_002/QRD_003/UAV_001 MQTT profile |
| 缺少配置时可能选择 UAV 样例身份 | 强制配置目录或完整显式文件对，禁用隐式样例回退 | node.py、launch |
| 消息类问题直到启动中途暴露 | 所有启用源先检查消息类和字段，再订阅与连接 MQTT | ros_bridge.py、node.py |
| NaN/Inf 或字符串 false 异常 | 非有限数值输出 null；明确布尔解析 | state.py、fields.py |
| 异常退出缺少完整释放路径 | finally 清理计时器、订阅、MQTT 客户端；幂等关闭入口 | node.py、ros_bridge.py |

## 配置迁移清单

| profile | 身份 | 连接模式 | 连接依据 | 电池百分比单位 |
| --- | --- | --- | --- | --- |
| go2_edu | QRD_001 | freshness | /livox/lidar | 电池关闭 |
| go2_robot2 | QRD_002 | heartbeat | /go2/state/low_state | fraction |
| go2_robot3 | QRD_003 | heartbeat | /go2/state/low_state | fraction |
| scout_mini | UGV_001 | freshness | /scout_status | percent（百分比字段禁用，仅电压） |
| wheeltec_r550p | UGV_003 | freshness | /odom | percent（百分比字段禁用，仅电压） |
| wheeltec_r550p_02 | UGV_004 | freshness | /odom | percent（百分比字段禁用，仅电压） |
| ground_air_agv | AGV_001 | field | /mavros/state 的 connected | fraction |
| uav_001 | UAV_001 | field | /mavros/state 的 connected | fraction |

设备 profile 中保留旧 connected_on_message 字段供兼容工具读取；版本 2 的运行行为以 connection_mode 为准。共享根目录中的旧 MAVROS 配置仍可显式选用；新增通用模板在 EPGeneral_device_config/config/templates/mqtav_generic 中。模板身份与文档 IP 必须替换。

## 使用与兼容边界

使用 [包级 README](README.md) 中的配置示例和启动命令。新增 `--config-dir`、`--check-config`、`--check-ros`；旧文件对参数继续支持。UAV bringup 已显式选择已安装共享配置目录，须随本次升级一起安装。仅“无参数隐式使用共享样例”的启动方式不再支持。

MQTT 消息 schema_version 仍为 1.0，保持 topic 命名、设备字段、session_id、sequence 和状态信封兼容。配置 schema_version 2 与消息版本不是同一概念。

本包没有迁移所有其他功能包中的设备 ID、导航 frame、外部工作空间路径或任务发布方命名。任务控制发布话题仍由其自身配置管理；本次测试验证 MQTT 展开结果与现有发布配置一致。跨七个功能包整体通用化仍须逐项处理原审查报告中的其他问题。

消息新鲜度只证明选定消息源持续发布，不代表设备所有子系统健康。field 模式不推断输入消息是否超时。schema 2 可明确单位，但不能自动证明第三方驱动实际遵循这些单位。

## 验证记录

基于远程 main 的 d9a35ee，在 Windows / Python 3.12.2 环境完成发布回归：**496 项测试，471 项通过、25 项跳过、0 失败**。

| 验证范围 | 总数 | 通过 | 跳过 |
| --- | --- | --- | --- |
| 仓库级测试 | 122 | 104 | 18 |
| 全部功能包测试 | 374 | 367 | 7 |
| 其中 epgeneral_mqtav（计入上一行） | 71 | 71 | 0 |

新增 35 项 MQTT 回归用例及 1 项显式配置入口检查。覆盖八套 profile、任意新设备身份与话题展开、四种模式、QRD_002 锁存/周期输入分离、单位/枚举转换、NaN/Inf、ROS 类型/字段预检、配置选择、启动失败资源清理和 UAV bringup 的显式配置目录。

另通过真实脚本入口对八套 profile 执行 --check-config，均成功；版本与文档一致性、Git 补丁空白检查通过。Python 3.6 仅作源码语法兼容检查，实际测试解释器为 Python 3.12.2。

25 项跳过来自当前平台条件：Bash/进程工具、Linux 进程所有权与锁、符号链接创建。目标 ROS/catkin 编译、真实驱动、MQTT Broker 断网重连与 Last Will 验收未执行。

在仓库根目录安装 requirements-test.txt 后可复现：

```bash
PYTHONPATH=epgeneral_mqtav/src PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 scripts/check_packages.py
python3 epgeneral_mqtav/scripts/check_version.py
git diff --check
```


## 部署验收步骤

1. 用既有 prepare_profile 流程准备目标 profile，将当前设备文件安装到 EPGeneral_device_config/config；新增设备则从通用模板起步填写真实身份、网络和 ROS 接口。
2. 在目标 ROS/Python 3 环境构建，安装配置所需消息包；先运行 --check-config，再运行 --check-ros。
3. 显式传入 config_dir 启动；观察 MQTT 中 device.id、三个话题、在线状态、连接状态和电池单位是否正确。
4. 对 heartbeat/freshness 暂停周期源超过超时，确认 false；恢复发布确认 true，armed 不应因独立心跳超时被重写。
5. 验证 Broker 断开重连、正常退出 offline、异常退出 Last Will，并核对新的默认日志目录。
6. 如需回退代码到 0.4.1，也应同步恢复对应旧 profile：新 ROS 话题模板与显式模式不能交给旧加载器。
