"""Optional self-update: git-pulls the Haven Backup *installation* (not the backup repo).

Disabled by default and never run implicitly during a scheduled backup -- on
infrastructure like a Proxmox host, an unattended code update immediately
followed by a restart is exactly the kind of surprise you don't want on a
backup agent. Run `haven-backup update` manually, or opt into automatic checks
via config if you're comfortable with that tradeoff.
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from haven_backup.config_manager import ConfigManager
from haven_backup.logging_engine import LoggingEngine

INSTALL_ROOT = Path(__file__).resolve().parent.parent


class UpdateEngine:
    def __init__(self, config: ConfigManager, logger: LoggingEngine = None):
        self.config = config
        self.logger = logger or LoggingEngine()
        self.install_root = INSTALL_ROOT

    def is_update_due(self) -> bool:
        last = self.config.get_last_update_time()
        return last is None or (datetime.now() - last) >= timedelta(days=1)

    def run_auto_update_if_due(self):
        if not self.config.get_auto_update_enabled():
            return False
        if not self.is_update_due():
            return False
        return self.run_update()

    def run_update(self) -> bool:
        channel = self.config.get_update_channel()

        if not (self.install_root / ".git").exists():
            self.logger.warning("backup", "Not a git checkout; cannot self-update.")
            return False

        try:
            subprocess.run(["git", "fetch", "origin"], cwd=self.install_root, check=True, capture_output=True)
            subprocess.run(["git", "checkout", channel], cwd=self.install_root, check=True, capture_output=True)
            subprocess.run(
                ["git", "pull", "origin", channel], cwd=self.install_root, check=True, capture_output=True
            )
            self.config.set_last_update_time(datetime.now())
            self.logger.info("backup", f"Updated Haven Backup to latest '{channel}'.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error("backup", f"Self-update failed: {e.stderr}")
            return False

    def restart(self):
        self.logger.info("backup", "Restarting Haven Backup after update...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
