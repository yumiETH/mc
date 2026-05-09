# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/services/crawler_manager.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

import asyncio
import json
import os
import signal
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..schemas import CrawlerStartRequest, LogEntry

QR_CODE_EVENT_PREFIX = "MEDIACRAWLER_EVENT:"


@dataclass
class CrawlerTaskState:
    """Runtime state for one platform task."""

    platform: str
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    process: Optional[subprocess.Popen] = None
    status: str = "idle"
    started_at: Optional[datetime] = None
    current_config: Optional[CrawlerStartRequest] = None
    task_id: Optional[str] = None
    latest_qrcode: Optional[Dict[str, Any]] = None
    qrcode_required: bool = False
    qrcode_not_required: bool = False
    qrcode_event: Optional[asyncio.Event] = None
    log_id: int = 0
    logs: List[LogEntry] = field(default_factory=list)
    read_task: Optional[asyncio.Task] = None


class CrawlerManager:
    """Crawler process manager.

    Rule:
    - Same platform: only one running task.
    - Different platforms: can run concurrently.
    """

    def __init__(self):
        self._states: Dict[str, CrawlerTaskState] = {}
        self._project_root = Path(__file__).parent.parent.parent
        self._log_queue: Optional[asyncio.Queue] = None
        self._state_guard = asyncio.Lock()
        self._last_active_platform: Optional[str] = None

    def _get_or_create_state(self, platform: str) -> CrawlerTaskState:
        state = self._states.get(platform)
        if state is None:
            state = CrawlerTaskState(platform=platform)
            self._states[platform] = state
        return state

    def _resolve_platform(self, platform: Optional[str]) -> Optional[str]:
        if platform:
            return platform

        # Prefer last active running platform to keep old API behavior stable.
        if self._last_active_platform:
            state = self._states.get(self._last_active_platform)
            if state and state.process and state.process.poll() is None:
                return self._last_active_platform

        for key, state in self._states.items():
            if state.process and state.process.poll() is None:
                return key

        return None

    @property
    def process(self) -> Optional[subprocess.Popen]:
        platform = self._resolve_platform(None)
        if not platform:
            return None
        return self._states[platform].process

    @property
    def logs(self) -> List[LogEntry]:
        platform = self._resolve_platform(None)
        if not platform:
            return []
        return self._states[platform].logs

    def get_log_queue(self) -> asyncio.Queue:
        if self._log_queue is None:
            self._log_queue = asyncio.Queue()
        return self._log_queue

    def _create_log_entry(self, state: CrawlerTaskState, message: str, level: str = "info") -> LogEntry:
        state.log_id += 1
        entry = LogEntry(
            id=state.log_id,
            timestamp=datetime.now().strftime("%H:%M:%S"),
            level=level,
            message=f"[{state.platform}] {message}",
            platform=state.platform,
        )
        state.logs.append(entry)
        if len(state.logs) > 500:
            state.logs = state.logs[-500:]
        return entry

    async def _push_log(self, entry: LogEntry):
        if self._log_queue is not None:
            try:
                self._log_queue.put_nowait(entry)
            except asyncio.QueueFull:
                pass

    def _parse_log_level(self, line: str) -> str:
        line_upper = line.upper()
        if "ERROR" in line_upper or "FAILED" in line_upper:
            return "error"
        if "WARNING" in line_upper or "WARN" in line_upper:
            return "warning"
        if "SUCCESS" in line_upper or "完成" in line or "成功" in line:
            return "success"
        if "DEBUG" in line_upper:
            return "debug"
        return "info"

    def _update_qrcode_state_from_log(self, state: CrawlerTaskState, line: str) -> None:
        if state.latest_qrcode or not state.qrcode_required:
            return

        login_skipped_markers = (
            "Login state result: True",
            "Use cache login state",
            "Ping zhihu successfully",
            "Login state verified by cookies",
            "Begin search",
            "Begin get",
            "Crawler finished",
        )
        if any(marker in line for marker in login_skipped_markers):
            state.qrcode_not_required = True
            if state.qrcode_event:
                state.qrcode_event.set()

    def _handle_structured_event(self, state: CrawlerTaskState, line: str) -> bool:
        if not line.startswith(QR_CODE_EVENT_PREFIX):
            return False

        raw_payload = line[len(QR_CODE_EVENT_PREFIX):]
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return True

        if payload.get("event") == "login_qrcode":
            state.latest_qrcode = payload
            if state.qrcode_event:
                state.qrcode_event.set()
            entry = self._create_log_entry(state, "Login QR code captured, waiting for scan.", "success")
            try:
                queue = self.get_log_queue()
                queue.put_nowait(entry)
            except asyncio.QueueFull:
                pass

        return True

    async def wait_for_qrcode(self, timeout_seconds: float = 30.0, platform: Optional[str] = None) -> Optional[Dict[str, Any]]:
        platform = self._resolve_platform(platform)
        if not platform:
            return None

        state = self._states[platform]
        if state.latest_qrcode:
            return state.latest_qrcode
        if state.qrcode_not_required or not state.qrcode_event:
            return None

        try:
            await asyncio.wait_for(state.qrcode_event.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return state.latest_qrcode

        return state.latest_qrcode

    async def start(self, config: CrawlerStartRequest) -> bool:
        platform = config.platform.value
        state = self._get_or_create_state(platform)

        async with state.lock:
            if state.process and state.process.poll() is None:
                return False

            state.logs = []
            state.log_id = 0

            cmd = self._build_command(config)
            state.task_id = uuid.uuid4().hex
            state.latest_qrcode = None
            state.qrcode_required = (config.login_type.value == "qrcode" and not config.cookies)
            state.qrcode_not_required = False
            state.qrcode_event = asyncio.Event()

            entry = self._create_log_entry(state, f"Starting crawler: {' '.join(cmd)}", "info")
            await self._push_log(entry)

            try:
                state.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                    cwd=str(self._project_root),
                    env={
                        **os.environ,
                        "PYTHONUNBUFFERED": "1",
                        "MEDIACRAWLER_QR_OUTPUT": "api",
                        "MEDIACRAWLER_TASK_ID": state.task_id,
                        "MEDIACRAWLER_TASK_PLATFORM": platform,
                    },
                )
                state.status = "running"
                state.started_at = datetime.now()
                state.current_config = config

                entry = self._create_log_entry(
                    state,
                    f"Crawler started on platform: {platform}, type: {config.crawler_type.value}",
                    "success",
                )
                await self._push_log(entry)

                state.read_task = asyncio.create_task(self._read_output(platform))
                self._last_active_platform = platform
                return True
            except Exception as e:
                state.status = "error"
                state.task_id = None
                state.qrcode_required = False
                state.qrcode_not_required = False
                state.qrcode_event = None
                entry = self._create_log_entry(state, f"Failed to start crawler: {str(e)}", "error")
                await self._push_log(entry)
                return False

    async def stop(self, platform: Optional[str] = None) -> bool:
        platform = self._resolve_platform(platform)
        if not platform:
            return False

        state = self._states[platform]
        async with state.lock:
            if not state.process or state.process.poll() is not None:
                return False

            state.status = "stopping"
            entry = self._create_log_entry(state, "Sending SIGTERM to crawler process...", "warning")
            await self._push_log(entry)

            try:
                state.process.send_signal(signal.SIGTERM)

                for _ in range(30):
                    if state.process.poll() is not None:
                        break
                    await asyncio.sleep(0.5)

                if state.process.poll() is None:
                    entry = self._create_log_entry(state, "Process not responding, sending SIGKILL...", "warning")
                    await self._push_log(entry)
                    state.process.kill()

                entry = self._create_log_entry(state, "Crawler process terminated", "info")
                await self._push_log(entry)
            except Exception as e:
                entry = self._create_log_entry(state, f"Error stopping crawler: {str(e)}", "error")
                await self._push_log(entry)

            self._reset_state_runtime(state)
            return True

    def _status_dict(self, state: CrawlerTaskState) -> dict:
        return {
            "status": state.status,
            "task_id": state.task_id,
            "platform": state.current_config.platform.value if state.current_config else state.platform,
            "crawler_type": state.current_config.crawler_type.value if state.current_config else None,
            "started_at": state.started_at.isoformat() if state.started_at else None,
            "error_message": None,
        }

    def get_status(self, platform: Optional[str] = None) -> dict:
        platform = self._resolve_platform(platform)
        if platform and platform in self._states:
            status = self._status_dict(self._states[platform])
        else:
            status = {
                "status": "idle",
                "task_id": None,
                "platform": None,
                "crawler_type": None,
                "started_at": None,
                "error_message": None,
            }

        platforms = {name: self._status_dict(state) for name, state in self._states.items()}
        status["platforms"] = platforms
        status["running_count"] = sum(1 for s in self._states.values() if s.process and s.process.poll() is None)
        return status

    def get_latest_qrcode(self, platform: Optional[str] = None) -> Optional[Dict[str, Any]]:
        platform = self._resolve_platform(platform)
        if not platform:
            return None
        return self._states[platform].latest_qrcode

    def is_qrcode_pending(self, platform: Optional[str] = None) -> bool:
        platform = self._resolve_platform(platform)
        if not platform:
            return False

        state = self._states[platform]
        if state.latest_qrcode:
            return False
        if not state.qrcode_required or state.qrcode_not_required:
            return False
        return bool(state.process and state.process.poll() is None)

    def get_logs(self, platform: Optional[str] = None, limit: int = 100) -> List[LogEntry]:
        if platform:
            state = self._states.get(platform)
            if not state:
                return []
            logs = state.logs
            return logs[-limit:] if limit > 0 else logs

        merged: List[LogEntry] = []
        for state in self._states.values():
            merged.extend(state.logs)
        merged.sort(key=lambda x: (x.timestamp, x.id))
        return merged[-limit:] if limit > 0 else merged

    def _build_command(self, config: CrawlerStartRequest) -> list:
        cmd = ["uv", "run", "python", "main.py"]

        cmd.extend(["--platform", config.platform.value])
        cmd.extend(["--lt", config.login_type.value])
        cmd.extend(["--type", config.crawler_type.value])
        cmd.extend(["--save_data_option", config.save_option.value])

        if config.crawler_type.value == "search" and config.keywords:
            cmd.extend(["--keywords", config.keywords])
        elif config.crawler_type.value == "detail" and config.specified_ids:
            cmd.extend(["--specified_id", config.specified_ids])
        elif config.crawler_type.value == "creator" and config.creator_ids:
            cmd.extend(["--creator_id", config.creator_ids])

        if config.start_page != 1:
            cmd.extend(["--start", str(config.start_page)])

        cmd.extend(["--get_comment", "true" if config.enable_comments else "false"])
        cmd.extend(["--get_sub_comment", "true" if config.enable_sub_comments else "false"])

        if config.cookies:
            cmd.extend(["--cookies", config.cookies])

        cmd.extend(["--headless", "true" if config.headless else "false"])

        return cmd

    def _reset_state_runtime(self, state: CrawlerTaskState):
        state.status = "idle"
        state.current_config = None
        state.task_id = None
        state.qrcode_required = False
        state.qrcode_not_required = False
        state.qrcode_event = None
        if state.read_task:
            state.read_task.cancel()
            state.read_task = None

    async def _read_output(self, platform: str):
        state = self._states.get(platform)
        if not state:
            return

        loop = asyncio.get_event_loop()

        try:
            while state.process and state.process.poll() is None:
                line = await loop.run_in_executor(None, state.process.stdout.readline)
                if line:
                    line = line.strip()
                    if line:
                        if self._handle_structured_event(state, line):
                            continue
                        self._update_qrcode_state_from_log(state, line)
                        level = self._parse_log_level(line)
                        entry = self._create_log_entry(state, line, level)
                        await self._push_log(entry)

            if state.process and state.process.stdout:
                remaining = await loop.run_in_executor(None, state.process.stdout.read)
                if remaining:
                    for line in remaining.strip().split("\n"):
                        if line.strip():
                            line = line.strip()
                            if self._handle_structured_event(state, line):
                                continue
                            self._update_qrcode_state_from_log(state, line)
                            level = self._parse_log_level(line)
                            entry = self._create_log_entry(state, line, level)
                            await self._push_log(entry)

            if state.status == "running":
                exit_code = state.process.returncode if state.process else -1
                if exit_code == 0:
                    entry = self._create_log_entry(state, "Crawler completed successfully", "success")
                else:
                    entry = self._create_log_entry(state, f"Crawler exited with code: {exit_code}", "warning")
                await self._push_log(entry)
                self._reset_state_runtime(state)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            entry = self._create_log_entry(state, f"Error reading output: {str(e)}", "error")
            await self._push_log(entry)


crawler_manager = CrawlerManager()
