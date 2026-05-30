"""Unit tests for ConnectionManager."""
import json
import socket
import threading
import time
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Patch tkinter before import so tests run headless
sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("tkinter.ttk", MagicMock())
sys.modules.setdefault("tkinter.messagebox", MagicMock())

from radha_gcs import ConnectionManager, SUCCESS, DANGER, SUBTEXT, WARN  # noqa: E402


class TestConnectionManagerSend(unittest.TestCase):

    def setUp(self):
        self.on_telem  = MagicMock()
        self.on_ack    = MagicMock()
        self.on_status = MagicMock()
        self.cm = ConnectionManager(self.on_telem, self.on_ack, self.on_status)

    def test_send_returns_false_when_not_connected(self):
        result = self.cm.send({"cmd": "ARM"})
        self.assertFalse(result)

    def test_send_returns_true_and_writes_newline_delimited_json(self):
        mock_sock = MagicMock()
        self.cm._sock    = mock_sock
        self.cm._running = True
        result = self.cm.send({"cmd": "HOVER"})
        self.assertTrue(result)
        sent = mock_sock.sendall.call_args[0][0]
        payload = json.loads(sent.decode().rstrip("\n"))
        self.assertEqual(payload["cmd"], "HOVER")
        self.assertTrue(sent.endswith(b"\n"))

    def test_send_disconnects_on_socket_error(self):
        mock_sock = MagicMock()
        mock_sock.sendall.side_effect = OSError("broken pipe")
        self.cm._sock    = mock_sock
        self.cm._running = True
        result = self.cm.send({"cmd": "LAND"})
        self.assertFalse(result)
        self.assertFalse(self.cm._running)


class TestConnectionManagerRecvLoop(unittest.TestCase):

    def _make_fake_socket(self, lines):
        """Return a mock socket that yields the given newline-delimited lines then EOF."""
        payloads = [("\n".join(lines) + "\n").encode()]
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = payloads + [b""]
        return mock_sock

    def setUp(self):
        self.on_telem  = MagicMock()
        self.on_ack    = MagicMock()
        self.on_status = MagicMock()
        self.cm = ConnectionManager(self.on_telem, self.on_ack, self.on_status)
        self.cm._intentional = True  # suppress reconnect in tests

    def _run_recv(self, lines):
        self.cm._sock    = self._make_fake_socket(lines)
        self.cm._running = True
        t = threading.Thread(target=self.cm._recv_loop)
        t.start()
        t.join(timeout=2)

    def test_telemetry_packet_dispatched(self):
        telem = {"roll": 1.2, "pitch": -0.5, "yaw": 182.3, "mode": "HOVER", "armed": 1}
        self._run_recv([json.dumps(telem)])
        self.on_telem.assert_called_once_with(telem)
        self.on_ack.assert_not_called()

    def test_ack_packet_dispatched(self):
        ack_pkt = {"ack": "ARM", "status": "OK"}
        self._run_recv([json.dumps(ack_pkt)])
        self.on_ack.assert_called_once_with(ack_pkt)
        self.on_telem.assert_not_called()

    def test_bad_json_silently_ignored(self):
        self._run_recv(["not json at all }{"])
        self.on_telem.assert_not_called()
        self.on_ack.assert_not_called()

    def test_multiple_packets_in_one_chunk(self):
        pkts = [
            json.dumps({"roll": 0.0, "mode": "DISARMED"}),
            json.dumps({"ack": "DISARM", "status": "OK"}),
        ]
        self._run_recv(pkts)
        self.assertEqual(self.on_telem.call_count, 1)
        self.assertEqual(self.on_ack.call_count, 1)

    def test_info_event_dispatched_as_telemetry(self):
        info_pkt = {"info": "PHONE_CONNECTED"}
        self._run_recv([json.dumps(info_pkt)])
        self.on_telem.assert_called_once_with(info_pkt)

    def test_dms_event_dispatched_as_telemetry(self):
        dms_pkt = {"dms": "FIRED", "action": "HOVER"}
        self._run_recv([json.dumps(dms_pkt)])
        self.on_telem.assert_called_once_with(dms_pkt)

    def test_disconnected_status_called_on_eof(self):
        self._run_recv([])
        self.on_status.assert_called_with("DISCONNECTED", SUBTEXT)


class TestConnectionManagerConnectedProperty(unittest.TestCase):

    def setUp(self):
        self.cm = ConnectionManager(MagicMock(), MagicMock(), MagicMock())

    def test_not_connected_initially(self):
        self.assertFalse(self.cm.connected)

    def test_connected_when_running_and_sock(self):
        self.cm._running = True
        self.cm._sock    = MagicMock()
        self.assertTrue(self.cm.connected)

    def test_not_connected_when_running_but_no_sock(self):
        self.cm._running = True
        self.cm._sock    = None
        self.assertFalse(self.cm.connected)


if __name__ == "__main__":
    unittest.main()
