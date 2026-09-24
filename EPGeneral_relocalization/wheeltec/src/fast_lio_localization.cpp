//
// Created by bruce on 2022/3/29.
//

#include <chrono>
#include <algorithm>
#include <cmath>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <vector>

#include <ros/ros.h>
#include <tf/tf.h>
#include <tf_conversions/tf_eigen.h>
#include <tf2_ros/transform_broadcaster.h>
#include <geometry_msgs/PointStamped.h>
#include <sensor_msgs/PointCloud2.h>
#include <geometry_msgs/PoseWithCovarianceStamped.h>
#include <nav_msgs/Odometry.h>
#include <std_msgs/String.h>
#include <std_msgs/Bool.h>
#include <std_srvs/Trigger.h>
#include <fast_lio_localization/AllowedRegions.h>
#include <fast_lio_localization/DeleteRegion.h>
#include <fast_lio_localization/allowed_regions.h>
#include <visualization_msgs/MarkerArray.h>
#include <message_filters/subscriber.h>
#include <message_filters/synchronizer.h>
#include <message_filters/sync_policies/exact_time.h>
#include <message_filters/sync_policies/approximate_time.h>
#include <XmlRpcValue.h>

#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <pcl_conversions/pcl_conversions.h>

#include <Eigen/Eigen>

#include "pclomp/ndt_omp.h"
#include "ccs_candidate_gate.h"

using namespace std;

typedef pclomp::NormalDistributionsTransform<pcl::PointXYZI, pcl::PointXYZI> NDT;
typedef pcl::PointCloud<pcl::PointXYZI> Cloud;


class Config
{
public:
    // 当前 WheelTech 系统要求 fast_lio_localization 发布：
    //
    // map -> odom
    //
    // 不再使用原始项目默认的 map -> camera_init。
    string odomFrame = "odom";

    // map -> odom TF 向未来预发布的时间。
    // 用于避免 TEB / move_base 控制周期与 localization TF
    // 发布周期之间几十毫秒的相位差导致 future extrapolation。
    double tfPostdateSec = 0.25;

    struct
    {
        bool debug = false;
        int numThreads = 4;
        int maximumIterations = 20;
        float voxelLeafSize = 0.1;
        float resolution = 1.0;
        double transformationEpsilon = 0.01;
        double stepSize = 0.1;
        double threshShift = 2;
        double threshRot = M_PI / 12;
        double minScanRange = 1.0;
        double maxScanRange = 100;
    } ndt;

    struct Gate
    {
        bool enabled = true;
        bool editable = true;
        bool requireConverged = true;
        int minConfirmFrames = 2;
        double enterMargin = 0.15;
        double exitMargin = 0.35;
        double maxFitnessScore = 2.0;
        double maxPoseJump = 1.0;
        double maxYawJump = M_PI / 6.0;
        double closeDistance = 0.30;
        double markerRate = 2.0;
        string clickedPointTopic = "/clicked_point";
        vector<ndt_gate::Polygon> allowedPolygons;
    } gate;

