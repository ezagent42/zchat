"""Tests for check_irc_connectivity."""
import socket
import pytest
from unittest.mock import patch, MagicMock

from zchat.cli.irc_manager import check_irc_connectivity


def test_unreachable_server_raises():
    """Unreachable host raises ConnectionError."""
    with pytest.raises(ConnectionError, match="Cannot reach IRC server"):
        check_irc_connectivity("192.0.2.1", 1, timeout=0.5)


def test_reachable_server_succeeds():
    """Mocked successful connection returns without error."""
    mock_sock = MagicMock()
    with patch("zchat.cli.irc_manager.socket.create_connection", return_value=mock_sock):
        check_irc_connectivity("127.0.0.1", 6667)
    mock_sock.close.assert_called_once()


def test_tls_wraps_socket():
    """TLS=True wraps the socket with SSL."""
    mock_sock = MagicMock()
    mock_ssl_sock = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.wrap_socket.return_value = mock_ssl_sock

    with patch("zchat.cli.irc_manager.socket.create_connection", return_value=mock_sock), \
         patch("zchat.cli.irc_manager.ssl.create_default_context", return_value=mock_ctx):
        check_irc_connectivity("example.com", 6697, tls=True)

    mock_ctx.wrap_socket.assert_called_once_with(mock_sock, server_hostname="example.com")
    mock_ssl_sock.close.assert_called_once()


def test_tls_failure_raises():
    """TLS handshake failure raises ConnectionError."""
    mock_sock = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.wrap_socket.side_effect = OSError("SSL handshake failed")

    with patch("zchat.cli.irc_manager.socket.create_connection", return_value=mock_sock), \
         patch("zchat.cli.irc_manager.ssl.create_default_context", return_value=mock_ctx):
        with pytest.raises(ConnectionError, match="Cannot reach IRC server"):
            check_irc_connectivity("example.com", 6697, tls=True)
