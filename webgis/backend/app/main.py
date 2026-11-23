"""Phase 1 基础 API；只提供健康检查与已验收项目元数据，不计算洪水。"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[2]
app = FastAPI(title="南宁洪水 WebGIS API", version="0.1.0")


@app.get("/api/health", summary="检查基础服务")
def health() -> dict:
    """无输入；返回服务标识与状态，不依赖外部数据站。"""
    return {"status": "ok", "service": "nanning-flood-webgis", "phase": 1}


@app.get("/api/project", summary="读取研究区及已验收数据摘要")
def project() -> dict:
    """无输入；读取本地 Phase 0 验收报告，只返回页面需要的公开元数据。"""
    try:
        report = json.loads(
            (PROJECT_ROOT / "docs/phase0_validation.json").read_text(encoding="utf-8")
        )
        rainfall = report["rainfall"]
        bbox = report["aoi"]["bbox_wsen"]
        if rainfall["dataset"] != "CHM_PRE V2" or len(bbox) != 4:
            raise ValueError("项目数据摘要与当前方案不符")
        return {
            "name": "南宁邕江洪水动态变化检测",
            "stage": "Phase 1 · 项目初始化",
            "study_area": {
                "name": "南宁邕江城区重点河段",
                "bbox_wsen": bbox,
                "area_km2": report["aoi"]["area_km2"],
                "crs": "EPSG:4326",
            },
            "datasets": {
                "dem": {
                    "name": "FABDEM v1.2",
                    "grid_label": "约 30 m",
                    "validated": report["dem"]["aoi_fully_covered"],
                },
                "rainfall": {
                    "name": "CHM_PRE V2",
                    "version": rainfall["repository_version"],
                    "grid_label": "0.1° · 逐日",
                    "date_labels": rainfall["date_labels"],
                    "cell_count": rainfall["shape"][1] * rainfall["shape"][2],
                    "daily_window": "前一日北京时间 20:00 至当日 20:00",
                    "validated": rainfall["source_values_replayed_exactly"],
                },
                "rivers": {
                    "name": "OpenStreetMap",
                    "geometry_label": "当前河道中心线",
                    "validated": report["rivers"]["main_channel_check"][
                        "main_channel_coverage_passed"
                    ],
                },
            },
        }
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        # 缺失文件时给出明确状态，不返回伪造的研究区或默认数据。
        raise HTTPException(status_code=503, detail="项目验收元数据不可用，请检查 Phase 0 报告。") from error