    explicit Config(ros::NodeHandle &nh) : _nh(nh)
    {
        // 必须读取 odom_frame。
        // 如果 launch 中没有设置，则默认使用 "odom"。
        _nh.param<string>("odom_frame", odomFrame, string("odom"));

        // map -> odom TF 向未来预发布时间。
        _nh.param("tf_postdate_sec", tfPostdateSec, 0.25);

        _nh.getParam("ndt/debug", ndt.debug);
        _nh.getParam("ndt/num_threads", ndt.numThreads);
        _nh.getParam("ndt/maximum_iterations", ndt.maximumIterations);
        _nh.getParam("ndt/voxel_leaf_size", ndt.voxelLeafSize);
        _nh.getParam("ndt/transformation_epsilon", ndt.transformationEpsilon);
        _nh.getParam("ndt/step_size", ndt.stepSize);
        _nh.getParam("ndt/resolution", ndt.resolution);
        _nh.getParam("ndt/thresh_shift", ndt.threshShift);
        _nh.getParam("ndt/thresh_rot", ndt.threshRot);
        _nh.getParam("ndt/min_scan_range", ndt.minScanRange);
        _nh.getParam("ndt/max_scan_range", ndt.maxScanRange);

        _nh.param("gate/enabled", gate.enabled, true);
        _nh.param("gate/editable", gate.editable, true);
        _nh.param("gate/require_converged", gate.requireConverged, true);
        _nh.param("gate/min_confirm_frames", gate.minConfirmFrames, 2);
        _nh.param("gate/enter_margin", gate.enterMargin, 0.15);
        _nh.param("gate/exit_margin", gate.exitMargin, 0.35);
        _nh.param("gate/max_fitness_score", gate.maxFitnessScore, 2.0);
        _nh.param("gate/max_pose_jump", gate.maxPoseJump, 1.0);
        _nh.param("gate/max_yaw_jump", gate.maxYawJump, M_PI / 6.0);
        _nh.param("gate/close_distance", gate.closeDistance, 0.30);
        _nh.param("gate/marker_rate", gate.markerRate, 2.0);
        _nh.param<string>("gate/clicked_point_topic", gate.clickedPointTopic, string("/clicked_point"));
        gate.minConfirmFrames = std::max(1, gate.minConfirmFrames);

        XmlRpc::XmlRpcValue polygons;
        if (gate.enabled && _nh.getParam("gate/allowed_polygons", polygons))
        {
            if (polygons.getType() != XmlRpc::XmlRpcValue::TypeArray)
                throw std::runtime_error("gate/allowed_polygons must be an array");
            for (int i = 0; i < polygons.size(); ++i)
                gate.allowedPolygons.push_back(parsePolygon(polygons[i]));
        }
        else if (gate.enabled)
        {
            XmlRpc::XmlRpcValue polygon;
            if (_nh.getParam("gate/allowed_polygon", polygon))
            {
                if (polygon.getType() != XmlRpc::XmlRpcValue::TypeArray)
                    throw std::runtime_error("gate/allowed_polygon must be an array");
                if (polygon.size() != 0)
                    gate.allowedPolygons.push_back(parsePolygon(polygon));
            }
        }

        ROS_INFO("fast_lio_localization config:");
        ROS_INFO("  odom_frame      = %s", odomFrame.c_str());
        ROS_INFO("  tf_postdate_sec = %.3f", tfPostdateSec);
        ROS_INFO("  gate/enabled    = %s", gate.enabled ? "true" : "false");
        ROS_INFO("  gate regions    = %zu", gate.allowedPolygons.size());
    }

private:
    static double coordinate(XmlRpc::XmlRpcValue& value)
    {
        if (value.getType() == XmlRpc::XmlRpcValue::TypeInt)
            return static_cast<int>(value);
        if (value.getType() == XmlRpc::XmlRpcValue::TypeDouble)
            return static_cast<double>(value);
        throw std::runtime_error("allowed region coordinates must be numeric");
    }

    static ndt_gate::Polygon parsePolygon(XmlRpc::XmlRpcValue& value)
    {
        if (value.getType() != XmlRpc::XmlRpcValue::TypeArray)
            throw std::runtime_error("allowed region must be an array of [x,y]");
        ndt_gate::Polygon polygon;
        for (int i = 0; i < value.size(); ++i)
        {
            if (value[i].getType() != XmlRpc::XmlRpcValue::TypeArray || value[i].size() < 2)
                throw std::runtime_error("allowed region vertex must contain x,y");
            polygon.push_back({coordinate(value[i][0]), coordinate(value[i][1])});
        }
        // Legacy configurations may include z or repeat the first vertex at the end.
        if (polygon.size() > 3 &&
            ndt_gate::segmentDistance(polygon.front(),polygon.back(),polygon.back()) < 1e-6)
            polygon.pop_back();
        std::string error;
        if (!ndt_gate::validPolygon(polygon,error))
            throw std::runtime_error("invalid configured allowed region: " + error);
        return polygon;
    }

    ros::NodeHandle &_nh;
};


