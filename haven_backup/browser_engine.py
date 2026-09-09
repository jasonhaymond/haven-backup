"""Interactive snapshot browser for manual, ad-hoc restores (not used by scheduled backups)."""

import os
import re

from haven_backup.restore_engine import RestoreEngine


class BrowserEngine:
    def __init__(self, restore_engine: RestoreEngine):
        self.restore_engine = restore_engine
        self._last_restore_paths = []

    def _display_folder(self, snapshot_files, current_path):
        folders, files = {}, []
        for path in snapshot_files:
            if not path.startswith(current_path):
                continue
            rel = path[len(current_path):].lstrip("/\\")
            parts = re.split(r"[/\\]", rel, maxsplit=1)
            if len(parts) == 1:
                files.append(parts[0])
            else:
                folders[parts[0]] = None

        folders = sorted(folders.keys())
        files = sorted(files)

        print("\nFolders:")
        for i, folder in enumerate(folders):
            print(f"  {i}) [D] {folder}")
        print("Files:")
        for i, name in enumerate(files):
            print(f"  {i + len(folders)}) [F] {name}")

        return folders, files

    def browse_snapshot(self, snapshot_id: str):
        snapshot = self.restore_engine.load_snapshot(snapshot_id)
        snapshot_files = snapshot.get("files", {})
        current_path = ""
        stack = []

        while True:
            folders, files = self._display_folder(snapshot_files, current_path)
            print("\nOptions: u) up  r) restore here  s) search  q) quit")
            choice = input("Choice: ").strip()

            if choice == "q":
                break
            elif choice == "u":
                if stack:
                    current_path = stack.pop()
            elif choice == "r":
                self._restore_menu(snapshot_id, current_path)
            elif choice == "s":
                term = input("Search term/regex: ")
                try:
                    pattern = re.compile(term)
                except re.error:
                    print("Invalid regex")
                    continue
                matches = [f for f in snapshot_files if pattern.search(f)]
                print(f"\n{len(matches)} match(es):" if matches else "No matches")
                for m in matches:
                    print(f"  {m}")
            else:
                try:
                    idx = int(choice)
                    if idx < len(folders):
                        stack.append(current_path)
                        current_path = os.path.join(current_path, folders[idx])
                except ValueError:
                    print("Invalid choice")

    def _restore_menu(self, snapshot_id, current_path):
        loc = input("Restore to [o]riginal location or [c]ustom path? ").strip().lower()
        restore_root = input("Custom path: ").strip() if loc == "c" else None
        restored = self.restore_engine.restore_paths(snapshot_id, [current_path], restore_root)
        self._last_restore_paths = restored
        print(f"[OK] Restored {len(restored)} file(s)")
