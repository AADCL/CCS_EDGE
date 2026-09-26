# 实时建图预览契约

配套平台 CCS 0.29.1、epgeneral_map_stream 0.14.1、epgeneral_device_config 0.3.1。

## 数据与预算

预览传输仍为 ccs-map-stream-v2 的 PCD binary XYZ float32 HTTP 分片；UDP 只携带描述符、ACK 与状态。每个点占 12 字节。共享配置与八份 profile 的 preprocess.voxel_size_m=0.10、sample_window_seconds=1.0；先按时间戳匹配位姿、保留坐标变换，再对窗口和输出体素去重。超预算时按体素键排序等间隔保留代表点，按实际 PCD 头核算数量。

limits.max_preview_fragment_bytes=500000，新增 limits.max_preview_bytes_per_second=500000（旧 schema 6 配置缺失时采用该默认值）。每台设备任意连续一秒内发送的预览 HTTP 正文不超过 500,000 字节，包括 PCD 头、重复下载、并发下载和 Range 下载；TCP/IP、HTTP 头及控制消息不计入，完整地图成果 ZIP 不使用预览预算。最终地图的分辨率、完整性与保存流程不受预览采样影响。

## 节奏与拥塞

新分片发布间隔至少一秒，不补发积压窗口；填满点缓存也不提前发布。待生成窗口只保留最新一个，未确认文件最多四个（配置可以进一步降低）。旧描述符重发优先最新分片，ACK 只表示平台已处理该预览、端侧可以释放文件，不表示该分片一定显示成功。平台可主动跳过过期/旧/失败分片并 ACK；成功计数和最后成功时间只由完整下载并校验、解析成功的点云更新。在读文件延迟到读取结束才删除。

平台预览连接超时 2 秒、读取无进展超时 2 秒、下载总期限 3 秒、排队最大年龄 3 秒、单次尝试。等待时间还会扣减本次下载可用期限。慢响应头、慢正文和会话取消均会中断预览连接；只保留一个最新待下载分片，重复和乱序旧通知不刷新年龄。GUI 合并待显示结果，停止和切换会话清理任务。每五秒 preview_summary 汇总跳过数量、成功字节数、最近耗时及成功时间。

完整点云中断 10 秒告警；连续 30 秒无完整点云且心跳中断至少 5 秒才失败。最终成果仍使用连接 5 秒、读取 30 秒、最多三次尝试和生成等待 600 秒。带宽低于所需数据量时允许降低实际显示帧率，不能保证任意网络条件下每秒收到完整预览。

## 升级与排查

先部署端侧包及对应 profile，再使用新版平台；修改 YAML/JSON 后重启相关进程。协议与配置 schema 未改变，旧端侧超过新版平台分片上限时需先升级；新版端侧也可由旧平台读取，但旧平台仍可能积压。现场排查同时查看 PCD 实际字节数、下载耗时、preview_summary、心跳和 CLOUD_WARNING，不通过扩大队列掩盖链路拥塞。

代码测试与本机 HTTP/Qt 联调不替代 QRD_002 实机无线验收。本次不自动部署设备。回滚时同时恢复两端原配置及相应软件版本；平台发行源码锁与子模块必须指向同一端侧提交。

## 验收记录

Windows/Python 3.10.19：建图包 104 项、仓库级配置与 profile 135 项测试通过（合计 239 项，24 项按平台条件跳过）。[逐套件结果](validation/realtime-map-preview/tests.json)。命令：设置 `PYTHONPATH=EPGeneral_map_stream/src` 后执行 `python -m unittest discover -s EPGeneral_map_stream/test -q`，再执行 `python -m unittest discover -s tests -q`。并发 HTTP、Range、发布节奏及在读文件删除由新增 `test_preview.py` 验证。原生 Qt/VisPy 联调记录在配套平台 PR 中；本次未部署实机。
