# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/routers/crawler.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..schemas import CrawlerStartRequest
from ..services import crawler_manager

router = APIRouter(prefix="/crawler", tags=["crawler"])


@router.post("/start")
async def start_crawler(request: CrawlerStartRequest):
    """Start crawler task"""
    success = await crawler_manager.start(request)
    if not success:
        # Same platform is single-task mode.
        status = crawler_manager.get_status(request.platform.value)
        if status.get("status") == "running":
            raise HTTPException(status_code=400, detail=f"Crawler is already running on platform: {request.platform.value}")
        raise HTTPException(status_code=500, detail="Failed to start crawler")

    qrcode = None
    qrcode_status = "not_required"
    if request.login_type.value == "qrcode" and not request.cookies:
        qrcode = await crawler_manager.wait_for_qrcode(platform=request.platform.value)
        if qrcode:
            qrcode_status = "ready"
        elif crawler_manager.is_qrcode_pending(platform=request.platform.value):
            qrcode_status = "pending"

    return {
        "status": "ok",
        "message": "Crawler started successfully",
        "platform": request.platform.value,
        "task_id": crawler_manager.get_status(request.platform.value).get("task_id"),
        "qrcode_status": qrcode_status,
        "qrcode": qrcode,
    }


@router.post("/stop")
async def stop_crawler(platform: Optional[str] = Query(default=None, description="Platform code, e.g. dy/xhs")):
    """Stop crawler task"""
    success = await crawler_manager.stop(platform=platform)
    if not success:
        if platform:
            raise HTTPException(status_code=400, detail=f"No crawler is running on platform: {platform}")
        raise HTTPException(status_code=400, detail="No crawler is running")

    return {"status": "ok", "message": "Crawler stopped successfully", "platform": platform}


@router.get("/status")
async def get_crawler_status(platform: Optional[str] = Query(default=None, description="Platform code, e.g. dy/xhs")):
    """Get crawler status"""
    return crawler_manager.get_status(platform=platform)


@router.get("/qrcode")
async def get_login_qrcode(
    wait: float = 0,
    platform: Optional[str] = Query(default=None, description="Platform code, e.g. dy/xhs"),
):
    """Get latest login QR code for current crawler task"""
    qrcode = (
        await crawler_manager.wait_for_qrcode(timeout_seconds=wait, platform=platform)
        if wait > 0
        else crawler_manager.get_latest_qrcode(platform=platform)
    )
    if not qrcode:
        raise HTTPException(status_code=404, detail="QR code is not ready")
    return qrcode


@router.get("/logs")
async def get_logs(
    limit: int = 100,
    platform: Optional[str] = Query(default=None, description="Platform code, e.g. dy/xhs"),
):
    """Get recent logs"""
    logs = crawler_manager.get_logs(platform=platform, limit=limit)
    return {"logs": [log.model_dump() for log in logs]}
