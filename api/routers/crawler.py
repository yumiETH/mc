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

from fastapi import APIRouter, HTTPException

from ..schemas import CrawlerStartRequest, CrawlerStatusResponse
from ..services import crawler_manager

router = APIRouter(prefix="/crawler", tags=["crawler"])


@router.post("/start")
async def start_crawler(request: CrawlerStartRequest):
    """Start crawler task"""
    success = await crawler_manager.start(request)
    if not success:
        # Handle concurrent/duplicate requests: if process is already running, return 400 instead of 500
        if crawler_manager.process and crawler_manager.process.poll() is None:
            raise HTTPException(status_code=400, detail="Crawler is already running")
        raise HTTPException(status_code=500, detail="Failed to start crawler")

    qrcode = None
    qrcode_status = "not_required"
    if request.login_type.value == "qrcode" and not request.cookies:
        qrcode = await crawler_manager.wait_for_qrcode()
        if qrcode:
            qrcode_status = "ready"
        elif crawler_manager.is_qrcode_pending():
            qrcode_status = "pending"

    return {
        "status": "ok",
        "message": "Crawler started successfully",
        "task_id": crawler_manager.task_id,
        "qrcode_status": qrcode_status,
        "qrcode": qrcode,
    }


@router.post("/stop")
async def stop_crawler():
    """Stop crawler task"""
    success = await crawler_manager.stop()
    if not success:
        # Handle concurrent/duplicate requests: if process already exited/doesn't exist, return 400 instead of 500
        if not crawler_manager.process or crawler_manager.process.poll() is not None:
            raise HTTPException(status_code=400, detail="No crawler is running")
        raise HTTPException(status_code=500, detail="Failed to stop crawler")

    return {"status": "ok", "message": "Crawler stopped successfully"}


@router.get("/status", response_model=CrawlerStatusResponse)
async def get_crawler_status():
    """Get crawler status"""
    return crawler_manager.get_status()


@router.get("/qrcode")
async def get_login_qrcode(wait: float = 0):
    """Get latest login QR code for current crawler task"""
    qrcode = (
        await crawler_manager.wait_for_qrcode(timeout_seconds=wait)
        if wait > 0
        else crawler_manager.get_latest_qrcode()
    )
    if not qrcode:
        raise HTTPException(status_code=404, detail="QR code is not ready")
    return qrcode


@router.get("/logs")
async def get_logs(limit: int = 100):
    """Get recent logs"""
    logs = crawler_manager.logs[-limit:] if limit > 0 else crawler_manager.logs
    return {"logs": [log.model_dump() for log in logs]}
