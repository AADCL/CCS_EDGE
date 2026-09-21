# epgeneral_uav_integration 0.1.0

UAV_001 的 CCS direct 任务适配、原生算法阶段管理和地图坐标导出。依赖设备原生 ducted_bringup、ducted_offboard、fast_lio_sam；不复制或修改原生控制器和标定。

入口见[UAV 部署指南](../../../documents/devices/uav/DEPLOYMENT_GUIDE.md)、[使用手册](../../../documents/USER_MANUAL.md)和[接口参考](../../../documents/INTERFACE_REFERENCE.md)。

UAV profile 无参数启动和显式 --mapping 均进入独立建图模式，只允许原生建图、地图保存和重定位，任务适配器及原生控制器保持禁用；--static 为纯观察模式，建图、重定位和飞行均禁用。只有 --flight 开放任务准备、定时自动起飞、建图、重定位和原生控制。原生控制器是唯一 MAVROS setpoint 发布者。完成/取消保持悬停，急停请求降落并等待落地锁定。定位丢失或适配器租约超时闭锁，禁止自动续飞。

地图输出采用实测 odom←camera_init 变换；二维 PGM 仅供显示。direct 无自动避障。单元测试位于 test/test_core.py，真实 ROS 隔离测试为 test/isolated_acceptance.py 和 test/maps_isolated.py，仅可在设备开发环境、独立 master 端口运行。