class Localizer
{
public:
    explicit Localizer(ros::NodeHandle &nh) :
            _nh(nh),
            _cfg(nh),
            _mapPtr(new Cloud),
            _mapFilteredPtr(new Cloud)
    {
        _mapSub = _nh.subscribe(
                "/map_cloud",
                10,
                &Localizer::mapCallback,
                this
        );

        _initPoseSub = _nh.subscribe(
                "/initialpose",
                10,
                &Localizer::initPoseWithNDTCallback,
                this
        );

        _pcSubPtr =
                new message_filters::Subscriber<sensor_msgs::PointCloud2>(
                        nh,
                        "/velodyne_points",
                        1
                );

        _odomSubPtr =
                new message_filters::Subscriber<nav_msgs::Odometry>(
                        nh,
                        "/odom_lio",
                        1
                );

        _syncPtr =
                new message_filters::Synchronizer<syncPolicy>(
                        syncPolicy(10),
                        *_pcSubPtr,
                        *_odomSubPtr
                );

        _syncPtr->registerCallback(
                boost::bind(
                        &Localizer::syncCallback,
                        this,
                        _1,
                        _2
                )
        );

        _voxelGridFilter.setLeafSize(
                _cfg.ndt.voxelLeafSize,
                _cfg.ndt.voxelLeafSize,
                _cfg.ndt.voxelLeafSize
        );

        _ndt.setNumThreads(_cfg.ndt.numThreads);
        _ndt.setTransformationEpsilon(_cfg.ndt.transformationEpsilon);
        _ndt.setStepSize(_cfg.ndt.stepSize);
        _ndt.setResolution(_cfg.ndt.resolution);
        _ndt.setMaximumIterations(_cfg.ndt.maximumIterations);

        _baseOdom.setIdentity();
        _odomMap.setIdentity();
        _lastRejectedPose.setIdentity();

        for (const auto& polygon : _cfg.gate.allowedPolygons)
        {
            std::string error;
            if (_regions.add(polygon,error) < 0)
                throw std::runtime_error(error);
        }

        ros::NodeHandle rootNh;
        _clickedPointSub = rootNh.subscribe(
                _cfg.gate.clickedPointTopic,
                20,
                &Localizer::clickedPointCallback,
                this
        );

        _gateMarkersPub = rootNh.advertise<visualization_msgs::MarkerArray>(
                "/ndt_gate/markers",
                1,
                true
        );

        _gateStatusPub = rootNh.advertise<std_msgs::String>(
                "/ndt_gate/status",
                10,
                true
        );

        _regionsPub = rootNh.advertise<fast_lio_localization::AllowedRegions>(
                "/ndt_gate/regions", 1, true);
        _deleteRegionSrv = rootNh.advertiseService(
                "/ndt_gate/delete_region", &Localizer::deleteRegionCallback, this);
        _cancelDraftSrv = rootNh.advertiseService(
                "/ndt_gate/cancel_draft", &Localizer::cancelDraftCallback, this);

        _gateMarkerTimer = _nh.createTimer(
                ros::Duration(1.0 / std::max(0.1, _cfg.gate.markerRate)),
                &Localizer::gateMarkerTimerCallback,
                this
        );

        _healthPub = rootNh.advertise<std_msgs::Bool>("/ccs/localization_valid", 1, true);
        _setRegionsSub = rootNh.subscribe("/ndt_gate/set_regions", 1, &Localizer::setRegionsCallback, this);
        _tfTimer = _nh.createTimer(ros::Duration(0.05), &Localizer::tfTimerCallback, this);
        publishGateStatus("WAITING_INITIAL_POSE");
        publishRegions();
        publishGateVisualization();
    }

private:
    ros::NodeHandle &_nh;

    ros::Publisher _healthPub;
    ros::Subscriber _setRegionsSub;
    ros::Timer _tfTimer;
    ros::Time _inputStamp, _lastCloudStamp, _regionsToken;
    ros::WallTime _initialDeadline;
    bool _pendingInitial = false;
    tf::Pose _initialGuess;
    bool inputsFresh() const {
        const double age = (ros::Time::now() - _inputStamp).toSec();
        return !_inputStamp.isZero() && age >= -0.5 && age <= 2.0;
    }
    void tfTimerCallback(const ros::TimerEvent&) {
        std_msgs::Bool health; health.data = _haveAcceptedPose && inputsFresh();
        _healthPub.publish(health);
        if (health.data) publishTF();
    }
    void setRegionsCallback(const fast_lio_localization::AllowedRegions::ConstPtr& msg) {
        if (!_haveAcceptedPose || !inputsFresh() || msg->header.frame_id != "map" ||
            msg->header.stamp.isZero() || msg->header.stamp < _regionsToken)
        { publishGateStatus("REGIONS_REJECTED invalid state/frame/token"); return; }
        if (msg->header.stamp == _regionsToken) { publishRegions(); return; }
        std::vector<ndt_gate::Region> replacement;
        for (const auto& region : msg->regions) {
            ndt_gate::Polygon polygon;
            for (const auto& point : region.polygon.points) {
                if (!std::isfinite(point.z) || std::fabs(point.z) > 1e-5)
                { publishGateStatus("REGIONS_REJECTED nonplanar polygon"); return; }
                polygon.push_back({point.x, point.y});
            }
            replacement.push_back({region.id, polygon, false});
        }
        std::string error;
        if (!_regions.replace(replacement, error))
        { publishGateStatus("REGIONS_REJECTED " + error); return; }
        _regionsToken = msg->header.stamp;
        _draft.clear(); _gateConfirmCount = 0;
        updateGateLatch((_odomMap * _baseOdom).getOrigin());
        publishRegions();
        publishGateStatus(_regions.empty() ? "REGIONS_APPLIED automatic_ndt=paused" : "REGIONS_APPLIED");
    }
    ros::Subscriber _mapSub;
    ros::Subscriber _initPoseSub;
    ros::Subscriber _clickedPointSub;

