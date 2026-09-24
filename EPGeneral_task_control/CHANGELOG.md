# Changelog

## [0.6.4] - 2026-09-24

- UGV_004 opts into fresh localization/full TF checks and terminal preparation failures. Preserve diagnostics across queries and restart; explicit task redelivery starts a new preparation. Other profiles retain retry defaults.

<!-- epgeneral_task_control_VERSION: 0.6.4 -->

## Unreleased - 2026-09-17 deployment configuration

- Keep the UGV_003 TEB reverse saturation bound (0.01 m/s) below the unchanged
  safety deadband (0.02 m/s), with penalty epsilon 0.005. The previous 0.10
  bound caused reverse-command cancellation during waypoint transitions.
- Disable backward initialization and proportional saturation explicitly.
  Reverse motion remains blocked. Reload navigation to apply; offline checks
  passed, and physical multi-waypoint acceptance remains pending.

## [0.6.3] - 2026-09-16

- Clear the Wheeltec local and global costmaps while chassis control is still
  disabled, then recheck localization and disabled state before enabling
  autonomous control. A missing or failed clear service aborts the task.
- Deliver safety-gate 0.1.2. It evaluates source lethal costmap cells instead
  of already-inflated inscribed cells and filters lethal grid squares that
  overlap the measured chassis body. Unknown cells and both live point-cloud
  vetoes remain fail-closed.
- Rotate the Gemini 336L video stream by 180 degrees for its inverted mount.

## [0.6.2] - 2026-09-16

- Deliver the baseline-checked WheelTech safety-gate 0.1.1 patch. A complete
  snapshot, collision check, and output publish now share the gate's output
  lock, preventing high-rate perception updates from starving every command.
- Tolerate up to 0.02 m/s of measured TEB reverse solver drift while preserving
  the reverse-motion interlock; no negative velocity is forwarded when reverse
  is disabled.
- Pin the UGV_003 planner limits in the CCS launch to 0.20 m/s, 0.40 rad/s,
  0.10 m/s reverse bound, and forward-drive weight 1000.

## [0.6.1] - 2026-09-16

- Release control normally after planner/action failures instead of converting
  them into a persistent emergency stop; control and localization faults remain
  fail-closed.
- Correct the UGV_003 TEB reverse-velocity bound and use chassis odometry for
  planner velocity feedback while retaining FAST-LIO pose validation.

## [0.6.0] - 2026-09-16

- Add the UGV_003 two-dimensional navigation entry, navigation process logs,
  and startup failure diagnostics.
- Add service-backed Wheeltec manual/autonomous authority coordination and
  driver heartbeat publication without changing the task wire protocol.

## [0.5.1] - 2026-09-09

- Go2 通过可选 attach 模式复用原生导航，保留其他设备 managed 和非自动控制默认值。
- reset 服务改为 Trigger 并检查成功响应；使能、停用增加服务响应和实时状态确认，取消与使能串行处理。
- 为 Go2 补齐主线急停消息确认、持久闭锁和仅在空闲且已停用时允许的人工 reset 服务。
- 服务超时、定位失效、终止停用失败均显式失败；超时使能返回后补偿停用，不虚报急停成功。

## [0.5.0] - 2026-09-07

- 新增 Ground-Air AGV 地面任务适配器，桥接原生任务、状态和急停服务。
- 新增经机器人确认的急停动作及持久闭锁，保留 Scout v2 协议兼容性。
- AGV 准备阶段校验实时定位、地图栅格和 0.1 m/s 速度上限。

## [0.4.4] - 2026-09-02

- 将运行配置迁移至 `epgeneral_device_config`，任务协议与执行状态机保持不变。

## [0.4.3] - 2026-08-27

- 在导航准备阶段校验任务点对应的 PGM 栅格，拒绝地图外、障碍区和未知区目标。
- 保留 `move_base` action 状态及文本，并区分规划失败、目标拒绝、抢占和其他 action 失败。

## [0.4.2] - 2026-08-27

- 创建并持有 `tf2_ros.TransformListener`，使 Scout 导航适配器实际订阅 `/tf` 和 `/tf_static`。
- 修复系统存在实时 `map<-odom` 变换但适配器私有 TF buffer 始终为空的问题。

## [0.4.1] - 2026-08-27

- 捕获 `map<-odom` TF 查询和位姿转换异常并反馈 `LOCALIZATION_UNAVAILABLE`。
- 防止导航准备失败以未捕获 ROS callback 异常结束，保证平台能够收到失败状态并释放执行等待。

## [0.4.0] - 2026-08-27

- 任务文件提交后异步启动并常驻 Scout 导航栈，导航就绪后才进入 `ready`。
- 执行、完成、失败和常规停止复用导航进程；删除、急停及关闭执行安全卸载。
- 增加内部 `PREPARE/UNLOAD` 命令、准备重试和导航进程退出监控。

## [0.3.1] - 2026-08-26

- 执行前校验实时 `/fastlio_odom`、`map<-odom` TF 和导航地图文件。
- 为定位不可用、地图不匹配和导航启动超时返回明确错误码。

## [0.3.0] - 2026-08-26

- 增加 Scout Mini 导航执行适配器、map<-odom 位姿校验、顺序航点 actionlib 执行和安全停止。
- Scout 执行要求端侧重定位状态为 localized 且任务地图匹配当前地图。

## [0.2.0] - 2026-08-26

- 升级 `ccs-task-control-v2`，增加任务协商、读取、删除、终止和急停消息。
- 增加 `MissionStore` 和 `~/ccs_edge_ws/mission` 任务目录。

## [0.1.0] - 2026-08-13

### Added

- `ccs-task-control-v1` UDP 14563/14564 接收、ACK、心跳、状态和进度。
- zlib/CRC32/分片校验、幂等 request ID、修订约束和 XML 原子持久化。
- 带完整 ID 的接收/执行状态机，以及强类型 ROS command/feedback 适配接口。
- UTC 调度、适配器反馈超时、停止与重启安全清理。
