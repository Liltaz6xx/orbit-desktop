"""Tests for restricted Windows action routing; no Windows calls are performed."""
import unittest
from orbit.actions import (
    ActionPermissions, WindowsController, fast_action_route,
    authorise_model_action, identity_response,
)


class ActionTests(unittest.TestCase):
    def test_approved_launches(self):
        self.assertEqual(fast_action_route('ORBIT, open Visual Studio Code.'), ('open_app', 'vscode'))
        self.assertEqual(fast_action_route('Please open Spotify.'), ('open_app', 'spotify'))
        self.assertEqual(fast_action_route('Open my Downloads folder.'), ('open_folder', 'downloads'))
        self.assertEqual(fast_action_route('Open my ORBIT project folder.'), ('open_folder', 'orbit'))
        self.assertEqual(fast_action_route('Lock my computer.'), ('lock_pc', 'none'))

    def test_read_only_stats(self):
        self.assertEqual(fast_action_route('Check my RAM usage.'), ('system_info', 'ram'))
        self.assertEqual(fast_action_route('How much disk space is free on my PC?'), ('system_info', 'disk'))

    def test_no_negated_actions(self):
        self.assertIsNone(fast_action_route("Don't open Notepad"))
        self.assertIsNone(fast_action_route('Do not lock my PC'))
        self.assertIsNone(fast_action_route('Tell me how to open Notepad'))

    def test_no_hypothetical_actions(self):
        self.assertIsNone(fast_action_route('Can I open Notepad?'))
        self.assertIsNone(fast_action_route('Should I open Spotify?'))
        self.assertIsNone(fast_action_route('What happens if I lock my PC?'))

    def test_no_unapproved_tool_targets(self):
        self.assertFalse(authorise_model_action('Open some random app', 'open_app', 'cmd'))
        self.assertFalse(authorise_model_action('Open Spotify', 'open_app', 'notepad'))
        self.assertFalse(authorise_model_action('Open Spotify', 'open_folder', 'documents'))
        self.assertFalse(authorise_model_action('Lock my PC', 'lock_pc', 'spotify'))

    def test_maker_identity(self):
        self.assertIn('Maker', identity_response('Hello ORBIT'))
        self.assertIn('Liltaz6xx created ORBIT', identity_response('Who made you?'))
        self.assertIn("in charge of this ORBIT installation", identity_response("Am I your Maker?"))
        self.assertIn('Qwen team', identity_response('Who made your Qwen model?'))
        self.assertIn('own developers', identity_response('Who developed your underlying model?'))

    def test_full_command_required(self):
        for text in ("I could open Notepad", "Open Notepad if I need it", "Open Notepad and Spotify",
                     "Could you lock the PC if I leave?", "Open C:/Tools/Notepad.exe", "What is RAM?"):
            with self.subTest(text=text):
                self.assertIsNone(fast_action_route(text))
        self.assertEqual(fast_action_route("Could you open Notepad, please?"), ("open_app", "notepad"))

    def test_session_permissions_and_lock(self):
        permissions = ActionPermissions()
        self.assertFalse(permissions.needs_confirmation("system_info", "cpu"))
        self.assertTrue(permissions.needs_confirmation("open_app", "notepad"))
        permissions.approve("open_app", "notepad")
        self.assertFalse(permissions.needs_confirmation("open_app", "notepad"))
        self.assertTrue(permissions.needs_confirmation("open_app", "paint"))
        permissions.approve("lock_pc", "none")
        self.assertTrue(permissions.needs_confirmation("lock_pc", "none"))

    def test_controller_rejects_before_contacting_windows(self):
        controller = WindowsController()
        for action, target, approved in (("run_script", "none", True), ("open_app", "cmd", True),
                                         ("open_folder", "C:/", True), ("lock_pc", "none", False)):
            with self.subTest(action=action, target=target), self.assertRaises(PermissionError):
                controller.execute(action, target, approved=approved)


if __name__ == '__main__':
    unittest.main()
