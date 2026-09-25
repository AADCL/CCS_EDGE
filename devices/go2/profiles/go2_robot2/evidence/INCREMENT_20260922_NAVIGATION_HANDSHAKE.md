# QRD_002 导航握手修复记录（2026-09-22）

目标：unitree@192.168.50.111；CCS 工作空间 /home/unitree/ccs_edge_ws。

## 故障

执行 013dc4863d8e4c3587bdc657ccec6472 于 16:48:34 使能并下发首个目标，16:49:14 原生 move_base 因持续无位移，在一次 costmap 清理恢复后报告 oscillation ABORTED。

现场参数 require_motion_state=false、auto_enable=false。原生 SDK 桥使能后设置 motion_interrupted_=true，等待 prepare_fresh_goal 服务才接收速度；navigation_supervisor 仅在 require_motion_state 或 auto_enable 开启时调用该服务。因此目标进入规划器，但速度被底盘桥忽略。

## 安装修复

Go2 integration 的 launch/navigation.launch 向原生 navigation_stack.launch 显式传入 require_motion_state=true。该接入要求原生导航支持该参数及 /go2_sdk_bridge_real/prepare_fresh_goal（std_srvs/Trigger）服务；QRD_002 已现场核验。

- 已部署：/home/unitree/ccs_edge_ws/src/EPGeneral_go2_integration/launch/navigation.launch。
- 原件备份：/home/unitree/ccs_edge_ws/backups/qrd002-navigation-handshake-20260922/navigation.launch.before。
- 新文件 SHA-256：6e31cf812acfdf6d4bc365ce860a024735002987a70530bb6eae3436ffee111f。
- 未修改原生 SDK、速度限制、避障或振荡阈值；未部署 QRD_003。

## 验证与交付状态

本地 Robot2/Robot3 profile 32 项测试通过。端侧在独立 ROS master 11329 使用原生 supervisor 二进制、模拟桥和内部 action 验证四种情形：旧参数漏握手、修复参数成功握手、桥拒绝时不转发目标、stopping 状态不转发目标。全部通过，未启动真实 SDK 测试运动。

已通过重定位协调器维护会话重新加载导航：现场 require_motion_state=true、auto_enable=false，并确认 supervisor 订阅 /go2/control/motion_state；定位状态 awaiting_pose，底盘 disabled，无活动执行。

任务失败后，用户曾让机器人坐下。后续定位失效、StopMove=-1 和持久安全闭锁单独保留。安全文件 SHA-256 前后均为 743c79644cec3d1aefa58698f249e6c6199fba5732cc2e81be714defdd727605，未删除或覆盖；未自动复位、使能或重放任务。

恢复需现场确认站立和正常控制状态、停车反馈恢复，重新定位，并按已有人工急停复位流程处理闭锁，再重新下发任务。真实运动验收尚未进行。回滚 launch 不应覆盖安全状态。

CCS_dev 本次证据位于 .diagnostics/qrd002_navigation_20260922/，包含原始日志归档、独立测试脚本及结果、安装与实时验证记录。

## 后续：历史安全闭锁复位与下发验证

用户重新执行流程时，17:55:56 的任务下发被 16:52:08 保存的安全闭锁拒绝。两端请求 ID 5e7f6f510358407c81cd714f79cda822 一致，同期定位已恢复；拒绝文本引用历史原因。

连续三份新鲜诊断确认 disabled、无运动命令、stop_complete=true、localization_ok=true，同时排除活动目标/执行后，调用正式 reset_emergency_stop 服务，返回 success=True。原闭锁备份于端侧 backups/qrd002-safety-reset-20260922/go2_task_safety.before.json；未直接删除安全文件、未使能。

18:01:41 重新完整传输原任务（revision=1，17 航点，2 分片，CRC32=1902180481），prepare/commit 均 accepted=True，有本轮 XML 落盘证据，ROS 状态与 manifest 均 ready。最终定位正常、停车完成、disabled、无闭锁、无活动执行。未进行运动验收。指控平台需重新发起下发以刷新自身请求确认；未伪造运行时状态或改写任务 JSON。

后续证据：CCS_dev/.diagnostics/qrd002_reset_20260922/REPORT.md、reset.txt、delivery_verification.txt。
