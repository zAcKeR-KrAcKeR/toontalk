"""
VideoDB Sandbox lifecycle manager.
Singleton pattern — one sandbox reused across a session to minimize cost.
Handles creation, readiness wait, and auto-stop.
"""

import asyncio
import logging
from typing import Optional
from videodb import connect

# SandboxTier removed from videodb 0.4.5 — use string values directly
class SandboxTier:
    medium = "medium"
    small  = "small"

logger = logging.getLogger(__name__)


class SandboxManager:
    """
    Manages a single VideoDB sandbox per server session.
    Creates on first use, reuses for subsequent calls, stops on shutdown.
    """

    def __init__(self, tier: str = "medium"):
        self._conn = None
        self._sandbox = None
        self._tier = SandboxTier.medium if tier == "medium" else SandboxTier.small
        self._lock = asyncio.Lock()

    def _get_conn(self):
        if self._conn is None:
            self._conn = connect()
        return self._conn

    async def get_sandbox_id(self) -> str:
        """
        Returns an active sandbox ID.
        Creates one if not exists or if stopped.
        """
        async with self._lock:
            conn = self._get_conn()

            # Check if existing sandbox is still active
            if self._sandbox is not None:
                try:
                    self._sandbox.refresh()
                    if self._sandbox.is_active:
                        logger.info(f"Reusing sandbox: {self._sandbox.id}")
                        return self._sandbox.id
                    else:
                        logger.warning(
                            f"Sandbox {self._sandbox.id} is no longer active "
                            f"(status: {self._sandbox.status}). Creating new one."
                        )
                        self._sandbox = None
                except Exception as e:
                    logger.warning(f"Could not refresh sandbox: {e}. Creating new one.")
                    self._sandbox = None

            # Try to reuse an existing active sandbox from the account
            try:
                for sb in conn.list_sandboxes():
                    if sb.is_active and str(sb.tier) == str(self._tier):
                        self._sandbox = sb
                        logger.info(f"Found existing active sandbox: {sb.id}")
                        return sb.id
            except Exception as e:
                logger.warning(f"Could not list sandboxes: {e}")

            # Create a fresh sandbox
            logger.info(f"Creating new sandbox (tier={self._tier})...")
            self._sandbox = conn.create_sandbox(
                tier=self._tier,
                name="toontalk-sandbox",
            )
            logger.info(f"Sandbox created: {self._sandbox.id}, status: {self._sandbox.status}")

            # Wait for it to become active
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._sandbox.wait_for_ready(timeout=300, interval=5),
            )
            logger.info(f"Sandbox ready: {self._sandbox.id}")
            return self._sandbox.id

    async def stop(self):
        """Stop the sandbox to conserve credits."""
        async with self._lock:
            if self._sandbox is not None:
                try:
                    self._sandbox.refresh()
                    if self._sandbox.is_active:
                        logger.info(f"Stopping sandbox: {self._sandbox.id}")
                        self._sandbox.stop()
                        self._sandbox.wait_for_stop(timeout=120)
                        logger.info(f"Sandbox {self._sandbox.id} stopped.")
                except Exception as e:
                    logger.error(f"Error stopping sandbox: {e}")
                finally:
                    self._sandbox = None

    def get_connection(self):
        """Return the raw VideoDB connection."""
        return self._get_conn()

    @property
    def current_sandbox_id(self) -> Optional[str]:
        if self._sandbox is not None and self._sandbox.is_active:
            return self._sandbox.id
        return None


# ─── Global singleton ─────────────────────────────────────────────────────────
import os

_sandbox_manager: Optional[SandboxManager] = None


def get_sandbox_manager() -> SandboxManager:
    global _sandbox_manager
    if _sandbox_manager is None:
        tier = os.getenv("SANDBOX_TIER", "medium")
        _sandbox_manager = SandboxManager(tier=tier)
    return _sandbox_manager
