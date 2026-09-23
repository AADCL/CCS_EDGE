# EPGeneral GO2 Integration

Version: 0.1.3. ROS package: `epgeneral_go2_integration`.

[User manual](../../../documents/USER_MANUAL.md#documents-user-manual-md) | [Interface reference](../../../documents/INTERFACE_REFERENCE.md#documents-interface-reference-md)

This package connects the CCS lifecycle to the native GO2 Noetic packages.
The `go2_robot2` profile targets `unitree@192.168.50.111`; `go2_robot3` targets
`unitree@192.168.50.112`. It does not vendor or rebuild the native navigation
workspace and does not change the older `go2_edu` deployment profile.

## Ownership

Use the root script supplied by the selected `deploy/<profile>` for normal operation. It
starts Livox, the initially disabled real SDK bridge, RGB camera and CCS
communication services. Mapping and localization are started only by their CCS
coordinators. Do not run native `run_go2 mapping/navigation` concurrently.

`bringup.launch` remains an explicit all-in-one integration entrypoint for
launch composition. It is not called by the root script, must not run alongside
that script, and does not provide its preflight or owned-process monitoring.

## Task Launch Contracts

| Entry | Parameters | Native work |
| --- | --- | --- |
| `mapping_fast_lio.launch` | `lock_file` | Exclusive mapping guard and `go2_bringup/fast_lio.launch` |
| `navigation_guard.launch` | `lock_file` | Acquires the exclusive navigation slot before the next stage |
| `navigation.launch` | required `map_name`, `map_root`, `extrinsics_file` | FAST-LIO, core adapters, NDT localization and navigation stack |
| `bringup.launch` | `profile_dir`, `network_interface`, `ground_station_ip`, `log_root`, `telemetry_namespace`, `camera_serial`, `color_fps` | Persistent devices and CCS services only |

The relocalization coordinator must start `navigation_guard.launch` before
`navigation.launch` and stop the stages in reverse order. Navigation deliberately
excludes Livox and SDK/control startup because those belong to the root script.
The mapping prerequisites live in the map-stream package to preserve its existing
launch contract and `/go2_map_accumulator/save_map` service name.

The guard rejects pre-existing conflicting nodes without stopping them. Mapping
allows its own FAST-LIO sibling only when the ROS node PID proves the same launch
parent; failed PID lookups remain fail-closed. Lock release checks an ownership
token so an exiting process cannot remove a later owner's lock.

## Integration Boundaries

- FAST-LIO remains on `/livox/lidar` and `/livox/imu`.
- CCS mapping preview uses raw `lio_odom` poses; exported accumulated PCD is in
  `odom`. The profile records these distinct frames explicitly.
- Native localization produces provisional identity TF before localization
  succeeds. `/localization/ok` freshness is therefore required independently of TF.
- Task reset is `std_srvs/Trigger`; SDK enable is `std_srvs/SetBool`.
- Native extrinsics and hardware safety settings stay in `go2_nav_ws`.

For Robot2, see the [deployment guide](../../../documents/devices/go2/DEPLOYMENT_GUIDE.md#deploy-go2-robot2-deployment-md),
[measured validation results](../../../documents/devices/go2/DEPLOYMENT_GUIDE.md#deploy-go2-robot2-validation-md), and
[migration/rollback commands](../../../documents/devices/go2/DEPLOYMENT_GUIDE.md#deploy-go2-robot2-validation-md-%E8%BF%81%E7%A7%BB%E4%B8%8E%E5%9B%9E%E6%BB%9A%E7%94%A8%E6%B3%95).
For Robot3, see the [deployment guide](../../../documents/devices/go2/DEPLOYMENT_GUIDE.md#deploy-go2-robot3-deployment-md) and
[validation record](../../../documents/devices/go2/DEPLOYMENT_GUIDE.md#deploy-go2-robot3-validation-md) for device-specific setup,
observed results, and rollback instructions.

## 0.1.3 camera configuration

The optional camera uses `epgeneral_video_srt/camera.launch` with the selected profile config directory. Driver package, RGB settings and serial environment mapping live in shared `video.yaml`. Empty `camera_serial` / `color_fps` launch arguments preserve the YAML values; explicit values override capture args, and configured nonempty environment mappings take final precedence. Requires video 0.2.0 and device config 0.3.0. See [video migration](../../../documents/VIDEO_SRT_GENERIC.md).
