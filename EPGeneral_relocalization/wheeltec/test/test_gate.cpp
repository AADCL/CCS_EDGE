// SPDX-License-Identifier: GPL-3.0-only
#include "ccs_candidate_gate.h"
#include "fast_lio_localization/allowed_regions.h"
#include <cassert>
#include <limits>
int main() {
    int count=0; std::string reason;
    auto accept = [&](bool initial, bool empty, bool converged, double fitness, double jump) {
        return ccs_wheeltec::acceptCandidate(initial,empty,true,1.,.35,true,converged,
            fitness,2.,jump,1.,0.,.52,2,count,reason);
    };
    assert(!accept(true,true,true,.5,0.));
    assert(reason=="WAITING_CONFIRMATION");
    assert(accept(true,true,true,.5,0.)); // stationary, no regions
    assert(!accept(false,true,true,.5,0.)); // later corrections paused
    assert(!accept(true,true,false,.5,0.) && count==0);
    assert(!accept(true,true,true,3.,0.) && reason=="FITNESS_TOO_HIGH");
    assert(!accept(true,true,true,.5,2.) && reason=="POSE_JUMP_TOO_LARGE");
    assert(!accept(true,true,true,std::numeric_limits<double>::quiet_NaN(),0.));
    ndt_gate::Regions regions;
    ndt_gate::Polygon triangle{{0.,0.},{4.,0.},{2.,3.}};
    assert(regions.replace({{7,triangle,false}},reason));
    assert(!regions.replace({{1,triangle,false},{1,triangle,false}},reason));
    assert(regions.items().at(0).id==7); // invalid replacement is atomic
    assert(regions.replace({},reason) && regions.empty());
    return 0;
}