    tf2_ros::TransformBroadcaster _br;
    ros::Publisher _gateMarkersPub;
    ros::Publisher _gateStatusPub;
    ros::Publisher _regionsPub;
    ros::ServiceServer _deleteRegionSrv;
    ros::ServiceServer _cancelDraftSrv;
    ros::Timer _gateMarkerTimer;

    message_filters::Subscriber<sensor_msgs::PointCloud2> *_pcSubPtr;
    message_filters::Subscriber<nav_msgs::Odometry> *_odomSubPtr;

    typedef message_filters::sync_policies::ApproximateTime<
            sensor_msgs::PointCloud2,
            nav_msgs::Odometry
    > syncPolicy;

    message_filters::Synchronizer<syncPolicy> *_syncPtr;

    NDT _ndt;
    pcl::VoxelGrid<pcl::PointXYZI> _voxelGridFilter;

    Config _cfg;

    Cloud::Ptr _mapPtr;
    Cloud::Ptr _mapFilteredPtr;

    tf::Pose _baseOdom;
    tf::Pose _odomMap;

    sensor_msgs::PointCloud2::ConstPtr _pcPtr = nullptr;

    ndt_gate::Regions _regions;
    ndt_gate::Polygon _draft;
    ros::Time _discardClicksThrough;
    bool _gateInsideLatched = false;
    bool _haveAcceptedPose = false;
    int _gateConfirmCount = 0;
    tf::Pose _lastRejectedPose;
    bool _hasRejectedPose = false;
    string _lastGateStatus = "WAITING";


    static double normalizedYaw(
            double yaw)
    {
        while (yaw > M_PI)
        {
            yaw -= 2.0 * M_PI;
        }

        while (yaw < -M_PI)
        {
            yaw += 2.0 * M_PI;
        }

        return yaw;
    }


    static double yawDiff(
            const tf::Transform &a,
            const tf::Transform &b)
    {
        return std::fabs(
                normalizedYaw(
                        tf::getYaw(a.getRotation()) -
                        tf::getYaw(b.getRotation())
                )
        );
    }


    double signedDistanceToGate(
            const tf::Vector3 &p) const
    {
        return _regions.distance({p.x(),p.y()});
    }


    bool updateGateLatch(
            const tf::Vector3& predicted)
    {
        _gateInsideLatched = _regions.update({predicted.x(),predicted.y()},
                                             _cfg.gate.enterMargin, _cfg.gate.exitMargin);
        return _gateInsideLatched;
    }


    void publishGateStatus(
            const string &status)
    {
        _lastGateStatus = status;

        if (_gateStatusPub)
        {
            std_msgs::String msg;
            msg.data = status;
            _gateStatusPub.publish(msg);
        }
    }


    void appendStatusMetric(
            std::ostringstream &oss,
            const string &name,
            double value) const
    {
        oss << " " << name << "=" << value;
    }


