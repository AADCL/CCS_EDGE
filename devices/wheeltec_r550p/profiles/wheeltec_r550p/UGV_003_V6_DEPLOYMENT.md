# UGV_003 V6.0 端侧适配交付（2026-09-23）

设备：`nrc19@192.168.50.122`。端侧工作区：`/home/nrc19/ccs_edge_ws`。
本机修改位于 `edge_side_pkg`。未提交或覆盖本机其他设备任务的改动。

## FAST_LIO 与修改边界

依照最后的指示，**不在 CCS 或本机源码工作区增加 FAST_LIO 包**。已经撤回临时副本及 CCS 中相应的 build/devel 包产物。`rospack find fast_lio` 必须返回 `/home/nrc19/livox_fastlio/src/FAST_LIO`。

原生 FAST_LIO 会无条件打开 `Log/pos_log.txt`、矩阵及 IMU 日志，原有开关无法完全禁止源码目录写入。因此只调整原生包 `CMakeLists.txt` 的 `FASTLIO_RUNTIME_ROOT` 参数，默认指向 `/home/nrc19/ccs_edge_ws/log/fastlio`，保留所有算法、标定和地图参数。对应可执行文件已同步更新。该二进制是在 CCS 内完成编译的产物，安装前逐文件确认 src/include/msg/config 与原生源码相同；随后删除临时源码包及其构建产物。没有在原生工作区运行 catkin 构建。

原生工作区最终允许的三个变化：

- `src/livox_ros_driver2/config/MID360_config.json`
- `src/FAST_LIO/CMakeLists.txt`
- `devel/lib/fast_lio/fastlio_mapping`

前后摘要均为 7,507 个文件/链接，无新增、删除或其他变化；原生文档、地图、其他源码保持不变。详见 `evidence/native-audit.json`。另有已授权的 eth0 NetworkManager 连接变更。

## 雷达和网络

- eth0 连接 UUID：`347390f9-52b0-3fde-9431-f920f42e1756`。
- 持久主地址：`192.168.123.5/24`；保留 `192.168.8.119/24`，`ipv4.never-default=yes`。
- Wi-Fi `192.168.50.122` 与默认路由保持原状。
- 变更前进行了 ARP 地址冲突探测；Livox SDK2 发现协议确认 MID-360（类型 9），序列号 `47MDN7J0030224`，地址 `192.168.123.124`。
- 实际加载的 MID360 JSON：雷达 `.123.124`，命令、状态、点云、IMU 主机接收地址均 `.123.5`。未改 MID360s 示例文件。
- 安装外参不变：前移 0.10 m、上移 0.15 m、前倾 20°。CCS 预览转换改用正确的 `base_link <- body` 正向安装关系。

## 启动与停止

2026-09-24 起，一键入口已改为与 UGV_004 相同的 Bash `setsid roslaunch`、PID 数组和 trap 管理方式，已删除 Python 启动 Supervisor。当前日志为 `logs/<UTC纳秒时间_PID>`，启动 PID/锁位于 `run/managed`。详见 [Bash 启动对齐说明](UGV_003_BASH_STARTUP.md)；以下 V6 算法与数据配置继续有效。

```bash
cd /home/nrc19/ccs_edge_ws
./start_ccs_edge_dev.sh --check       # 只检查，不启动驱动或算法
./start_ccs_edge_dev.sh               # 前台启动，默认待命，包含可选视频
CCS_ENABLE_VIDEO=0 ./start_ccs_edge_dev.sh  # 不启动视频
```

按 Ctrl+C 正常退出。不要通过全局 `pkill ros` 清理。

启动顺序为环境与文件检查、网络/串口/时间同步检查、Master、底盘/Livox、新鲜真实消息、MQTT/遥测/建图协调/定位协调/任务协调、可选视频。Noetic、原生 underlay、CCS overlay 依次加载。脚本拒绝重复启动及冲突节点，不自动建图、定位、导航、执行任务或探索。

退出先停任务/导航，再停定位和建图相关服务、视频、基础驱动和本次自建的 Master；外部 Master 不归本脚本清理。视频按 PID、进程启动时间、进程组和启动归属令牌管理，失败时降级而不阻断基础服务。

## 建图、定位与原生导航

新增 `epgeneral_wheeltec_integration` 只包装原生 V6.0 组件，消除了已不存在的 `wheeltec_livox_base.launch` 入口。基础传感器与底盘常驻，算法按需启动。

