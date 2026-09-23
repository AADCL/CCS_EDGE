#include <arpa/inet.h>

#include <atomic>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <regex>
#include <vector>

#include <cv_bridge/cv_bridge.h>
#include <gio/gio.h>
#include <gst/app/gstappsrc.h>
#include <gst/gst.h>
#include <image_transport/image_transport.h>
#include <ros/ros.h>
#include <sensor_msgs/CompressedImage.h>
#include <sensor_msgs/Image.h>
#include <std_msgs/String.h>
#include <chrono>
#include <cmath>

class VideoSrtNode {
 public:
  explicit VideoSrtNode(std::uint64_t reconnects)
      : nh_(), pnh_("~"), image_transport_(nh_), pipeline_(nullptr), appsrc_(nullptr), srt_sink_(nullptr),
        bus_(nullptr), sequence_(0), received_frame_(false),
        shutting_down_(false), failed_(false), reconnects_(reconnects) {
    try {
      loadConfiguration();
      gst_init(nullptr, nullptr);
      validateGstreamerPlugins();
      startPipeline();
      pipeline_started_ = std::chrono::steady_clock::now();
      last_frame_time_ = ros::WallTime::now();
      status_publisher_ = pnh_.advertise<std_msgs::String>(
          status_topic_[0] == '~' ? status_topic_.substr(1) : status_topic_, 1, true);
      if (image_message_type_ == "sensor_msgs/Image") {
        image_subscriber_ = image_transport_.subscribe(
            image_topic_, 1, &VideoSrtNode::imageCallback, this,
            image_transport::TransportHints("raw"));
      } else {
        compressed_subscriber_ = nh_.subscribe(
            image_topic_, 1, &VideoSrtNode::compressedImageCallback, this);
      }
      frame_watchdog_ = nh_.createWallTimer(
          ros::WallDuration(1.0), &VideoSrtNode::watchdogCallback, this);
      ROS_INFO_STREAM("epgeneral_video_srt ready device_id=" << device_id_
                      << " listener=srt://" << device_ip_ << ":" << srt_port_
                      << " image_topic=" << image_topic_ << " image_message_type="
                      << image_message_type_ << " output=" << output_width_ << "x"
                      << output_height_ << " rotation=" << rotation_degrees_
                      << "deg latency_ms=" << srt_latency_ms_);
    } catch (...) {
      shutdownPipeline();
      throw;
    }
  }

  bool failed() {
    GstMessage* message;
    while (bus_ && (message = gst_bus_pop(bus_)) != nullptr) {
      busMessage(bus_, message, this);
      gst_message_unref(message);
    }
    return failed_;
  }

  ~VideoSrtNode() { shutdownPipeline(); }

  void shutdownPipeline() {
    shutting_down_ = true;
    frame_watchdog_.stop();
    image_subscriber_.shutdown();
    compressed_subscriber_.shutdown();
    if (status_publisher_ && ros::ok()) {
      failed_ = true;
      watchdogCallback(ros::WallTimerEvent());
    }
    if (appsrc_ != nullptr) gst_app_src_end_of_stream(GST_APP_SRC(appsrc_));
    if (pipeline_ != nullptr) gst_element_set_state(pipeline_, GST_STATE_NULL);
    if (bus_ != nullptr) gst_object_unref(bus_);
    if (appsrc_ != nullptr) gst_object_unref(appsrc_);
    if (srt_sink_ != nullptr) gst_object_unref(srt_sink_);
    if (pipeline_ != nullptr) gst_object_unref(pipeline_);
    ROS_INFO("epgeneral_video_srt stopped");
  }