    bool acceptNdtCandidate(
            const tf::Transform &predictedBaseMap,
            const tf::Transform &candidateBaseMap,
            double fitnessScore,
            bool converged,
            const string &trigger)
    {
        const bool initial = trigger == "initialpose";
        const double predictedDistance =
                signedDistanceToGate(predictedBaseMap.getOrigin());
        const double candidateDistance =
                signedDistanceToGate(candidateBaseMap.getOrigin());
        const bool predictedInside = updateGateLatch(predictedBaseMap.getOrigin());

        const auto jump = predictedBaseMap.inverseTimes(candidateBaseMap);
        const double jumpShift = hypot(
                jump.getOrigin().x(),
                jump.getOrigin().y()
        );
        const double jumpYaw = yawDiff(predictedBaseMap, candidateBaseMap);

        string reason;
        const bool hardOk = ccs_wheeltec::acceptCandidate(initial, _regions.empty(), predictedInside,
            candidateDistance, _cfg.gate.exitMargin, _cfg.gate.requireConverged, converged,
            fitnessScore, _cfg.gate.maxFitnessScore, jumpShift, _cfg.gate.maxPoseJump,
            jumpYaw, _cfg.gate.maxYawJump, _cfg.gate.minConfirmFrames, _gateConfirmCount, reason);

        std::ostringstream status;
        status << reason
               << " trigger=" << trigger
               << " confirm=" << _gateConfirmCount << "/"
               << _cfg.gate.minConfirmFrames
               << " converged=" << (converged ? "true" : "false");
        status << " regions=" << _regions.items().size();
        appendStatusMetric(status, "fitness", fitnessScore);
        appendStatusMetric(status, "predicted_dist", predictedDistance);
        appendStatusMetric(status, "candidate_dist", candidateDistance);
        appendStatusMetric(status, "jump_xy", jumpShift);
        appendStatusMetric(status, "jump_yaw", jumpYaw);
        publishGateStatus(status.str());

        if (!hardOk)
        {
            _lastRejectedPose = candidateBaseMap;
            _hasRejectedPose = true;
            publishGateVisualization();
            ROS_WARN(
                    "NDT gate rejected candidate: %s",
                    status.str().c_str()
            );
            return false;
        }

        _hasRejectedPose = false;
        publishGateVisualization();
        return true;
    }


    void clickedPointCallback(
            const geometry_msgs::PointStamped::ConstPtr &msg)
    {
        if (!_cfg.gate.enabled || !_cfg.gate.editable)
        {
            return;
        }

        // Click topic delivery and cancel RPC delivery can arrive out of order.
        if (!_discardClicksThrough.isZero() && msg->header.stamp <= _discardClicksThrough)
            return;

        if (!msg->header.frame_id.empty() &&
            msg->header.frame_id != "map")
        {
            ROS_WARN_THROTTLE(
                    2.0,
                    "NDT gate ignores clicked point in frame '%s'; use RViz Fixed Frame 'map'",
                    msg->header.frame_id.c_str()
            );
            return;
        }

        ndt_gate::Point point{msg->point.x,msg->point.y};
        if (!std::isfinite(point.x) || !std::isfinite(point.y))
        {
            publishGateStatus("INVALID_POINT");
            return;
        }

        if (_draft.size() >= 3 &&
            ndt_gate::segmentDistance(point, _draft.front(), _draft.front()) <=
            _cfg.gate.closeDistance)
        {
            std::string error;
            const auto id = _regions.add(_draft,error);
            if (id < 0)
            {
                publishGateStatus("INVALID_POLYGON " + error);
            }
            else
            {
                _draft.clear();
                _gateConfirmCount = 0;
                publishGateStatus("AREA_CLOSED id=" + std::to_string(id) +
                                  " regions=" + std::to_string(_regions.items().size()));
            }
        }
        else
        {
            if (!_draft.empty() && ndt_gate::segmentDistance(point,_draft.back(),_draft.back()) < 1e-6)
                return;
            _draft.push_back(point);
            publishGateStatus("DRAWING_ALLOWED_AREA vertices=" + std::to_string(_draft.size()));
        }

        publishRegions();
        publishGateVisualization();
    }

    static geometry_msgs::Polygon polygonMessage(const ndt_gate::Polygon& polygon)
    {
        geometry_msgs::Polygon msg;
        for (const auto& p : polygon)
        {
            geometry_msgs::Point32 point;
            point.x = p.x; point.y = p.y; point.z = 0.0;
            msg.points.push_back(point);
        }
        return msg;
    }

    void publishRegions()
    {
        fast_lio_localization::AllowedRegions msg;
        msg.header.frame_id = "map";
        msg.header.stamp = _regionsToken;
        msg.editable = _cfg.gate.enabled && _cfg.gate.editable;
        msg.draft = polygonMessage(_draft);
        for (const auto& r : _regions.items())
        {
            fast_lio_localization::AllowedRegion region;
            region.id = r.id;
            region.polygon = polygonMessage(r.polygon);
            msg.regions.push_back(region);
        }
        _regionsPub.publish(msg);
    }

    bool deleteRegionCallback(fast_lio_localization::DeleteRegion::Request& req,
                              fast_lio_localization::DeleteRegion::Response& res)
    {
        if (!_cfg.gate.enabled || !_cfg.gate.editable)
        { res.success = false; res.message = "AREA_EDITING_DISABLED"; return true; }
        res.success = _regions.erase(req.id);
        res.message = (res.success ? "AREA_DELETED id=" : "AREA_NOT_FOUND id=") +
                      std::to_string(req.id);
        if (res.success)
        {
            _gateConfirmCount = 0;
            updateGateLatch((_odomMap * _baseOdom).getOrigin());
            publishRegions();
        }
        publishGateStatus(res.message);
        publishGateVisualization();
        return true;
    }

