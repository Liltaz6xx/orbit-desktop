"""Release integrity and in-app update notification regression tests."""

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from time import monotonic
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from orbit.config import Settings
from orbit.preferences import Preferences
from orbit.updater import RELEASE_PAGE, REPOSITORY, Update, latest_update
from orbit.window import OrbitWindow


def release_fixture():
    version = "99.1.0"
    filename = f"ORBIT-Desktop-{version}-Windows-x64-Setup.exe"
    url = f"https://github.com/{REPOSITORY}/releases/download/v{version}/{filename}"
    update = Update(version, filename, url, "a" * 64, 100)
    release = {
        "tag_name": f"v{version}",
        "draft": False,
        "prerelease": False,
        "assets": [
            {"name": filename, "browser_download_url": url, "digest": f"sha256:{update.digest}", "size": 100}
        ],
    }
    return release, update


class LatestReleaseTests(unittest.TestCase):
    def test_major_release_is_newer_and_requires_a_verified_asset(self):
        release, expected = release_fixture()
        with patch("orbit.updater.urlopen", return_value=io.BytesIO(json.dumps(release).encode())):
            self.assertEqual(latest_update("0.7.0-beta.11"), expected)
        with patch("orbit.updater.urlopen", return_value=io.BytesIO(json.dumps(release).encode())):
            self.assertIsNone(latest_update(expected.version))
        release["assets"][0]["digest"] = None
        with patch("orbit.updater.urlopen", return_value=io.BytesIO(json.dumps(release).encode())):
            with self.assertRaisesRegex(ValueError, "checksum"):
                latest_update("0.7.0-beta.11")


class UpdateNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_until(self, predicate):
        deadline = monotonic() + 4
        while not predicate() and monotonic() < deadline:
            QTest.qWait(15)
        self.assertTrue(predicate())

    def test_startup_notice_rechecks_on_click_and_has_no_automatic_install(self):
        _, update = release_fixture()
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(database_path=Path(folder) / "memory.sqlite3")
            with (
                patch.object(QApplication, "platformName", return_value="windows"),
                patch("orbit.window.DiscordPresence.start"),
                patch("orbit.window.installed_copy", return_value=True),
                patch("orbit.window.latest_update", return_value=update) as check,
            ):
                window = OrbitWindow(settings, voice=Mock(), preferences=Preferences())
                try:
                    window.show()
                    self.wait_until(lambda: not window.update_banner.isHidden())
                    self.assertIn(update.version, window.update_notice.text())
                    self.assertFalse(window.installing_update)
                    self.assertEqual(check.call_count, 1)
                    with patch.object(window, "confirm_update") as confirm:
                        window.update_action.click()
                        self.wait_until(lambda: confirm.called)
                        confirm.assert_called_once_with(update)
                    self.assertEqual(check.call_count, 2)
                finally:
                    window.close()
                    for thread in window.workers.threads:
                        thread.join(2)

    def test_portable_copy_offers_release_page(self):
        _, update = release_fixture()
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(database_path=Path(folder) / "memory.sqlite3")
            with (
                patch("orbit.window.installed_copy", return_value=False),
                patch("orbit.window.latest_update", return_value=update),
                patch("orbit.window.QDesktopServices.openUrl", return_value=True) as browse,
            ):
                window = OrbitWindow(settings, voice=Mock(), preferences=Preferences())
                try:
                    window.check_for_update(manual=True)
                    self.wait_until(lambda: browse.called)
                    self.assertEqual(browse.call_args.args[0].toString(), RELEASE_PAGE)
                    self.assertEqual(window.update_action.text(), "Get update")
                    self.assertFalse(window.installing_update)
                finally:
                    window.close()
                    for thread in window.workers.threads:
                        thread.join(2)
