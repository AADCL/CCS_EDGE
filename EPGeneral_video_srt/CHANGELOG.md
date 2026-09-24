# Changelog

## [0.2.0] - 2026-09-23

- Unified ROS Image, CompressedImage and RTSP inputs under explicit shared device/video configuration.
- Added validated schema 2, effective disable switches, redacted preflight, configurable status and reconnect behavior.
- Moved optional camera launch arguments and decoder preload into shared profiles; retained legacy launch aliases.
- Removed global device identity parameters and fixed GStreamer SRT latency to use its millisecond property.
- Added monotonic ROS frame pacing/timestamps, bounded pipeline queues and clean pipeline recovery.
- Added generic templates, migration documentation and configuration/runtime regression coverage.

## [0.1.2] - 2026-09-16

- Added an optional, validated 180-degree rotation stage before SRT encoding.
- Configured the upside-down UGV_003 Gemini 336L profile to rotate only its streamed video.

## [0.1.1] - 2026-09-02

- Centralized runtime configuration in `epgeneral_device_config`.
- Removed package-local camera profile YAML files without changing the SRT pipeline.

## [0.1.0] - 2026-08-18

- Added configurable raw and compressed ROS image subscriptions.
- Added baseline H.264/MPEG-TS encoding and SRT Listener output on UDP 9000.
- Added frame watchdog, required GStreamer element checks, and pipeline diagnostics.
- Improved startup diagnostics for missing SRT plugins and normalized wildcard Listener URI
  generation to `srt://:<port>?mode=listener`.
- Fixed SRT latency conversion from configured milliseconds to URI microseconds and mirrored
  fatal startup errors to stderr for roslaunch diagnostics.