    bool cancelDraftCallback(std_srvs::Trigger::Request&, std_srvs::Trigger::Response& res)
    {
        if (!_cfg.gate.enabled || !_cfg.gate.editable)
        { res.success = false; res.message = "AREA_EDITING_DISABLED"; return true; }
        _draft.clear();
        _discardClicksThrough = ros::Time::now();
        res.success = true;
        res.message = "DRAWING_CANCELLED";
        publishGateStatus(res.message);
        publishRegions();
        publishGateVisualization();
        return true;
    }


    void gateMarkerTimerCallback(
            const ros::TimerEvent &)
    {
        publishGateVisualization();
    }


    void publishGateVisualization()
    {
        if (!_gateMarkersPub)
        {
            return;
        }

        visualization_msgs::MarkerArray markers;
        const ros::Time now = ros::Time::now();

        visualization_msgs::Marker clear;
        clear.header.frame_id = "map";
        clear.header.stamp = now;
        clear.pose.orientation.w = 1.0;
        clear.action = visualization_msgs::Marker::DELETEALL;
        markers.markers.push_back(clear);

        visualization_msgs::Marker area;
        area.header.frame_id = "map";
        area.header.stamp = now;
        area.ns = "ndt_gate";
        area.id = 0;
        area.type = visualization_msgs::Marker::LINE_STRIP;
        area.action = visualization_msgs::Marker::ADD;
        area.pose.orientation.w = 1.0;
        area.scale.x = 0.06;
        area.color.r = _gateInsideLatched ? 0.0 : 1.0;
        area.color.g = _gateInsideLatched ? 0.85 : 0.65;
        area.color.b = 0.05;
        area.color.a = 1.0;

        const auto appendPolygon = [&](const ndt_gate::Polygon& polygon,
                                       int id, bool closed, bool inside)
        {
            if (polygon.empty()) return;
            visualization_msgs::Marker line = area;
            line.ns = closed ? "ndt_allowed_regions" : "ndt_draft";
            line.id = id;
            line.color.r = closed ? (inside ? 0.0 : 0.2) : 1.0;
            line.color.g = closed ? (inside ? 0.9 : 0.65) : 0.7;
            line.color.b = closed ? (inside ? 0.15 : 1.0) : 0.0;
            for (const auto& p : polygon)
            {
                geometry_msgs::Point out;
                out.x = p.x; out.y = p.y; out.z = 0.05;
                line.points.push_back(out);
            }
            visualization_msgs::Marker vertices = line;
            vertices.ns = closed ? "ndt_region_vertices" : "ndt_draft_vertices";
            vertices.type = visualization_msgs::Marker::SPHERE_LIST;
            vertices.scale.x = vertices.scale.y = vertices.scale.z = 0.15;
            markers.markers.push_back(vertices);
            if (closed) line.points.push_back(line.points.front());
            if (line.points.size() >= 2) markers.markers.push_back(line);
            visualization_msgs::Marker label = line;
            label.ns = closed ? "ndt_region_labels" : "ndt_draft_labels";
            label.type = visualization_msgs::Marker::TEXT_VIEW_FACING;
            label.points.clear();
            label.pose.position = line.points.front();
            label.pose.position.z = 0.45;
            label.scale.z = 0.3;
            label.text = closed ? "NDT " + std::to_string(id) : "DRAFT";
            markers.markers.push_back(label);
        };
        for (const auto& r : _regions.items()) appendPolygon(r.polygon,r.id,true,r.inside);
        appendPolygon(_draft,0,false,false);

        const tf::Transform predictedBaseMap = _odomMap * _baseOdom;

        visualization_msgs::Marker text;
        text.header.frame_id = "map";
        text.header.stamp = now;
        text.ns = "ndt_gate";
        text.id = 2;
        text.type = visualization_msgs::Marker::TEXT_VIEW_FACING;
        text.action = visualization_msgs::Marker::ADD;
        text.pose.position.x = predictedBaseMap.getOrigin().x();
        text.pose.position.y = predictedBaseMap.getOrigin().y();
        text.pose.position.z = 1.2;
        text.pose.orientation.w = 1.0;
        text.scale.z = 0.35;
        text.color.r = _gateInsideLatched ? 0.0 : 1.0;
        text.color.g = _gateInsideLatched ? 1.0 : 0.2;
        text.color.b = 0.1;
        text.color.a = 1.0;
        text.text = _lastGateStatus;
        markers.markers.push_back(text);

        visualization_msgs::Marker rejected;
        rejected.header.frame_id = "map";
        rejected.header.stamp = now;
        rejected.ns = "ndt_gate";
        rejected.id = 3;
        rejected.type = visualization_msgs::Marker::ARROW;
        rejected.pose.position.x = _lastRejectedPose.getOrigin().x();
        rejected.pose.position.y = _lastRejectedPose.getOrigin().y();
        rejected.pose.position.z = 0.25;
        rejected.pose.orientation.x = _lastRejectedPose.getRotation().x();
        rejected.pose.orientation.y = _lastRejectedPose.getRotation().y();
        rejected.pose.orientation.z = _lastRejectedPose.getRotation().z();
        rejected.pose.orientation.w = _lastRejectedPose.getRotation().w();
        rejected.scale.x = 0.7;
        rejected.scale.y = 0.12;
        rejected.scale.z = 0.12;
        rejected.color.r = 1.0;
        rejected.color.g = 0.0;
        rejected.color.b = 0.0;
        rejected.color.a = 0.9;
        rejected.action = _hasRejectedPose ?
                          visualization_msgs::Marker::ADD :
                          visualization_msgs::Marker::DELETE;
        markers.markers.push_back(rejected);

        _gateMarkersPub.publish(markers);
    }


