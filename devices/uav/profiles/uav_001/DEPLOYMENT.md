# UAV_001 端侧启动说明

工作空间：`/home/nrc/ccs_edge_ws`。本机 profile 使用与 UGV_004 相同的根目录启动形式。

## 启动

先确认地面站 `192.168.50.101` 在线，再执行：

```bash
cd /home/nrc/ccs_edge_ws
./start_ccs_edge_dev.sh --check
./start_ccs_edge_dev.sh
# 前台按 Ctrl+C 有序停止
```

`--check` 不启动节点，不创建运行日志或 PID 文件。无参数启动为安全的 mapping 模式：
允许建图、保存和重定位，飞行任务与控制器保持禁用。

UAV 专属模式：

```bash
./start_ccs_edge_dev.sh --static
./start_ccs_edge_dev.sh --mapping
./start_ccs_edge_dev.sh --flight
```

`--flight` 只允许在独立实飞验收后使用。正常停止使用 `Ctrl+C`；空中或控制状态未知时
不得强制结束控制器，不得使用 `killall`、`pkill` 或删除状态文件。

## 重定位与任务运行

重定位和任务功能已于 2026-09-22 启用。需要同时接收重定位和任务指令时使用：

```bash
cd /home/nrc/ccs_edge_ws
./start_ccs_edge_dev.sh --check
./start_ccs_edge_dev.sh --flight
```

无参数启动仍进入 `mapping` 安全模式，并会关闭任务执行权限。`--flight` 只开放阶段管理和
任务执行通道，不会自行解锁或起飞；任务仍需通过活动地图、定位新鲜度、飞控已连接、已落地、
未解锁及无急停锁等门禁。重启后需要任务功能时必须再次显式使用 `--flight`。

## 文件和日志

- 运行配置：`config/uav_001/*.yaml`
- 启动 launch：`launch/uav_001_bringup.launch`
- 启动助手：`scripts/`
- 会话日志：`logs/<UTC时间_纳秒_PID>/`
- 最新日志：`logs/latest`
- PID 和单实例锁：`run/managed`
- 地图、任务和安全状态：`maps`、`mission`、`run/state`

故障先查看 `logs/latest/startup.log`、`runtime_monitor.log`、`bringup.log` 和对应组件日志。
就绪检查：

```bash
source /home/nrc/ccs_edge_ws/devel/setup.bash --extend
python3 /home/nrc/ccs_edge_ws/scripts/readiness.py
```

不得用模拟位姿替代生产数据。静态检查不表示设备可实飞；direct 控制不提供自动避障。
