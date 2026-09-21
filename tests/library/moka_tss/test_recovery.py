# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from unittest.mock import MagicMock
from library.moka_tss.app import MokaApp


class TestRecovery(unittest.TestCase):
    def setUp(self):
        self.screen_mock = MagicMock()
        self.renderer_mock = MagicMock()
        self.app = MokaApp(
            screen=self.screen_mock,
            renderer=self.renderer_mock,
            tray_enabled=False
        )

    def test_screen_recovery(self):
        # Mocks screen raising exceptions twice and then recovering on the third attempt
        self.app.simulate = False

        # Make screen.show fail twice, then succeed
        self.screen_mock.show.side_effect = [Exception("error 1"), Exception("error 2"), None]

        self.app.step()
        self.app.step()
        self.app.step()

        # Verify reset is never called since there were only 2 consecutive errors
        self.screen_mock.reset.assert_not_called()
        self.assertEqual(self.app._consecutive_screen_errors, 0)
        self.assertEqual(self.screen_mock.show.call_count, 3)

    def test_screen_recovery_trigger(self):
        # Mocks 3 consecutive screen errors and checks `.reset()` is called
        self.app.simulate = False
        self.screen_mock.show.side_effect = Exception("error")

        self.app.step()
        self.app.step()
        self.app.step()

        self.screen_mock.reset.assert_called_once()
        self.assertEqual(self.app._consecutive_screen_errors, 0)

    def test_render_recovery(self):
        # Simulate 3 consecutive render failures and verify _load_default_sprites is invoked
        self.renderer_mock.side_effect = Exception("render error")
        self.app._load_default_sprites = MagicMock(return_value=MagicMock())

        self.app.step()
        self.app.step()
        self.app.step()

        self.app._load_default_sprites.assert_called_once()
        self.assertEqual(self.app._consecutive_render_errors, 0)

    def test_callback_never_raises(self):
        # Simulate failures inside the recovery block itself to assert the app doesn't crash
        self.renderer_mock.side_effect = Exception("render error")
        self.app._load_default_sprites = MagicMock(side_effect=Exception("load error"))

        # Should not raise an exception
        try:
            self.app.step()
            self.app.step()
            self.app.step()
        except Exception as e:
            self.fail(f"step() raised an exception unexpectedly: {e}")

        self.app._load_default_sprites.assert_called_once()
        # _consecutive_render_errors should be reset even if recovery fails
        self.assertEqual(self.app._consecutive_render_errors, 0)

        # Also test screen reset failure
        self.renderer_mock.side_effect = None
        self.screen_mock.show.side_effect = Exception("screen error")
        self.screen_mock.reset.side_effect = Exception("reset error")

        try:
            self.app.step()
            self.app.step()
            self.app.step()
        except Exception as e:
            self.fail(f"step() raised an exception unexpectedly: {e}")

        self.screen_mock.reset.assert_called_once()
        # _consecutive_screen_errors should be reset even if recovery fails
        self.assertEqual(self.app._consecutive_screen_errors, 0)


if __name__ == '__main__':
    unittest.main()