    void mapCallback(
            const sensor_msgs::PointCloud2::ConstPtr &msg)
    {
        ROS_INFO("Get map");

        pcl::fromROSMsg<pcl::PointXYZI>(
                *msg,
                *_mapPtr
        );

        _ndt.setInputTarget(_mapPtr);
    }


    void initPoseWithNDTCallback(const geometry_msgs::PoseWithCovarianceStamped::ConstPtr &msg) {
        const auto& q = msg->pose.pose.orientation;
        const auto& p = msg->pose.pose.position;
        const double norm = q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w;
        if (msg->header.frame_id != "map" || !std::isfinite(norm) || norm < 0.9 || norm > 1.1 ||
            !std::isfinite(p.x) || !std::isfinite(p.y) || !std::isfinite(p.z))
        { publishGateStatus("INITIAL_POSE_REJECTED invalid pose"); return; }
        _initialGuess = tf::Pose(tf::Quaternion(q.x,q.y,q.z,q.w).normalized(), tf::Vector3(p.x,p.y,p.z));
        _pendingInitial = true; _haveAcceptedPose = false; _gateConfirmCount = 0;
        _initialDeadline = ros::WallTime::now() + ros::WallDuration(30.0);
        std_msgs::Bool health; health.data = false; _healthPub.publish(health);
        publishGateStatus("WAITING_INITIAL_CONFIRMATION");
    }
    void syncCallback(const sensor_msgs::PointCloud2::ConstPtr &pcMsg,
                      const nav_msgs::Odometry::ConstPtr &odomMsg) {
        // Confirmation consumes distinct fresh clouds, including while stationary.
        if (pcMsg->header.stamp <= _lastCloudStamp) return;
        _lastCloudStamp = pcMsg->header.stamp;
        _inputStamp = std::min(pcMsg->header.stamp, odomMsg->header.stamp);
        if (!inputsFresh()) return;
        _pcPtr = pcMsg;
        tf::poseMsgToTF(odomMsg->pose.pose, _baseOdom);
        if (_mapPtr->empty()) return;
        if (_pendingInitial && ros::WallTime::now() > _initialDeadline) {
            _pendingInitial = false;
            publishGateStatus("INITIAL_LOCALIZATION_TIMEOUT");
        }
        if (_pendingInitial) {
            match(pcMsg, _initialGuess, "initialpose");
            if (_haveAcceptedPose) _pendingInitial = false;
        } else if (_haveAcceptedPose && !_regions.empty()) {
            if (updateGateLatch((_odomMap * _baseOdom).getOrigin()))
                match(pcMsg, _odomMap * _baseOdom, "odom_update");
            else _gateConfirmCount = 0;
        }
        publishTF();
    }

