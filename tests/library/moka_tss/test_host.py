# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - Python system monitor for USB-C displays
# Mascota fork - tests for host process coordination and instance lock

"""Tests for host instance lock and single instance error handling."""

import tempfile
import unittest
from pathlib import Path

from library.moka_tss.host import InstanceLock, SingleInstanceError
from library.moka_tss.paths import user_data_dir


class TestHostInstanceLock(unittest.TestCase):
    """Test suite for InstanceLock acquire, release, and context manager."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.lock_path = Path(self.temp_dir.name) / "moka_tss.lock"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_acquire_and_release(self) -> None:
        """Lock acquires file handle and release allows re-acquisition."""
        lock1 = InstanceLock(self.lock_path)
        lock1.acquire()
        self.assertIsNotNone(lock1._file)
        self.assertTrue(self.lock_path.exists())

        lock1.release()
        self.assertIsNone(lock1._file)

        lock2 = InstanceLock(self.lock_path)
        lock2.acquire()
        self.assertIsNotNone(lock2._file)
        lock2.release()
        self.assertIsNone(lock2._file)

    def test_second_instance_fails(self) -> None:
        """Second lock attempt on the same path raises SingleInstanceError."""
        lock1 = InstanceLock(self.lock_path)
        lock1.acquire()
        try:
            lock2 = InstanceLock(self.lock_path)
            with self.assertRaises(SingleInstanceError):
                lock2.acquire()
        finally:
            lock1.release()

        # Re-acquisition must succeed after release
        lock3 = InstanceLock(self.lock_path)
        lock3.acquire()
        lock3.release()

    def test_context_manager(self) -> None:
        """Context manager acquires on entry and releases on exit."""
        with InstanceLock(self.lock_path) as lock:
            self.assertIsNotNone(lock._file)
            second_lock = InstanceLock(self.lock_path)
            with self.assertRaises(SingleInstanceError):
                second_lock.acquire()

        # Outside the with block, lock is released and can be acquired again
        reacquired = InstanceLock(self.lock_path)
        reacquired.acquire()
        reacquired.release()

    def test_default_lock_path(self) -> None:
        """Default lock path points to user_data_dir() / 'moka_tss.lock'."""
        lock = InstanceLock()
        expected_path = user_data_dir() / "moka_tss.lock"
        self.assertEqual(lock.lock_path, expected_path)
