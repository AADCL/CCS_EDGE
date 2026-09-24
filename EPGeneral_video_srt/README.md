# epgeneral_video_srt

当前版本：**0.2.0**。ROS Noetic 的通用视频输入与 H.264/MPEG-TS/SRT Listener 输出包。

[使用手册](../documents/USER_MANUAL.md#documents-user-manual-md) · [接口参考](../documents/INTERFACE_REFERENCE.md#documents-interface-reference-md) · [通用化、迁移与验证](../documents/VIDEO_SRT_GENERIC.md)

设备身份、相机驱动、图像话题、RTSP 地址及硬件预加载路径均由 `EPGeneral_device_config` 提供。功能包不携带运行 YAML，不按设备名或相机型号选择行为。支持 `ros_image`、`ros_compressed`、`rtsp` 三种输入；均输出 baseline H.264、MPEG-TS、SRT Listener。

## 安装

Ubuntu 20.04 / ROS Noetic / GStreamer 1.16+：

```bash
sudo apt install ros-noetic-cv-bridge ros-noetic-image-transport libopencv-dev \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
  python3-yaml python3-gi gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0
cd ~/ccs_edge_ws
catkin_make
source devel/setup.bash
```

相机驱动按设备安装在原生工作空间，不作为本包的固定依赖。

## 配置与启动

先按部署脚本安装 profile 到共享配置包及工作空间配置目录，然后明确选择实际运行副本：

```bash
CFG="$(rospack find epgeneral_device_config)/config"
rosrun epgeneral_video_srt video_srt_node.py --config-dir "$CFG" --check-config
rosrun epgeneral_video_srt video_srt_node.py --config-dir "$CFG" --check-runtime
# 仅当需要本包管理相机驱动时，在独立终端/已有进程监督器中执行：
roslaunch epgeneral_video_srt camera.launch config_dir:="$CFG"
roslaunch epgeneral_video_srt epgeneral_video_srt.launch config_dir:="$CFG"
```

`config_dir` 同时加载 `device.yaml` 和 `video.yaml`；也可传完整的 `device_config_file`、`video_config_file` 文件对。两种方式互斥，空参启动失败，不会隐式使用样例设备。配置修改后需重启。

`enabled: false` 使视频和相机入口直接成功退出。`capture.enabled: false` 仅关闭可选相机入口，视频仍可订阅外部输入。视频节点本身不启动相机驱动。

`rtsp_srt.launch`、`epgeneral_realsense_d435i_srt.launch` 保留为同一通用入口的兼容别名，模式完全由 YAML 决定。`rtsp_srt_node.py` 为同一 CLI 的兼容脚本；旧的仅 ROS 私有参数调用须迁移到配置文件。

## 运行状态与边界

默认状态话题 `/epgeneral_video_srt/status` 发布 `std_msgs/String` JSON：设备 ID、输入模式、就绪状态、帧数、帧龄、重连次数、错误类别。ROS 后端帧数随管线重建归零；RTSP 后端累计到进程退出。`ready` 表示近期输入已进入管线，不代表远端播放器已经解码。

输入超时或运行中管线错误会按配置间隔重建；ROS 后端初始配置、插件或 Listener 启动失败直接退出交给监督器处理。RTSP 连接失败自动重试。状态日志隐藏 RTSP URI，诊断配置输出也隐藏该值；不要把含密码 URI 直接写入版本库。

SRT 延迟以毫秒直接设置 GStreamer `srtsink.latency`，不再在 GStreamer URI 中乘 1000。播放器的 FFmpeg SRT URI 使用其自身微秒单位，例如：

```bash
ffplay "srt://127.0.0.1:9000?mode=caller&transtype=live&latency=120000"
```

分辨率须为偶数，旋转支持 0/180 度；输入不足时不会在 ROS 后端补帧。端侧按配置开放 SRT UDP 端口。当前范围不包含音频、录像、认证、加密和多客户端分发。