    /**
     * Matching the point cloud with map to calculate `_odomMap`.
     *
     * @param pcPtr  The point cloud for matching.
     * @param baseMap The guess matrix.
     */
    void match(
            const sensor_msgs::PointCloud2::ConstPtr &pcPtr,
            const tf::Transform &baseMap,
            const string &trigger)
    {
        static chrono::steady_clock::time_point t0;
        static chrono::steady_clock::time_point t1;

        Cloud::Ptr tmpCloudPtr(
                new Cloud
        );

        pcl::fromROSMsg(
                *pcPtr,
                *tmpCloudPtr
        );

        Cloud::Ptr filteredCloudPtr(
                new Cloud
        );

        _voxelGridFilter.setInputCloud(
                tmpCloudPtr
        );

        _voxelGridFilter.filter(
                *filteredCloudPtr
        );

        Cloud::Ptr scanCloudPtr(
                new Cloud
        );

        for (const auto &p : *filteredCloudPtr)
        {
            const auto r =
                    hypot(
                            p.x,
                            p.y
                    );

            if (r > _cfg.ndt.minScanRange &&
                r < _cfg.ndt.maxScanRange)
            {
                scanCloudPtr->push_back(p);
            }
        }

        if (scanCloudPtr->size() < 10) { _gateConfirmCount = 0; publishGateStatus("NDT_SCAN_TOO_SMALL"); return; }
        _ndt.setInputSource(
                scanCloudPtr
        );

        Eigen::Affine3d baseMapMat;

        tf::poseTFToEigen(
                baseMap,
                baseMapMat
        );

        Cloud::Ptr outputCloudPtr(
                new Cloud
        );

        if (_cfg.ndt.debug)
        {
            t0 = chrono::steady_clock::now();
        }

        _ndt.align(
                *outputCloudPtr,
                baseMapMat.matrix().cast<float>()
        );

        if (_cfg.ndt.debug)
        {
            t1 = chrono::steady_clock::now();
        }

        auto tNDT =
                _ndt.getFinalTransformation();

        tf::Transform baseMapNDT;

        tf::poseEigenToTF(
                Eigen::Affine3d(
                        tNDT.cast<double>()
                ),
                baseMapNDT
        );

        const tf::Transform predictedBaseMap = baseMap;

        const double fitnessScore = _ndt.getFitnessScore();
        const bool converged = _ndt.hasConverged();

        if (!acceptNdtCandidate(
                predictedBaseMap,
                baseMapNDT,
                fitnessScore,
                converged,
                trigger))
        {
            return;
        }

        // 计算：
        //
        // T_map_odom =
        // T_map_base *
        // inverse(T_odom_base)
        //
        // 当前 WheelTech 系统中，
        // 这个 correction 最终作为：
        //
        // map -> odom
        //
        // 发布。
        _odomMap =
                baseMapNDT *
                _baseOdom.inverse();

        _haveAcceptedPose = true;

        if (_cfg.ndt.debug)
        {
            ROS_INFO(
                    "NDT: %ldms",
                    chrono::duration_cast<chrono::milliseconds>(
                            t1 - t0
                    ).count()
            );
        }

        ROS_INFO(
                "NDT Relocated: fitness=%.4f converged=%s trigger=%s",
                fitnessScore,
                converged ? "true" : "false",
                trigger.c_str()
        );
    }


    void publishTF()
    {
        if (!_haveAcceptedPose || !inputsFresh()) return;
        geometry_msgs::TransformStamped tfMsg;

        // 关键修改：
        //
        // map -> odom 向未来预发布 0.25 秒，
        // 避免 TEB 查询当前时刻 TF 时，
        // 最新 map -> odom 尚落后几十毫秒而出现：
        //
        // Lookup would require extrapolation into the future
        //
        tfMsg.header.stamp =
                ros::Time::now() +
                ros::Duration(
                        _cfg.tfPostdateSec
                );

        tfMsg.header.frame_id = "map";

        // 必须是 odom。
        tfMsg.child_frame_id =
                _cfg.odomFrame;

        tfMsg.transform.translation.x =
                _odomMap.getOrigin().x();

        tfMsg.transform.translation.y =
                _odomMap.getOrigin().y();

        tfMsg.transform.translation.z =
                _odomMap.getOrigin().z();

        tfMsg.transform.rotation.x =
                _odomMap.getRotation().x();

        tfMsg.transform.rotation.y =
                _odomMap.getRotation().y();

        tfMsg.transform.rotation.z =
                _odomMap.getRotation().z();

        tfMsg.transform.rotation.w =
                _odomMap.getRotation().w();

        _br.sendTransform(
                tfMsg
        );
    }
};


int main(
        int argc,
        char **argv)
{
    ros::init(
            argc,
            argv,
            "ccs_wheeltec_localizer"
    );

    ros::NodeHandle nh("~");

    Localizer localizer(
            nh
    );

    ros::spin();

    return 0;
}