- 建图：FAST-LIO + 原生静态 mapper + TF + 位姿适配器。正常结束时先停止 mapper 完成保存，再运行 CCS 包装的原生 `finalize_map.py`，显式指定 CCS 内输入和输出目录。
- 定位：局部 FAST-LIO、TF、位姿/点云适配器、NDT、地图服务。共享排他会话锁包含会话类型及地图 ID；定位成功需要连续、不同时间戳的新鲜 `map -> odom` 样本，不沿用旧磁盘状态。
- 导航：调用原生 `navigation_teb.launch`，保留地形层、Patchwork++、Terrain Guard、GlobalPlanner、TEB。需要同地图的真实定位会话，派生地图、真实消息、TF 和必要节点全部就绪。
- 速度：`move_base -> /wheeltec_driver/cmd_vel -> wheeltec_robot`。2026-09-24 轨迹任务适配改为直接接入普通底盘驱动，不再启动探索安全门。原生地形层、Patchwork++、Terrain Guard 和本地代价地图仍由导航入口加载。
- 底盘驱动保留 0.20 秒指令超时停车、线速度 0.20 m/s 与角速度 0.40 rad/s 的最终限幅；TEB 使用原生 V6 的反向上限 0.15 m/s 和惩罚边界 0.05。UGV_003 专属 `driver_auto_acquire` 使用新鲜底盘 `/odom` 确认驱动存活，适配 V6 空闲归还控制权。任务取消先确认目标终态再归还手柄；确认超时调用底盘锁存停车。急停/复位继续经过 CCS 服务和底盘服务，持久急停标记不会自动清除。

### 2026-09-24 轨迹任务直连修复

14:42:45 与 14:43:35 的两次轨迹任务中，原生安全门因 TEB 的微小负线速度锁存 `reverse_command_inhibited`，向 `/move_base/cancel` 取消目标。UGV_004 的正常导航使用 TEB 直接接普通底盘驱动。UGV_003 本次只调整控制接入与任务收尾，保留 V6 地形导航、定位和地图流程。

端侧改动位于 `/home/nrc19/ccs_edge_ws`：任务包的 `config.py`、`scout_adapter.py`、`wheeltec_control.py`；集成包的 `navigation.launch`、`native_navigation_components.launch`、`planner_overrides.yaml`、`native_navigation.py`、`readiness.py`、`package.xml`；配置 `config/wheeltec_r550p/task_control.yaml`。另同步 3 个针对性测试文件。共享 `config.py` 只应用本次安全门模式校验补丁，没有带入本机其他设备的开发内容。原文件副本和精确前后哈希在 `backups/ugv003-direct-navigation-20260924T073611Z/manifest.json`。

导航就绪检查要求 `/move_base` 发布到 `/wheeltec_driver/cmd_vel`、`/wheeltec_robot` 订阅该话题，并检查驱动 `cmd_vel_timeout <= 0.20`、`max_linear_x <= 0.20`、`max_angular_z <= 0.40`。正常收尾先取消目标并确认终态，再归还手柄；取消失败或超时调用底盘锁存停车。

验证：本机任务模块 120 项、端侧轨迹适配器 23 项、控制权 15 项、导航接线 2 项通过。端侧 CCS 集成包编译、launch 解析和一键脚本 `--check` 通过。端侧旧全量测试因缺少通用示例配置报 25 个环境错误；集成包启动脚本测试因缺少本机仓库的 `profiles/` 布局失败。未执行运动目标或急停复位。

部署时旧一键进程仍在用户终端 `pts/3` 前台运行，任务节点尚未重新加载新代码。需在该终端按 Ctrl+C 正常退出后，从 `/home/nrc19/ccs_edge_ws` 重新运行 `./start_ccs_edge_dev.sh`。此前的 `run/state/task_emergency_stop.json` 急停标记保留；现场确认底盘和控制链状态后，按既有人工复位流程处理。重启前不能把静态验收视为实车轨迹任务通过。

回滚时先正常停止一键进程，从上述备份目录按 `manifest.json` 中相同相对路径恢复原文件，再重新编译 CCS 集成包并启动。新增测试文件不影响运行，可留作追溯。回滚不得清除急停标记，也不修改 `~/livox_fastlio`。

## 数据路径与兼容性

