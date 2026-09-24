# 视频功能包通用化与迁移

版本：epgeneral_video_srt **0.2.0**、epgeneral_device_config **0.3.0**、epgeneral_go2_integration **0.1.3**。

## 配置职责

运行配置仍集中于 `EPGeneral_device_config/config`。仓库中的 `devices/*/profiles/*/config` 是设备部署源，使用现有 profile 安装脚本复制到共享配置包和工作空间 `config/<profile>`。两份副本不会自动热同步；启动时显式指定其中一份，修改后重启。

- `device.yaml` schema 1：唯一设备 ID/IP。
- `video.yaml` schema 2：启用开关、输入模式、图像/RTSP 来源、编码、SRT、运行状态及可选驱动。
- `config/templates/video_generic`：使用文档专用地址的通用起点；复制后填写实际身份和来源，不直接部署。

功能包代码不包含 QRD/UGV/UAV/AGV 分支、本地用户目录或固定相机地址。保留旧 RealSense launch 名称仅为兼容，不决定模式。身份通过私有参数传给 ROS 图像后端，不再读写全局 `/edge_device`，多个实例需选择不同节点名、状态话题和 SRT 端口。

## schema 2 示例

```yaml
schema_version: 2
enabled: true
input_mode: ros_image
image_topic: /devices/{device_id}/camera/image_raw
output_width: 640
output_height: 480
framerate: 30
bitrate_kbps: 2000
rotation_degrees: 0
srt_bind_address: 0.0.0.0
srt_port: 9000
srt_latency_ms: 120
frame_timeout_seconds: 5.0
runtime:
  status_topic: "~status"
  reconnect_interval_seconds: 3.0
  decoder_preload: []
capture:
  enabled: false
```

`ros_compressed` 使用 `sensor_msgs/CompressedImage` 和压缩图像话题。若显式提供 `image_message_type`，必须与模式一致。话题仅支持 `{device_id}` 占位符。

RTSP 模式将 `input_mode` 改为 `rtsp`，设置 `rtsp_uri` 或 `rtsp_uri_env` 二选一，并设置 `rtsp_codec: h264|h265`、`rtsp_transport: tcp|udp`、`rtsp_latency_ms`。例如 `rtsp_uri_env: CCS_CAMERA_RTSP_URI` 从运行环境读取含凭据地址，不在日志打印。RTSP 解码后统一按配置缩放、限帧、旋转、编码为 H.264。硬件确有需要时才填写 `runtime.decoder_preload` 的绝对库路径，通用模板为空。

平铺的视频字段保留，便于旧部署迁移；不额外引入第二套嵌套字段。schema 1/缺省 schema 的旧图像配置继续接受；旧 RTSP 配置应已显式声明 `input_mode: rtsp`。`deployment.enabled` 为旧开关兼容项，与新 `enabled` 冲突时拒绝启动。新配置的模式必须显式填写。

## 可选相机驱动

```yaml
capture:
  enabled: true
  package: camera_driver
  launch: rgb.launch
  args:
    color_width: 640
    color_height: 480
    color_fps: 30
  arg_env:
    serial_no: CCS_CAMERA_SERIAL
```

`camera.launch` 根据上述字段以 argv 执行 roslaunch，不执行 shell 字符串，不守护化。现有启动监督器仍负责进程组、就绪检查和停止顺序。只有选择此入口才启动相机；外部驱动仍可独立提供图像。运行前必须 source 实际驱动工作空间。

Go2 robot2/robot3 的 RGB 驱动参数、Scout/Wheeltec 的驱动入口、Ground-Air A8 的 IP/话题已迁入配置。保留 Go2 `CCS_D435_SERIAL` 环境变量，通过 `capture.arg_env` 注入；未设置则自动选相机。Go2 集成 launch 保留 `camera_serial` 和 `color_fps` 显式覆盖，空值采用 YAML；同名非空环境映射最终优先。旧 go2_edu 的原生 bringup 仍可自带驱动，不能同时再启动 camera.launch。

设备专用脚本中的硬件就绪检查仍属于设备集成层；更换驱动话题时需要一起适配这些检查。公共视频包本身不读取这些固定话题。

## 已迁移 profile

