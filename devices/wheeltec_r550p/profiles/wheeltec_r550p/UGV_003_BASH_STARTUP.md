# UGV_003 启动方式对齐 UGV_004（2026-09-24）

本次读取 UGV_004 实机 `nrc15@192.168.50.123:/home/nrc15/ccs_edge_ws/start_ccs_edge_dev.sh`，确认其内容与本机 `wheeltec_r550p_02` 当前脚本相同。原始 SHA-256 为 `3cabf278e57901e7732aa12036e72bc24935cd790cb8af09a6ede9ca0cd45682`。UGV_004 在本次任务中仅做只读核查。收尾时其入口出现同期外部更新（SHA-256 `cc171152166d67d31c81f24a63ee1761c8486dccfd11ac35986236971c994d02`）：新增可选相机监督、ROS_HOME 和降级处理，主链仍为 Bash。UGV_003 沿用自己的 Bash 视频管理器，没有复制该新增 Python 相机监督入口。两个观测摘要记录在 `evidence/bash_20260924/ugv004-reference.json`。

## 链路对比

| 环节 | UGV_003 原实现 | UGV_004 / UGV_003 新实现 |
|---|---|---|
| 启动入口 | Bash 加载环境后 exec Python Supervisor | Bash 加载环境并直接执行启动流程 |
| 拉起功能包 | Python Popen(start_new_session=True) | Bash `setsid roslaunch ... &` |
| 进程所有权 | Python Popen 对象和 process group | Bash PID 数组，核验 PPID/PGID/SID |
| 常驻检查 | Python while 循环 | Bash while 循环，节点失败连续复核三次 |
| 退出 | Python 信号回调、finally | Bash INT/TERM/EXIT trap |
| 启动锁/PID | run/startup.lock、run/*.pid | run/managed/startup.lock、run/managed/*.pid |
| 会话日志 | log 中同名文件追加 | logs/<UTC纳秒时间_PID>，logs/latest 指向本次会话 |
| 短时检查 | Python 监控内部检查 | 独立预检、SNTP、消息/零轮速检查，执行完即退出 |

UGV_003 额外同时持有旧 `run/startup.lock`，防止迁移时与旧入口并发。拉起的长期子进程关闭锁文件描述符。保留地图/定位互斥锁 `run/algorithm.lock` 及原有状态和地图目录。

移除 `scripts/ugv003_supervisor.py`，启动入口不再 exec 或导入任何 Python Supervisor。新增的 `ccs_wheeltec_preflight.py`、`ccs_sntp_sync.py`、`ccs_wheeltec_readiness.py` 与 UGV_004 一样只负责有限时长检查。ROS 节点自身及按需导航包装代码继续使用其原有语言，不承担一键启动根进程监控。

## UGV_003 保留的设备差异

最初读取的 UGV_004 对照版本使用 V5.1、默认无视频（随后外部更新加入可选相机）；UGV_003 继续使用此前完成的 V6.0 原生集成和可选 Gemini 336L/SRT。没有替换成 UGV_004 的二维导航或 /cmd_vel 底盘直连方案。

- 基础包入口：`epgeneral_wheeltec_integration/base.launch`。
- 任务入口：`epgeneral_task_control/wheeltec_task_control.launch`，保留 `/wheeltec_control`。
- 轨迹任务速度链：`move_base -> /wheeltec_driver/cmd_vel -> 底盘`；普通底盘驱动保留超时停车、限速和锁存急停，导航仍加载 V6 地形层与 Terrain Guard。
- 启动及退出使用 `/wheeltec_robot/set_autonomous=false` 归还控制权，并核验真实零轮速；只发送零速度，不触发导航目标。
- V6 建图、定位、原生地形导航继续由任务按需启动；正常一键启动保持待命。
- MID-360 地址、安装外参、FAST_LIO 原生包及输出路径保持原状，本次未修改原生工作区或系统网络/授时配置。

## 启动

先启动地面站的 NTP 服务（现有指控平台提供 `192.168.50.101:123/UDP`），再执行：

```bash
cd /home/nrc19/ccs_edge_ws
./start_ccs_edge_dev.sh --check
./start_ccs_edge_dev.sh
# 仅关闭本次视频：
CCS_ENABLE_VIDEO=0 ./start_ccs_edge_dev.sh
```

Ctrl+C 有序退出；SIGTERM 同样收尾。不要全局 pkill ROS。只检查模式不会拉起 ROS 节点。

授时门禁与 UGV_004 相同：等待最多 45 秒，检查实际 SNTP 偏差不超过 0.5 秒；仅 NTP 服务 active 不足以通过。设备刚启动为 1970 年、地面站未运行授时服务时会明确拒绝启动。脚本不会直接设置系统时间。必要服务启动失败会回收本次进程，外部 Master 保留；视频失败只降级并清理本次视频进程。

日志：`logs/latest/startup.log`、各功能包 `.log`、`ros/`、`video/`、`mqtav/`、`relocalization/`。算法历史输出、地图和任务状态路径未迁移。

## 文件与备份

端侧备份：`/home/nrc19/ccs_edge_ws/backups/ugv003_bash_20260924/`。

- 更新：根 `start_ccs_edge_dev.sh`、`manage_ccs_video.sh`。
- 新增：`scripts/ccs_wheeltec_preflight.py`、`scripts/ccs_wheeltec_readiness.py`、`scripts/ccs_sntp_sync.py`。
- 删除：`scripts/ugv003_supervisor.py`。
- 测试：将集成包的 `test_supervisor.py` 替换为 `test_startup.py`，验证真实 Bash 子进程与信号；更新本机 profile 测试。
- 文档：本文件与 V6 交付说明的当前入口说明，以及本机部署指南/记录。

本次源码、脚本和文档变更只在本机 edge_side_pkg 与 UGV_003 的 ccs_edge_ws 内。没有新增 FAST_LIO 包，没有修改 UGV_004。精确清单和摘要位于 `evidence/bash_20260924/changes.json`，原生审计位于同目录 `native-audit.json`。

## 验证

- 本机 Linux 和端侧：21 项集成回归通过；本机 profile 6 项通过。
- 实机只检查模式通过，launch 中所有节点可执行文件解析通过。
- 默认含视频启动进入待命；进程树确认父进程为 Bash、子进程为独立会话的 roslaunch；无 FAST-LIO/move_base 自动启动。
- 重复启动拒绝；Ctrl+C 退出码 130，所有本次进程有序停止。
- 必需服务异常退出触发收尾；非本次创建的 Master 不被停止。
- 冷启动时实测 NTP 缺失会拒绝启动；临时运行现有地面站授时服务后 timesyncd 自动完成校时，验收结束关闭临时授时服务。未改地面站代码或系统授时配置。
- 未执行运动任务，不把本轮启动验收等同于重新验收全部导航算法；此前 V6 无运动算法验证见 V6 交付说明。

## 回滚到本次修改前

先停止新入口，确认其进程已退出。核对待恢复文件与 `changes.json` 中的已部署摘要一致，再从备份恢复：

```bash
cd /home/nrc19/ccs_edge_ws
tar -xzf backups/ugv003_bash_20260924/before.tar.gz -C .
```

该备份只包含此次替换/删除前的指定入口、视频脚本、旧 Python 监控、旧测试和 V6 交付说明，不包含其他工作空间。再按清单删除本次新增的三份短时检查工具、test_startup.py 和新交付说明。保留 logs、地图、任务及备份。此回滚会恢复旧 Python 启动监控，仅用于明确需要回退本次改造时。
