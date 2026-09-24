// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <cmath>
#include <string>

namespace ccs_wheeltec {
// A caller must supply distinct, fresh scans; geometry and ROS transport stay outside.
inline bool acceptCandidate(bool initial, bool empty, bool predictedInside,
    double candidateDistance, double exitMargin, bool requireConverged, bool converged,
    double fitness, double maxFitness, double jump, double maxJump,
    double yaw, double maxYaw, int required, int& confirmations, std::string& reason) {
    if (!initial && empty) reason = "WAITING_ALLOWED_AREA";
    else if (!initial && !predictedInside) reason = "PREDICTED_POSE_OUTSIDE_AREA";
    else if (!initial && candidateDistance <= -exitMargin) reason = "CANDIDATE_OUTSIDE_AREA";
    else if (requireConverged && !converged) reason = "NDT_NOT_CONVERGED";
    else if (!std::isfinite(fitness) || fitness > maxFitness) reason = "FITNESS_TOO_HIGH";
    else if (!std::isfinite(jump) || !std::isfinite(yaw) || jump > maxJump || yaw > maxYaw)
        reason = "POSE_JUMP_TOO_LARGE";
    else {
        if (confirmations < required) ++confirmations;
        reason = confirmations < required ? "WAITING_CONFIRMATION" : "ACCEPTED";
        return confirmations >= required;
    }
    confirmations = 0;
    return false;
}
}