 private:
  void loadConfiguration() {
    if (!pnh_.getParam("device_id", device_id_) || !std::regex_match(device_id_, std::regex("[A-Za-z][A-Za-z0-9_-]*")))
      throw std::runtime_error("private device_id is required; use the configured launcher");
    if (!pnh_.getParam("device_ip", device_ip_) || !validIpAddress(device_ip_))
      throw std::runtime_error("private device_ip must be a valid IP address");
    pnh_.param<std::string>("status_topic", status_topic_, "~status");
    if (status_topic_.empty()) throw std::runtime_error("status_topic is required");
    pnh_.param<std::string>("image_topic", image_topic_, "/camera/image_raw");
    pnh_.param<std::string>("image_message_type", image_message_type_, "sensor_msgs/Image");
    pnh_.param<std::string>("srt_bind_address", bind_address_, "0.0.0.0");
    pnh_.param("srt_port", srt_port_, 9000);
    pnh_.param("srt_latency_ms", srt_latency_ms_, 120);
    if (!pnh_.getParam("output_width", output_width_)) pnh_.param("image_width", output_width_, 640);
    if (!pnh_.getParam("output_height", output_height_)) pnh_.param("image_height", output_height_, 480);
    pnh_.param("framerate", framerate_, 30);
    pnh_.param("bitrate_kbps", bitrate_kbps_, 2000);
    pnh_.param("rotation_degrees", rotation_degrees_, 0);
    pnh_.param("frame_timeout_seconds", frame_timeout_seconds_, 5.0);
    if (image_topic_.empty() || image_topic_[0] != '/')
      throw std::runtime_error("image_topic must be an absolute ROS topic");
    if (image_message_type_ != "sensor_msgs/Image" &&
        image_message_type_ != "sensor_msgs/CompressedImage")
      throw std::runtime_error("image_message_type must be sensor_msgs/Image or sensor_msgs/CompressedImage");
    if (!validIpAddress(bind_address_) || srt_port_ < 1 || srt_port_ > 65535 ||
        srt_latency_ms_ < 20 || srt_latency_ms_ > 8000 || output_width_ < 16 || output_width_ > 3840 || output_width_ % 2 ||
        output_height_ < 16 || output_height_ > 2160 || output_height_ % 2 || framerate_ < 1 || framerate_ > 120 ||
        bitrate_kbps_ < 100 || bitrate_kbps_ > 20000 || !std::isfinite(frame_timeout_seconds_) || frame_timeout_seconds_ <= 0.0)
      throw std::runtime_error("video or SRT numeric configuration is out of range");
    if (rotation_degrees_ != 0 && rotation_degrees_ != 180)
      throw std::runtime_error("rotation_degrees must be 0 or 180");
  }

  static bool validIpAddress(const std::string& address) {
    struct in_addr ipv4;
    struct in6_addr ipv6;
    return inet_pton(AF_INET, address.c_str(), &ipv4) == 1 ||
           inet_pton(AF_INET6, address.c_str(), &ipv6) == 1;
  }

  std::string listenerUri() const {
    std::string host = bind_address_;
    if (host.find(':') != std::string::npos) host = "[" + host + "]";
    return "srt://" + host + ":" + std::to_string(srt_port_) +
           "?mode=listener&transtype=live";
  }

  void validateGstreamerPlugins() const {
    const char* elements[] = {"appsrc", "videoconvert", "x264enc", "h264parse", "mpegtsmux", "srtsink"};
    for (const char* name : elements) {
      GstElementFactory* factory = gst_element_factory_find(name);
      if (factory == nullptr) {
        gchar* version = gst_version_string();
        const std::string message =
            std::string("required GStreamer element is unavailable: ") + name +
            ". Install gstreamer1.0-plugins-bad (srtsink), check GST_PLUGIN_PATH; runtime=" +
            (version != nullptr ? version : "unknown");
        g_free(version);
        throw std::runtime_error(message);
      }
      gst_object_unref(factory);
    }
    if (rotation_degrees_ == 180) {
      GstElementFactory* factory = gst_element_factory_find("videoflip");
      if (factory == nullptr)
        throw std::runtime_error(
            "required GStreamer element is unavailable: videoflip. "
            "Install gstreamer1.0-plugins-good");
      gst_object_unref(factory);
    }
  }

