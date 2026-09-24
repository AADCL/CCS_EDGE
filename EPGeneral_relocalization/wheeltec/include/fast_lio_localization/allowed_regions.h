#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <vector>

namespace ndt_gate
{
struct Point
{
    double x;
    double y;
};

using Polygon = std::vector<Point>;

inline double segmentDistance(Point p, Point a, Point b)
{
    const double dx = b.x - a.x;
    const double dy = b.y - a.y;
    const double length2 = dx * dx + dy * dy;
    const double t = length2 > 0.0
        ? std::max(0.0, std::min(1.0, ((p.x-a.x)*dx + (p.y-a.y)*dy)/length2))
        : 0.0;
    return std::hypot(p.x - a.x - t*dx, p.y - a.y - t*dy);
}

inline double cross(Point a, Point b, Point c)
{
    return (b.x-a.x)*(c.y-a.y) - (b.y-a.y)*(c.x-a.x);
}

inline bool intersects(Point a, Point b, Point c, Point d)
{
    constexpr double eps = 1e-9;
    const double ab_c = cross(a,b,c), ab_d = cross(a,b,d);
    const double cd_a = cross(c,d,a), cd_b = cross(c,d,b);
    if (((ab_c > eps && ab_d < -eps) || (ab_c < -eps && ab_d > eps)) &&
        ((cd_a > eps && cd_b < -eps) || (cd_a < -eps && cd_b > eps)))
        return true;
    return segmentDistance(c,a,b) <= eps || segmentDistance(d,a,b) <= eps ||
           segmentDistance(a,c,d) <= eps || segmentDistance(b,c,d) <= eps;
}

inline bool validPolygon(const Polygon& polygon, std::string& error)
{
    if (polygon.size() < 3) { error = "at least 3 vertices required"; return false; }
    double twiceArea = 0.0;
    for (std::size_t i = 0; i < polygon.size(); ++i)
    {
        const Point a = polygon[i], b = polygon[(i+1)%polygon.size()];
        if (!std::isfinite(a.x) || !std::isfinite(a.y))
        { error = "non-finite vertex"; return false; }
        if (segmentDistance(a,b,b) < 1e-6)
        { error = "duplicate adjacent vertex"; return false; }
        twiceArea += cross(polygon.front(), a, b);
        for (std::size_t j = i+1; j < polygon.size(); ++j)
        {
            if (j == i+1 || (i == 0 && j == polygon.size()-1)) continue;
            if (intersects(a,b,polygon[j],polygon[(j+1)%polygon.size()]))
            { error = "self-intersecting polygon"; return false; }
        }
    }
    if (!std::isfinite(twiceArea) || std::fabs(twiceArea) < 1e-6)
    { error = "zero or invalid polygon area"; return false; }
    // Adjacent edges must not double back over one another.
    for (std::size_t i = 0; i < polygon.size(); ++i)
    {
        Point a = polygon[i], b = polygon[(i+1)%polygon.size()];
        Point c = polygon[(i+2)%polygon.size()];
        if (segmentDistance(c,a,b) < 1e-9 || segmentDistance(a,b,c) < 1e-9)
        { error = "overlapping adjacent edges"; return false; }
    }
    error.clear();
    return true;
}

inline double signedDistance(const Polygon& polygon, Point p)
{
    if (polygon.size() < 3 || !std::isfinite(p.x) || !std::isfinite(p.y))
        return -std::numeric_limits<double>::infinity();
    bool inside = false;
    double distance = std::numeric_limits<double>::infinity();
    for (std::size_t i = 0, j = polygon.size()-1; i < polygon.size(); j = i++)
    {
        Point a = polygon[j], b = polygon[i];
        distance = std::min(distance, segmentDistance(p,a,b));
        if ((a.y > p.y) != (b.y > p.y) &&
            p.x < (b.x-a.x)*(p.y-a.y)/(b.y-a.y)+a.x)
            inside = !inside;
    }
    return inside ? distance : -distance;
}

struct Region
{
    std::int32_t id;
    Polygon polygon;
    bool inside = false;
};

class Regions
{
public:
    const std::vector<Region>& items() const { return regions_; }
    bool empty() const { return regions_.empty(); }

    std::int32_t add(const Polygon& polygon, std::string& error)
    {
        if (!validPolygon(polygon,error)) return -1;
        if (nextId_ == std::numeric_limits<std::int32_t>::max())
        { error = "region ID limit reached"; return -1; }
        const auto id = nextId_++;
        regions_.push_back({id,polygon,false});
        return id;
    }

    bool replace(std::vector<Region> replacement, std::string& error) {
        if (replacement.size() > 128) { error = "too many regions"; return false; }
        std::vector<std::int32_t> ids;
        std::int32_t next = 1;
        for (auto& region : replacement) {
            if (region.id <= 0 || region.id == std::numeric_limits<std::int32_t>::max() ||
                std::find(ids.begin(), ids.end(), region.id) != ids.end() || region.polygon.size() > 512)
            { error = "invalid region id or size"; return false; }
            if (!validPolygon(region.polygon, error)) return false;
            ids.push_back(region.id); next = std::max(next, region.id + 1); region.inside = false;
        }
        regions_.swap(replacement); nextId_ = next; error.clear(); return true;
    }
    bool erase(std::int32_t id)
    {
        const auto it = std::find_if(regions_.begin(),regions_.end(),
                                    [id](const Region& r){ return r.id == id; });
        if (it == regions_.end()) return false;
        regions_.erase(it);
        return true;
    }

    double distance(Point p) const
    {
        double best = -std::numeric_limits<double>::infinity();
        for (const auto& r : regions_) best = std::max(best,signedDistance(r.polygon,p));
        return best;
    }

    bool update(Point predicted, double enterMargin, double exitMargin)
    {
        bool anyInside = false;
        for (auto& r : regions_)
        {
            const double d = signedDistance(r.polygon,predicted);
            if (!std::isfinite(d)) r.inside = false;
            else if (!r.inside && d >= enterMargin) r.inside = true;
            else if (r.inside && d <= -exitMargin) r.inside = false;
            anyInside = anyInside || r.inside;
        }
        return anyInside;
    }

private:
    std::vector<Region> regions_;
    std::int32_t nextId_ = 1;
};
} // namespace ndt_gate
