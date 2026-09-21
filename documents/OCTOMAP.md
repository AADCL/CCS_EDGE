# OT 占据图接入（map_stream 0.14.0 / device_config 0.1.3）

本包编排设备已有建图/转换包，不新增点云生成 OT 的算法。成果要求原始 PCD 加 PGM/YAML 或 OT，允许同时提供；OT 是 OctoMap 完整树，支持 OcTree 和 ColorOcTree，不接收改名的 BT。

## 配置

既有配置继续有效。共享配置和八套设备 profile 的 artifacts 增加：

```yaml
artifacts:
  pcd_path: "{session_dir}/map.pcd"
  ot_path: "{session_dir}/map.ot"
  # source_ot_path: "/现场核实的绝对路径/实际文件名.ot"
```

ot_path 必须位于本次 session_dir 内、与 pcd_path 同目录。source_ot_path 可包含已有模板字段（例如 session_dir、map_name），实际文件名须由设备导出包核实。省略时查找已有适配器的本次地图目录中的 map.ot：Go2 使用配置的源 PCD 目录，Scout/managed 使用带 map_name 的地图目录，Ground-Air 使用原生保存目录，UAV 使用转换后会话目录。不存在 OT 时原 PGM 路径不变。

若需要调用已安装导出器，可显式配置以下两个 argv 列表。占位内容必须替换为已核实命令，示例不是已部署功能：

```yaml
integrations:
  occupancy:
    check_command: ["/核实后的导出器", "--check"]
    command: ["/核实后的导出器", "{pcd_path}", "{ot_path}"]
```

检查命令应只验证依赖，不启动建图；生成命令须等待成果写入完成后返回。通过 argv 调用，不经过 shell 展开。支持既有 session_dir、session_log_dir、map_name、PCD/PGM/YAML 等字段及新增 ot_path。

Go2 配置 occupancy 后替代原 PGM 生成步骤和专属检查，可删除 integrations.pgm 与 PGM/YAML 路径配置；未提供的 PGM 路径使用会话内默认值但不要求文件。Scout/managed/Ground-Air 保留原生 PCD finalize/save，再执行配置的占据图导出器，不强求原生保存阶段已有占据图。UAV 保留其已验证的原生 PCD 坐标转换和现有 PGM 导出，再执行可选导出器。

导出器可直接写入会话目标，也可写入 source_ot_path。OT 与会话 PCD 必须处于同一 artifacts.frame 坐标系；例如原生 camera_init 与转换后的 odom 不得混放。不同坐标系的 OT 需要已有设备功能包先完成转换，本次不猜测转换命令。

## 新鲜度与打包

建图开始前记录源/目标占据图指纹；按会话开始时间、大小、mtime、inode、SHA-256 检查变化。适配脚本复制保留源时间戳，复制操作不能使历史文件变新。历史会话文件不进入包；只删除本次 session_dir 中对应无效的暂存副本，不删除原始来源。

OT 与其他成果经过稳定性等待、非空/非符号链接/总大小检查，OT 检查完整树头、节点数、有限概率、深度及文件长度。PGM/YAML 成对时执行原专属检查；只有 OT 时不读取 YAML。清单增加 files.ot 的 path、byte_count、sha256，存放位置与原始 PCD 相同，ZIP 使用文件 basename。

Go2 导出包装器归档旧源文件（包括 OT），先清理生成目标；失败恢复旧来源。其余原生适配器保留现有地图会话目录和保存协议，最终会话新鲜度闸门统一生效。

## 兼容

平台 prepare_mapping.payload.artifact_formats 为支持格式列表；旧平台缺失时等价 `["pcd","pgm","yaml"]`。新平台声明 OT 后可接收全部组合。未协商 OT 时只发送旧三件套；OT-only 明确报 `OT was not negotiated`。旧平台不会收到额外 OT 清单角色。

协议 ID ccs-map-stream-v2、manifest schema 1 和现有端口不变。新增配置未启用任何现场进程；部署前验证真实导出器、文件名、坐标系，并使用本机型既有部署流程。

## 验证范围

本次在 Windows 执行包内单元测试及平台真实 ZIP 合同测试；ROS/设备原生功能包的实机保存、飞行/底盘控制未执行。Linux/ROS 依赖测试跳过项保留在测试报告。平台使用官方 OctoMap v1.10.0 样本并以官方库回读平台输出。

2026-09-21 验证：仓库测试 121 项（103 通过、18 跳过），建图包测试 96 项（90 通过、6 跳过）。首次文档覆盖检查发现新增字段/文档清单未登记，补齐后相关 9 项复测通过。修改的三个 Bash 脚本通过 `bash -n`。跳过项依赖 Linux/ROS，本次未在 Windows 上宣称设备联调通过。