  std::string buildPipeline() const {
    std::ostringstream pipeline;
    pipeline << "appsrc name=source is-live=true block=false format=time do-timestamp=false "
             << "caps=video/x-raw,format=BGR,width=" << output_width_ << ",height="
             << output_height_ << ",framerate=" << framerate_ << "/1 "
             << "! queue max-size-buffers=2 leaky=downstream ";
    if (rotation_degrees_ == 180) pipeline << "! videoflip method=rotate-180 ";
    pipeline << "! videoconvert ! video/x-raw,format=I420 "
             << "! x264enc tune=zerolatency speed-preset=ultrafast bitrate=" << bitrate_kbps_
             << " key-int-max=" << framerate_ << " bframes=0 byte-stream=true aud=true "
             << "! video/x-h264,profile=baseline,stream-format=byte-stream,alignment=au "
             << "! h264parse config-interval=-1 ! mpegtsmux alignment=7 "
             << "! srtsink name=srt_output uri=\"" << listenerUri() << "\" sync=false";
    return pipeline.str();
  }

  void startPipeline() {
    GError* error = nullptr;
    const std::string description = buildPipeline();
    ROS_INFO_STREAM("epgeneral_video_srt GStreamer pipeline: " << description);
    pipeline_ = gst_parse_launch(description.c_str(), &error);
    if (pipeline_ == nullptr || error != nullptr) {
      const std::string message = error != nullptr ? error->message : "unknown parser error";
      if (error != nullptr) g_error_free(error);
      throw std::runtime_error("failed to create SRT pipeline: " + message);
    }
    appsrc_ = gst_bin_get_by_name(GST_BIN(pipeline_), "source");
    if (appsrc_ == nullptr) throw std::runtime_error("failed to locate GStreamer appsrc");
    srt_sink_ = gst_bin_get_by_name(GST_BIN(pipeline_), "srt_output");
    if (srt_sink_ == nullptr) throw std::runtime_error("failed to locate GStreamer srtsink");
    // GstSRTSink latency is milliseconds; avoid a second URI unit conversion.
    g_object_set(G_OBJECT(srt_sink_), "latency", srt_latency_ms_, nullptr);
    if (g_object_class_find_property(G_OBJECT_GET_CLASS(srt_sink_), "wait-for-connection"))
      g_object_set(G_OBJECT(srt_sink_), "wait-for-connection", FALSE, nullptr);
    if (g_signal_lookup("caller-connecting", G_OBJECT_TYPE(srt_sink_)) != 0) {
      g_signal_connect(srt_sink_, "caller-connecting",
                       G_CALLBACK(&VideoSrtNode::callerConnecting), this);
    }
    g_signal_connect(srt_sink_, "caller-added", G_CALLBACK(&VideoSrtNode::callerAdded), this);
    g_signal_connect(srt_sink_, "caller-removed", G_CALLBACK(&VideoSrtNode::callerRemoved), this);
    bus_ = gst_element_get_bus(pipeline_);
    const GstStateChangeReturn state_result = gst_element_set_state(pipeline_, GST_STATE_PLAYING);
    if (state_result == GST_STATE_CHANGE_FAILURE)
      throw std::runtime_error("failed to start SRT Listener pipeline");
    ROS_INFO_STREAM("epgeneral_video_srt SRT listener bound to " << bind_address_ << ":" << srt_port_
                    << "; waiting for a ground-station caller");
  }

  void imageCallback(const sensor_msgs::ImageConstPtr& message) {
    try { pushFrame(cv_bridge::toCvShare(message, "bgr8")->image); }
    catch (const std::exception& error) {
      ROS_ERROR_THROTTLE(5.0, "epgeneral_video_srt raw image processing failed: %s", error.what());
    }
  }

  void compressedImageCallback(const sensor_msgs::CompressedImageConstPtr& message) {
    try {
      if (message->data.empty()) throw std::runtime_error("compressed image payload is empty");
      pushFrame(cv_bridge::toCvCopy(message, "bgr8")->image);
    } catch (const std::exception& error) {
      ROS_ERROR_THROTTLE(5.0, "epgeneral_video_srt compressed image processing failed: %s", error.what());
    }
  }

