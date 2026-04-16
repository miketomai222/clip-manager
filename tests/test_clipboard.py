"""Tests for clipd.clipboard HTML capture logic."""

from unittest.mock import MagicMock, patch

import pytest

from clip_common.types import ContentType
from clipd.clipboard import (
    _get_clipboard_html,
    _get_clipboard_types,
    _is_sensitive_in_types,
    WlPasteWatcher,
)


class TestGetClipboardTypes:
    def test_returns_list_of_types(self):
        mock_result = MagicMock(returncode=0, stdout="text/plain\ntext/html\n")
        with patch("clipd.clipboard.subprocess.run", return_value=mock_result):
            types = _get_clipboard_types()
        assert "text/plain" in types
        assert "text/html" in types

    def test_returns_empty_on_failure(self):
        mock_result = MagicMock(returncode=1, stdout="")
        with patch("clipd.clipboard.subprocess.run", return_value=mock_result):
            types = _get_clipboard_types()
        assert types == []

    def test_returns_empty_on_timeout(self):
        import subprocess
        with patch("clipd.clipboard.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("wl-paste", 2)):
            types = _get_clipboard_types()
        assert types == []


class TestIsSensitiveInTypes:
    def test_password_hint_detected(self):
        assert _is_sensitive_in_types(["x-kde-passwordManagerHint", "text/plain"])

    def test_password_in_type_name_detected(self):
        assert _is_sensitive_in_types(["application/x-password", "text/plain"])

    def test_normal_types_not_sensitive(self):
        assert not _is_sensitive_in_types(["text/plain", "text/html"])

    def test_empty_list_not_sensitive(self):
        assert not _is_sensitive_in_types([])


class TestGetClipboardHtml:
    def test_returns_html_content(self):
        html = '<p>Hello <a href="http://example.com">world</a></p>'
        mock_result = MagicMock(returncode=0, stdout=html)
        with patch("clipd.clipboard.subprocess.run", return_value=mock_result):
            result = _get_clipboard_html()
        assert result == html

    def test_returns_none_on_failure(self):
        mock_result = MagicMock(returncode=1, stdout="")
        with patch("clipd.clipboard.subprocess.run", return_value=mock_result):
            result = _get_clipboard_html()
        assert result is None

    def test_passes_html_type_flag(self):
        mock_result = MagicMock(returncode=0, stdout="<b>hi</b>")
        with patch("clipd.clipboard.subprocess.run", return_value=mock_result) as mock_run:
            _get_clipboard_html()
        cmd = mock_run.call_args[0][0]
        assert "--type" in cmd
        assert "text/html" in cmd


class TestWlPasteWatcherReadAndNotify:
    def _make_watcher(self, callback):
        with patch("clipd.clipboard._init_xfixes", return_value=None):
            watcher = WlPasteWatcher(on_new_clip=callback)
        return watcher

    def test_captures_html_clip_when_html_type_available(self):
        received = []
        watcher = self._make_watcher(lambda c, t: received.append((c, t)))

        html = '<p>Hello <a href="http://x.com">link</a></p>'
        with patch("clipd.clipboard._get_clipboard_types",
                   return_value=["text/plain", "text/html"]), \
             patch("clipd.clipboard._get_clipboard_html", return_value=html):
            watcher._read_and_notify()

        assert len(received) == 1
        assert received[0] == (html, ContentType.HTML)

    def test_captures_text_clip_when_no_html_type(self):
        received = []
        watcher = self._make_watcher(lambda c, t: received.append((c, t)))

        with patch("clipd.clipboard._get_clipboard_types",
                   return_value=["text/plain"]), \
             patch("clipd.clipboard._get_clipboard_text", return_value="plain text"):
            watcher._read_and_notify()

        assert len(received) == 1
        assert received[0] == ("plain text", ContentType.TEXT)

    def test_skips_sensitive_clipboard(self):
        received = []
        watcher = self._make_watcher(lambda c, t: received.append((c, t)))

        with patch("clipd.clipboard._get_clipboard_types",
                   return_value=["x-kde-passwordManagerHint", "text/plain"]):
            watcher._read_and_notify()

        assert received == []

    def test_deduplicates_repeated_html_clip(self):
        received = []
        watcher = self._make_watcher(lambda c, t: received.append((c, t)))

        html = "<b>same</b>"
        with patch("clipd.clipboard._get_clipboard_types",
                   return_value=["text/html"]), \
             patch("clipd.clipboard._get_clipboard_html", return_value=html):
            watcher._read_and_notify()
            watcher._read_and_notify()

        assert len(received) == 1