所有运行数据进入 CCS：

| 内容 | 相对 `ccs_edge_ws` 的路径 |
|---|---|
| 建图及原生 finalize 产物 | `maps/mapping/<session>` |
| 地面站三件套原件 | `maps/download/<map_id>` |
| 导航派生地形文件 | `maps/download/<map_id>/native_v60` |
| 地图归档 | `maps/archive` |
| 状态、会话锁、PID、ROS_HOME | `run` |
| ROS 和服务日志 | `log` |
| FAST-LIO 运行输出 | `log/fastlio/Log`、`log/fastlio/PCD` |
| 实施前备份、摘要、部署包 | `backups/ugv003_v60_20260923` |

地面站继续发送现有 PCD/PGM/YAML 三件套；原件保留，原生地形、map_raw 等在独立目录生成。输入 PCD 已处于地图坐标系，不再次应用安装外参。缓存摘要涵盖三件套、转换配置、包版本和生成代码；检查地形层长度、PCD/PGM 完整性及输出摘要。转换失败、超时或取消不发布不完整结果，不允许导航。新行为仅由 UGV_003 的 `adapter.native_map.enabled` 开启，网络协议和端口不变。

## 验证记录

- 本机：任务控制 115 项、定位 35 项、UGV_003 profile 6 项通过；建图相关回归通过。
- 端侧：集成回归 18 项、导航适配器 21 项、控制权 12 项通过；launch 解析、bash 语法、CCS 集成包编译通过。
- 实机：雷达身份和新鲜点云、底盘遥测、重复启动拒绝、真实建图/定位互斥、静态地图保存及原生转换、下载三件套派生地形、NDT 定位、原生导航组件、速度接线、控制权空闲归还、急停/复位通过。
- 相机/SRT 可独立启动停止；默认完整一键启动含视频进入待命后正常退出。降级、截断产物、缓存失效、TF 陈旧/重复、错误进程归属均有回归覆盖。
- 无运动验收没有发布导航目标；监测到的非零受保护速度命令为 0。运动能力、地面站端完整 UI 任务执行及长期运行不在此次实测结论内。
- 端侧旧仓库全套任务测试曾因缺少通用示例配置和地面站契约夹具出现 25 个环境错误；未以这些失败冒充通过。相关端侧测试按可用模块执行，本机完整任务控制回归通过。

关键证据在本目录 `evidence/`；完整日志在端侧 `log/acceptance-*`。`deployment-files.json` 列出实际部署源码/配置的原始及最终摘要、是否新增。`device-adaptation.patch` 是对端侧旧版本的精确补丁，避免直接用本机较新公共包覆盖设备。

## 回滚

先 Ctrl+C 停止本次启动并确认算法/视频已退出。备份目录记为：

```bash
W=/home/nrc19/ccs_edge_ws
B=$W/backups/ugv003_v60_20260923
```

1. 依据 `deployment-files.json` 中 `status=modified` 的相对路径，从 `$B/ccs-before.tar.gz` **逐项恢复**到 `$W`；不要解压覆盖整个 src，以免覆盖后来其他工作的修改。`status=added` 的文件经摘要确认仍为本次版本后逐项移除；只清理空目录，保留 maps/log/backups 中的验收与用户数据。
2. 原生文件恢复：

```bash
cp "$B/MID360_config.json" /home/nrc19/livox_fastlio/src/livox_ros_driver2/config/MID360_config.json
cp "$B/FAST_LIO-CMakeLists.txt" /home/nrc19/livox_fastlio/src/FAST_LIO/CMakeLists.txt
cp "$B/fastlio_mapping.before" /home/nrc19/livox_fastlio/devel/lib/fast_lio/fastlio_mapping
```

3. 网络恢复（连接详情见 `$B/eth0-before.txt`）：

```bash
sudo nmcli connection modify uuid 347390f9-52b0-3fde-9431-f920f42e1756 ipv4.addresses '192.168.1.5/24,192.168.8.119/24' ipv4.never-default yes
sudo nmcli device reapply eth0
```

4. 重新加载 Noetic/原生环境，仅在 CCS 内重新生成 catkin 环境和需要的公共包构建产物；不要在原生工作区重建。回滚会恢复旧启动链的历史问题，也会让新雷达网络配置失效，这是回滚到原始状态的预期结果。

没有创建 Git 提交或推送，也没有增加开机自启服务。