| profile | 输入 | 输出 | 驱动/差异 |
| --- | --- | --- | --- |
| go2_edu | ROS Image | 640×480@30 | RealSense；保留原生 bringup 管理方式 |
| go2_robot2 | ROS Image | 640×480@30 | RealSense RGB，USB3 |
| go2_robot3 | ROS Image | 640×480@15 | RealSense RGB，USB2 |
| scout_mini | ROS Image | 640×480@30 | Scout D435I launch |
| wheeltec_r550p | ROS Image | 640×360@30 | Gemini 336L，输出旋转 180° |
| wheeltec_r550p_02 | ROS Image，禁用 | 640×480@30 | enabled=false，保留占位 |
| ground_air_agv | ROS Image | 1280×720@30 | A8 ROS 驱动 |
| uav_001 | RTSP H.265 | 640×480@15 | A8 RTSP；libgomp 预加载只在此配置 |

保留各 profile 原有身份、码率、端口和来源值。SRT 统一 Listener，地面站 Caller 的连接方向与 H.264/MPEG-TS 格式不变。

## 迁移和只读检查

1. 安装新版视频包和共享配置包；Go2 集成入口同时更新至 0.1.3。
2. 使用现有部署脚本安装目标 profile；核对实际运行目录的 device.yaml 和 video.yaml。
3. 所有视频入口显式传 config_dir，或完整的 device/video 文件对；仅传一个文件不再隐式读取样例身份。
4. 按实际模式运行以下预检，成功后再由原有启动入口运行。

```bash
CFG="$HOME/ccs_edge_ws/config/<profile>"
rosrun epgeneral_video_srt video_srt_node.py --config-dir "$CFG" --check-config
rosrun epgeneral_video_srt video_srt_node.py --config-dir "$CFG" --check-ros
rosrun epgeneral_video_srt video_srt_node.py --config-dir "$CFG" --check-runtime --check-camera
roslaunch --files epgeneral_video_srt epgeneral_video_srt.launch config_dir:="$CFG"
```

check-config 只读 YAML；check-ros 解析输入消息类型；check-runtime 另检查 GStreamer 元素和预加载库；check-camera 用 roslaunch --files 解析选定驱动入口。这些检查不启动节点、相机或 SRT，也不证明硬件在场或流可解码。enabled=false 时跳过运行依赖。

回滚时同时还原视频代码、共享配置与设备启动入口，避免新 camera.launch 被旧包引用。已有旧配置字段仍可读，但旧功能包不具备新 enabled 和 capture 语义。不要只回退单个 launch。

## 验证

配置单元测试覆盖三种模式、旧格式、非法参数、脱敏、显式路径、禁用模式、相机 argv 和进程替换。仓库测试核对全部 profile 参数、版本、文档链接和原有设备就绪/控制门顺序。

2026-09-23 验证：Windows 仓库回归 123 项通过（18 项平台条件跳过），各包回归 420 项通过（7 项条件跳过，含视频配置 24 项）。QRD_003（ARM64、ROS Noetic、GStreamer 1.16.3）独立 /tmp 工作空间完成 catkin_make 与 install。开发空间和安装空间各完成四条回环：ROS Image、CompressedImage、RTSP H.264、RTSP H.265 → H.264/MPEG-TS/SRT；安装空间四条链路均验证断流恢复，ROS 两条验证 180° 图像旋转。

可选回环测试入口：`EPGeneral_video_srt/test/integration_loopback.py`（不随普通单元测试自动运行）。它要求 `ROS_MASTER_URI=http://127.0.0.1:11331`、独立 ROS master 和 loopback ROS_IP，SRT 使用 19101..19104、合成 RTSP 使用 19203..19204。测试额外需要 GstRtspServer GI、OpenCV Python、numpy 和 x265enc；仅测试服务器需要这些依赖。ARM64 存在 libgomp TLS 问题时，在测试环境中设置 `CCS_VIDEO_TEST_PRELOAD` 和测试进程 `LD_PRELOAD`，脚本会清除被测进程继承值并从临时 video.yaml 重新加载，验证配置确实生效。测试不替换已部署功能包，不运行真实相机或机器人控制。真实相机恢复、现场网络和硬件驱动需在下次实际部署时验收。
