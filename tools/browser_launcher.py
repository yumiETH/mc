# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tools/browser_launcher.py
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


import os
import platform
import subprocess
import time
import socket
import signal
from typing import Optional, List, Tuple
import asyncio
from pathlib import Path

from tools import utils


class BrowserLauncher:
    """
    Browser launcher for detecting and launching user's Chrome/Edge browser
    Supports Windows and macOS systems
    """

    def __init__(self):
        self.system = platform.system()
        self.browser_process = None
        self.debug_port = None

    def detect_browser_paths(self) -> List[str]:
        """
        Detect available browser paths in system
        Returns list of browser paths sorted by priority
        """
        paths = []

        if self.system == "Windows":
            # Common Chrome/Edge installation paths on Windows
            possible_paths = [
                # Chrome paths
                os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                # Edge paths
                os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
                # Chrome Beta/Dev/Canary
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome Beta\Application\chrome.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome Dev\Application\chrome.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome SxS\Application\chrome.exe"),
            ]
        elif self.system == "Darwin":  # macOS
            # Common Chrome/Edge installation paths on macOS
            possible_paths = [
                # Chrome paths
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta",
                "/Applications/Google Chrome Dev.app/Contents/MacOS/Google Chrome Dev",
                "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
                # Edge paths
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Microsoft Edge Beta.app/Contents/MacOS/Microsoft Edge Beta",
                "/Applications/Microsoft Edge Dev.app/Contents/MacOS/Microsoft Edge Dev",
                "/Applications/Microsoft Edge Canary.app/Contents/MacOS/Microsoft Edge Canary",
            ]
        else:
            # Linux and other systems
            possible_paths = [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/google-chrome-beta",
                "/usr/bin/google-chrome-unstable",
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
                "/snap/bin/chromium",
                "/usr/bin/microsoft-edge",
                "/usr/bin/microsoft-edge-stable",
                "/usr/bin/microsoft-edge-beta",
                "/usr/bin/microsoft-edge-dev",
            ]

        # Check if path exists and is executable
        for path in possible_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                paths.append(path)

        return paths

    def find_available_port(self, start_port: int = 9222) -> int:
        """
        Find available port
        """
        port = start_port
        while port < start_port + 100:  # Try up to 100 ports
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                    return port
            except OSError:
                port += 1

        raise RuntimeError(f"Cannot find available port, tried {start_port} to {port-1}")

    def launch_browser(self, browser_path: str, debug_port: int, headless: bool = False,
                      user_data_dir: Optional[str] = None) -> subprocess.Popen:
        """
        Launch browser process
        """
        # Basic launch arguments
        args = [
            browser_path,
            f"--remote-debugging-port={debug_port}",
            "--remote-debugging-address=0.0.0.0",  # Allow remote access
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=TranslateUI",
            "--disable-ipc-flooding-protection",
            "--disable-hang-monitor",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--disable-dev-shm-usage",  # Avoid shared memory issues
            "--no-sandbox",  # Disable sandbox in CDP mode
            # Key anti-detection arguments
            "--disable-blink-features=AutomationControlled",  # Disable automation control flag
            "--exclude-switches=enable-automation",  # Exclude automation switch
            "--disable-infobars",  # Disable info bars
        ]

        # Headless mode
        if headless:
            args.extend([
                "--headless=new",  # Use new headless mode
                "--disable-gpu",
            ])
        else:
            # Extra arguments for non-headless mode
            args.extend([
                "--start-maximized",  # Maximize window, more like real user
            ])

        # User data directory
        if user_data_dir:
            args.append(f"--user-data-dir={user_data_dir}")

        utils.logger.info(f"[BrowserLauncher] Launching browser: {browser_path}")
        utils.logger.info(f"[BrowserLauncher] Debug port: {debug_port}")
        utils.logger.info(f"[BrowserLauncher] Headless mode: {headless}")
        self.debug_port = debug_port

        try:
            # On Windows, use CREATE_NEW_PROCESS_GROUP to prevent Ctrl+C from affecting subprocess
            if self.system == "Windows":
                process = subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                process = subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid  # Create new process group
                )

            self.browser_process = process
            return process

        except Exception as e:
            utils.logger.error(f"[BrowserLauncher] Failed to launch browser: {e}")
            raise

    def _is_debug_port_alive(self) -> bool:
        """Check whether the CDP debug port is still being listened on."""
        if not self.debug_port:
            return False

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                return s.connect_ex(("localhost", self.debug_port)) == 0
        except Exception:
            return False

    def _find_pid_by_port(self) -> Optional[int]:
        """Find the process PID currently listening on the configured debug port."""
        if not self.debug_port:
            return None

        try:
            if self.system == "Windows":
                result = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=10,
                )
                # Windows may expose the listening endpoint as 127.0.0.1:PORT,
                # 0.0.0.0:PORT or [::]:PORT depending on Chrome and system config.
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) < 5:
                        continue
                    protocol, local_addr, _remote_addr, state, pid = parts[:5]
                    if protocol.upper() != "TCP" or state.upper() != "LISTENING":
                        continue
                    if local_addr.endswith(f":{self.debug_port}") or local_addr.endswith(f"]:{self.debug_port}"):
                        return int(pid)
            else:
                result = subprocess.run(
                    ["lsof", "-ti", f"tcp:{self.debug_port}"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=10,
                )
                pid_text = result.stdout.strip().splitlines()
                if pid_text:
                    return int(pid_text[0])
        except Exception as e:
            utils.logger.warning(f"[BrowserLauncher] Failed to resolve PID by debug port: {e}")

        return None

    def wait_for_browser_ready(self, debug_port: int, timeout: int = 30) -> bool:
        """
        Wait for browser to be ready
        """
        utils.logger.info(f"[BrowserLauncher] Waiting for browser to be ready on port {debug_port}...")

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    result = s.connect_ex(('localhost', debug_port))
                    if result == 0:
                        utils.logger.info(f"[BrowserLauncher] Browser is ready on port {debug_port}")
                        return True
            except Exception:
                pass

            time.sleep(0.5)

        utils.logger.error(f"[BrowserLauncher] Browser failed to be ready within {timeout} seconds")
        return False

    def get_browser_info(self, browser_path: str) -> Tuple[str, str]:
        """
        Get browser info (name and version)
        """
        try:
            if "chrome" in browser_path.lower():
                name = "Google Chrome"
            elif "edge" in browser_path.lower() or "msedge" in browser_path.lower():
                name = "Microsoft Edge"
            elif "chromium" in browser_path.lower():
                name = "Chromium"
            else:
                name = "Unknown Browser"

            # Try to get version info
            try:
                result = subprocess.run([browser_path, "--version"],
                                      capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=5)
                version = result.stdout.strip() if result.stdout else "Unknown Version"
            except:
                version = "Unknown Version"

            return name, version

        except Exception:
            return "Unknown Browser", "Unknown Version"

    def cleanup(self):
        """
        Cleanup resources, close browser process
        """
        if not self.browser_process:
            return

        process = self.browser_process

        if process.poll() is not None:
            if not self._is_debug_port_alive():
                utils.logger.info("[BrowserLauncher] Browser process already exited, no cleanup needed")
                self.browser_process = None
                return
            utils.logger.warning(
                "[BrowserLauncher] Launcher process exited but debug port is still alive, "
                "will try to terminate the real browser process by port"
            )

        utils.logger.info("[BrowserLauncher] Closing browser process...")

        try:
            if self.system == "Windows":
                pid_to_kill = process.pid if process.poll() is None else self._find_pid_by_port()
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        utils.logger.warning("[BrowserLauncher] Normal termination timeout, using taskkill to force kill")
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                            capture_output=True,
                            check=False,
                            encoding='utf-8',
                            errors='ignore'
                        )
                        process.wait(timeout=5)
                elif pid_to_kill:
                    utils.logger.info(f"[BrowserLauncher] Killing browser by debug-port PID: {pid_to_kill}")
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid_to_kill)],
                        capture_output=True,
                        check=False,
                        encoding='utf-8',
                        errors='ignore'
                    )
                else:
                    utils.logger.warning("[BrowserLauncher] Could not resolve browser PID from debug port")
            else:
                pgid = os.getpgid(process.pid)
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    utils.logger.info("[BrowserLauncher] Browser process group does not exist, may have exited")
                else:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        utils.logger.warning("[BrowserLauncher] Graceful shutdown timeout, sending SIGKILL")
                        os.killpg(pgid, signal.SIGKILL)
                        process.wait(timeout=5)

            utils.logger.info("[BrowserLauncher] Browser process closed")
        except Exception as e:
            utils.logger.warning(f"[BrowserLauncher] Error closing browser process: {e}")
        finally:
            self.browser_process = None