  void pushFrame(const cv::Mat& input) {
    if (input.data == nullptr || input.rows < 1 || input.cols < 1 || input.type() != CV_8UC3)
      throw std::runtime_error("converted frame must be non-empty BGR8");
    const auto now = std::chrono::steady_clock::now();
    last_frame_time_ = ros::WallTime::now();
    received_frame_ = true;
    const auto period = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
        std::chrono::duration<double>(1.0 / framerate_));
    if (sequence_ && now < next_frame_due_) return;
    next_frame_due_ = sequence_ ? next_frame_due_ + period : now + period;
    if (next_frame_due_ < now) next_frame_due_ = now + period;
    std::vector<std::uint8_t> frame(static_cast<std::size_t>(output_width_) * output_height_ * 3);
    for (int y = 0; y < output_height_; ++y) {
      const std::uint8_t* source_row = input.ptr<std::uint8_t>(y * input.rows / output_height_);
      std::uint8_t* output_row = frame.data() + static_cast<std::size_t>(y) * output_width_ * 3;
      for (int x = 0; x < output_width_; ++x)
        std::memcpy(output_row + static_cast<std::size_t>(x) * 3,
                    source_row + static_cast<std::size_t>(x * input.cols / output_width_) * 3, 3);
    }
    std::lock_guard<std::mutex> lock(push_mutex_);
    if (shutting_down_) return;
    GstBuffer* buffer = gst_buffer_new_allocate(nullptr, frame.size(), nullptr);
    gst_buffer_fill(buffer, 0, frame.data(), frame.size());
    const GstClockTime duration = gst_util_uint64_scale_int(1, GST_SECOND, framerate_);
    GST_BUFFER_PTS(buffer) = static_cast<GstClockTime>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(now - pipeline_started_).count());
    GST_BUFFER_DTS(buffer) = GST_BUFFER_PTS(buffer);
    GST_BUFFER_DURATION(buffer) = duration;
    ++sequence_;
    const GstFlowReturn result = gst_app_src_push_buffer(GST_APP_SRC(appsrc_), buffer);
    if (result != GST_FLOW_OK)
      ROS_WARN_THROTTLE(5.0, "epgeneral_video_srt appsrc push returned %d", result);
    last_frame_time_ = ros::WallTime::now();
    received_frame_ = true;
    ROS_INFO_ONCE("epgeneral_video_srt pushed first frame into H.264/MPEG-TS encoder");
  }

  void watchdogCallback(const ros::WallTimerEvent&) {
    const double age = (ros::WallTime::now() - last_frame_time_).toSec();
    if (age > frame_timeout_seconds_) failed_ = true;
    std_msgs::String status;
    std::ostringstream value;
    // Identity and input mode have already been validated by the shared launcher.
    value << "{\"device_id\":\"" << device_id_ << "\",\"input_mode\":\""
          << (image_message_type_ == "sensor_msgs/Image" ? "ros_image" : "ros_compressed")
          << "\",\"ready\":" << (received_frame_ && !failed_ ? "true" : "false")
          << ",\"frames\":" << sequence_ << ",\"frame_age\":" << age
          << ",\"reconnects\":" << reconnects_
          << ",\"error\":\"" << (failed_ ? "input_or_pipeline_unavailable" : "") << "\"}";
    status.data = value.str();
    status_publisher_.publish(status);
  }

  static gboolean busMessage(GstBus*, GstMessage* message, gpointer user_data) {
    VideoSrtNode* node = static_cast<VideoSrtNode*>(user_data);
    if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_ERROR || GST_MESSAGE_TYPE(message) == GST_MESSAGE_WARNING) {
      GError* error = nullptr;
      gchar* debug = nullptr;
      if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_ERROR) {
        gst_message_parse_error(message, &error, &debug);
        ROS_ERROR("epgeneral_video_srt pipeline error: %s", error->message);
        node->failed_ = true;
      } else {
        gst_message_parse_warning(message, &error, &debug);
        ROS_WARN("epgeneral_video_srt pipeline warning: %s", error->message);
      }
      g_clear_error(&error);
      g_free(debug);
    } else if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_EOS) {
      node->failed_ = true;
    } else if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_STATE_CHANGED &&
               GST_MESSAGE_SRC(message) == GST_OBJECT(node->pipeline_)) {
      GstState old_state, new_state, pending;
      gst_message_parse_state_changed(message, &old_state, &new_state, &pending);
      ROS_INFO("epgeneral_video_srt pipeline state %s -> %s",
               gst_element_state_get_name(old_state), gst_element_state_get_name(new_state));
    }
    return TRUE;
  }

  static gboolean callerConnecting(GstElement*, GSocketAddress*, const gchar* stream_id,
                                    gpointer user_data) {
    VideoSrtNode* node = static_cast<VideoSrtNode*>(user_data);
    ROS_INFO_STREAM("epgeneral_video_srt caller connecting device=" << node->device_id_
                    << " stream_id=" << (stream_id != nullptr ? stream_id : ""));
    return TRUE;
  }

  static void callerAdded(GstElement*, gint socket, GSocketAddress*, gpointer user_data) {
    VideoSrtNode* node = static_cast<VideoSrtNode*>(user_data);
    ROS_INFO_STREAM("epgeneral_video_srt caller connected device=" << node->device_id_
                    << " socket=" << socket);
  }

  static void callerRemoved(GstElement*, gint socket, GSocketAddress*, gpointer user_data) {
    VideoSrtNode* node = static_cast<VideoSrtNode*>(user_data);
    ROS_INFO_STREAM("epgeneral_video_srt caller disconnected device=" << node->device_id_
                    << " socket=" << socket);
  }

  ros::NodeHandle nh_, pnh_;
  image_transport::ImageTransport image_transport_;
  image_transport::Subscriber image_subscriber_;
  ros::Subscriber compressed_subscriber_;
  ros::WallTimer frame_watchdog_;
  ros::Publisher status_publisher_;
  std::string status_topic_;
  std::chrono::steady_clock::time_point pipeline_started_, next_frame_due_;
  std::string device_id_, device_ip_, image_topic_, image_message_type_, bind_address_;
  int srt_port_, srt_latency_ms_, output_width_, output_height_, framerate_, bitrate_kbps_;
  int rotation_degrees_;
  double frame_timeout_seconds_;
  GstElement* pipeline_;
  GstElement* appsrc_;
  GstElement* srt_sink_;
  GstBus* bus_;
  std::mutex push_mutex_;
  std::uint64_t sequence_;
  ros::WallTime last_frame_time_;
  std::atomic<bool> received_frame_, shutting_down_, failed_;
  std::uint64_t reconnects_;
};

int main(int argc, char** argv) {
  ros::init(argc, argv, "epgeneral_video_srt");
  ros::NodeHandle private_node("~");
  double reconnect_interval = 3.0;
  private_node.param("reconnect_interval_seconds", reconnect_interval, 3.0);
  if (!std::isfinite(reconnect_interval) || reconnect_interval < 0.1 || reconnect_interval > 300)
    return 2;
  std::uint64_t reconnects = 0;
  while (ros::ok()) {
    try {
      VideoSrtNode node(reconnects);
      ros::WallRate rate(100);
      while (ros::ok() && !node.failed()) {
        ros::spinOnce();
        rate.sleep();
      }
    } catch (const std::exception& error) {
      ROS_FATAL("epgeneral_video_srt startup failed: %s", error.what());
      return 1;
    }
    if (!ros::ok()) break;
    ++reconnects;
    const auto deadline = std::chrono::steady_clock::now() +
        std::chrono::duration<double>(reconnect_interval);
    while (ros::ok() && std::chrono::steady_clock::now() < deadline)
      ros::WallDuration(0.1).sleep();
  }
  return 0;
}
