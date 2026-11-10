"""Create the Yangtze River Delta region in the currently open STK 11 scenario.

Planning scope:
  Shanghai Municipality, Jiangsu Province, Zhejiang Province, and Anhui Province.

The STK 11 AreaTarget object accepts one closed polygon.  The merged administrative
boundary is a MultiPolygon, so the mainland is stored as YangtzeRiverDelta and the
two detached island polygons are stored as YangtzeRiverDelta_Island_1/2.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import win32com.client
from shapely.geometry import mapping, shape
from shapely.ops import unary_union


WORKSPACE = Path(__file__).resolve().parent
SOURCE_DIR = WORKSPACE / "source_data"
SOURCE_GEOJSON = SOURCE_DIR / "geoBoundaries-CHN-ADM1_simplified.geojson"
OUTPUT_GEOJSON = WORKSPACE / "yangtze_river_delta_boundary.geojson"

SOURCE_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/"
    "releaseData/gbOpen/CHN/ADM1/"
    "geoBoundaries-CHN-ADM1_simplified.geojson"
)
PLANNING_SOURCE = (
    "https://app.www.gov.cn/govdata/gov/201912/01/451514/article.html"
)
TARGET_NAMES = {
    "Shanghai Municipality",
    "Jiangsu Province",
    "Zhejiang Province",
    "Anhui Province",
}


def load_source_geojson() -> dict:
    SOURCE_DIR.mkdir(exist_ok=True)
    if not SOURCE_GEOJSON.exists():
        urllib.request.urlretrieve(SOURCE_URL, SOURCE_GEOJSON)
    return json.loads(SOURCE_GEOJSON.read_text(encoding="utf-8"))


def merged_geometry(data: dict):
    selected = [
        shape(feature["geometry"])
        for feature in data["features"]
        if feature["properties"].get("shapeName") in TARGET_NAMES
    ]
    if len(selected) != 4:
        found = sorted(
            feature["properties"].get("shapeName", "")
            for feature in data["features"]
            if feature["properties"].get("shapeName") in TARGET_NAMES
        )
        raise RuntimeError(f"Expected 4 province-level features, found {found!r}")
    result = unary_union(selected)
    if not result.is_valid:
        result = result.buffer(0)
    return result


def save_reproducible_boundary(geometry) -> None:
    feature = {
        "type": "Feature",
        "properties": {
            "name": "Yangtze River Delta",
            "name_zh": "长三角地区",
            "planning_scope": "上海市、江苏省、浙江省、安徽省全域",
            "planning_source": PLANNING_SOURCE,
            "geometry_source": SOURCE_URL,
        },
        "geometry": mapping(geometry),
    }
    OUTPUT_GEOJSON.write_text(
        json.dumps(feature, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_or_create_area_target(scenario, name: str):
    try:
        return scenario.Children.Item(name)
    except Exception:
        return scenario.Children.New(2, name)  # eAreaTarget


def set_polygon(area_target, polygon) -> int:
    # Shapely coordinates are longitude/latitude; STK expects latitude/longitude.
    coordinates = list(polygon.exterior.coords)
    if coordinates[0] == coordinates[-1]:
        coordinates = coordinates[:-1]
    boundary = [[float(lat), float(lon)] for lon, lat in coordinates]
    area_target.CommonTasks.SetAreaTypePattern(boundary)
    area_target.AutoCentroid = True
    return len(boundary)


def configure_graphics(area_target, is_mainland: bool) -> None:
    # Keep the object visible and distinguish the detached island components.
    graphics = area_target.Graphics
    try:
        graphics.IsObjectGraphicsVisible = True
    except Exception:
        pass
    try:
        graphics.Color = 0x00A5FF if is_mainland else 0x00D7FF
        graphics.LineWidth = 3 if is_mainland else 2
    except Exception:
        pass
    try:
        graphics.FillVisible = True
    except Exception:
        pass


def main() -> None:
    data = load_source_geojson()
    geometry = merged_geometry(data)
    save_reproducible_boundary(geometry)

    polygons = sorted(
        list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry],
        key=lambda polygon: polygon.area,
        reverse=True,
    )

    app = win32com.client.GetActiveObject("STK11.Application")
    root = app.Personality2
    scenario = root.CurrentScenario
    if scenario is None:
        raise RuntimeError("No STK scenario is currently open")

    root.UnitPreferences.SetCurrentUnit("AngleUnit", "deg")
    created = []
    root.BeginUpdate()
    try:
        for index, polygon in enumerate(polygons):
            name = "YangtzeRiverDelta" if index == 0 else f"YangtzeRiverDelta_Island_{index}"
            target = get_or_create_area_target(scenario, name)
            count = set_polygon(target, polygon)
            target.ShortDescription = "长三角地区" if index == 0 else f"长三角地区离岛组成部分 {index}"
            target.LongDescription = (
                "依据《长江三角洲区域一体化发展规划纲要》，范围包括上海市、"
                "江苏省、浙江省、安徽省全域。规划依据："
                f"{PLANNING_SOURCE}；几何数据：geoBoundaries CHN ADM1。"
            )
            configure_graphics(target, index == 0)
            created.append((name, count, polygon.area))
    finally:
        root.EndUpdate()

    root.SaveScenario()
    print(f"Scenario: {scenario.InstanceName}")
    print(f"Planning scope: 上海市、江苏省、浙江省、安徽省全域")
    print(f"Geometry type: {geometry.geom_type}; components: {len(polygons)}")
    for name, count, area in created:
        print(f"Created/updated {name}: {count} boundary points; planar area={area:.6f} deg^2")
    print(f"Boundary GeoJSON: {OUTPUT_GEOJSON}")


if __name__ == "__main__":
    main()
