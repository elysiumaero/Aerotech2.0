"""Tests for protocol packet parsing logic in RADHAApp._on_telem."""
import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("tkinter.ttk", MagicMock())
sys.modules.setdefault("tkinter.messagebox", MagicMock())


class TestTelemRouting(unittest.TestCase):
    """Test that _on_telem dispatches packets to the right handler."""

    def _make_app(self):
        """Return a minimal RADHAApp with mocked UI methods."""
        import radha_gcs as gcs
        root = MagicMock()
        root.after = lambda delay, fn, *args: fn(*args)
        with patch.object(gcs.RADHAApp, "_build_ui"), \
             patch.object(gcs.RADHAApp, "_switch_tab"), \
             patch.object(gcs.RADHAApp, "_tick"), \
             patch.object(gcs.FlightLog, "__init__", return_value=None), \
             patch.object(gcs.FlightLog, "write"), \
             patch.object(gcs.FlightLog, "write_telem"):
            app = gcs.RADHAApp.__new__(gcs.RADHAApp)
            app.root      = root
            app._armed    = False
            app._preset_segs = []
            app._gps_vars = {}
            app._fix_lbl  = None
            app._bat_lbl  = None
            app._tv       = {k: MagicMock() for k in
                             ["roll","pitch","yaw","alt_cm","bat_mv","mode"]}
            app.conn      = MagicMock()
            app.dms       = MagicMock()
            app.flog      = MagicMock()
            app._log      = MagicMock()
            app._arm_lbl  = MagicMock()
            app._mode_lbl = MagicMock()
            app._apply_gps   = MagicMock()
            app._apply_telem = MagicMock()
            app._draw_ati    = MagicMock()
        return app

    def test_phone_packet_routes_to_apply_gps(self):
        app = self._make_app()
        pkt = {"type": "phone", "lat": 28.6, "lon": 77.2, "fix": 1, "sats": 8,
               "heading": 182.0, "baro_cm": 21500, "alt": 215.0}
        app._on_telem(pkt)
        app._apply_gps.assert_called_once_with(pkt)
        app._apply_telem.assert_not_called()

    def test_telemetry_packet_routes_to_apply_telem(self):
        app = self._make_app()
        pkt = {"roll": 1.2, "pitch": -0.5, "yaw": 182.3,
               "alt_cm": 45, "bat_mv": 11800, "mode": "HOVER", "armed": 1}
        app._on_telem(pkt)
        app._apply_telem.assert_called_once_with(pkt)
        app._apply_gps.assert_not_called()

    def test_info_packet_logs_and_does_not_route_to_telem(self):
        app = self._make_app()
        app._on_telem({"info": "PHONE_CONNECTED"})
        app._apply_telem.assert_not_called()
        app._log.assert_called()
        msg = app._log.call_args[0][0]
        self.assertIn("PHONE", msg)

    def test_info_phone_disconnected_logs_warning(self):
        app = self._make_app()
        app._on_telem({"info": "PHONE_DISCONNECTED"})
        import radha_gcs as gcs
        app._log.assert_called_with("ESP32: PHONE_DISCONNECTED", gcs.WARN)

    def test_dms_fired_packet_logs_danger(self):
        app = self._make_app()
        app._on_telem({"dms": "FIRED", "action": "HOVER"})
        app._apply_telem.assert_not_called()
        import radha_gcs as gcs
        # color arg should be DANGER
        call_kwargs = app._log.call_args[0]
        self.assertEqual(call_kwargs[1], gcs.DANGER)

    def test_gcs_connected_info_logs_success(self):
        app = self._make_app()
        app._on_telem({"info": "GCS_CONNECTED"})
        import radha_gcs as gcs
        app._log.assert_called_with("ESP32: GCS_CONNECTED", gcs.SUCCESS)


class TestBatteryAlarm(unittest.TestCase):
    """Test that _apply_telem colors the battery label correctly."""

    def _make_app_with_bat_lbl(self):
        import radha_gcs as gcs
        root = MagicMock()
        root.after = lambda delay, fn, *args: fn(*args)
        app = gcs.RADHAApp.__new__(gcs.RADHAApp)
        app.root = root
        app._armed = False
        app._tv = {k: MagicMock() for k in
                   ["roll", "pitch", "yaw", "alt_cm", "bat_mv", "mode"]}
        app._bat_lbl  = MagicMock()
        app._arm_lbl  = MagicMock()
        app._mode_lbl = MagicMock()
        app._log      = MagicMock()
        app._draw_ati = MagicMock()
        app.flog      = MagicMock()
        return app

    def _telem(self, bat_mv):
        return {"roll": 0.0, "pitch": 0.0, "yaw": 0.0,
                "alt_cm": 50, "bat_mv": bat_mv, "mode": "HOVER", "armed": 1}

    def test_normal_voltage_text_color(self):
        import radha_gcs as gcs
        app = self._make_app_with_bat_lbl()
        app._apply_telem(self._telem(11800))
        app._bat_lbl.config.assert_called_with(fg=gcs.TEXT)

    def test_warn_voltage_orange(self):
        import radha_gcs as gcs
        app = self._make_app_with_bat_lbl()
        app._apply_telem(self._telem(10400))
        app._bat_lbl.config.assert_called_with(fg=gcs.WARN)

    def test_critical_voltage_red(self):
        import radha_gcs as gcs
        app = self._make_app_with_bat_lbl()
        app._apply_telem(self._telem(9500))
        app._bat_lbl.config.assert_called_with(fg=gcs.DANGER)


if __name__ == "__main__":
    unittest.main()
