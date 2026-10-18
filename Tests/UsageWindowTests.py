"""Host registry must prevent duplicate dispatchers, including fresh contexts."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Integrations/DaVinciResolve'))
import foldset_usage_ui as ui

class WindowTests(unittest.TestCase):
    def test_existing_host_window_reused_with_no_local_reference(self):
        resolve, bmd = MagicMock(), MagicMock()
        existing = resolve.Fusion.return_value.UIManager.FindWindow.return_value
        ui._window = None
        ui.open_window(resolve, bmd)
        resolve.Fusion.return_value.UIManager.FindWindow.assert_called_once_with('FoldsetFinderUsage')
        existing.Show.assert_called_once()
        existing.Raise.assert_called_once()
        bmd.UIDispatcher.assert_not_called()

    def test_repeated_invocation_does_not_touch_existing_results(self):
        resolve, bmd = MagicMock(), MagicMock()
        existing = resolve.Fusion.return_value.UIManager.FindWindow.return_value
        for _ in range(3):
            ui._window = None  # A separate script execution cannot be relied on.
            ui.open_window(resolve, bmd)
        self.assertEqual(existing.Raise.call_count, 3)
        existing.GetItems.assert_not_called()
        existing.Hide.assert_not_called()
        bmd.UIDispatcher.assert_not_called()

unittest.main()
