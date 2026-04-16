"""Tests for clip_common.html_utils."""

from clip_common.html_utils import strip_html


class TestStripHtml:
    def test_plain_text_unchanged(self):
        assert strip_html("hello world") == "hello world"

    def test_anchor_tag_preserves_text(self):
        assert strip_html('<a href="https://example.com">click here</a>') == "click here"

    def test_paragraph_tags_removed(self):
        assert strip_html("<p>first</p><p>second</p>") == "firstsecond"

    def test_nested_tags(self):
        assert strip_html("<b><em>bold italic</em></b>") == "bold italic"

    def test_rich_paragraph_with_link(self):
        html = 'Check out <a href="https://example.com">this site</a> for more info.'
        assert strip_html(html) == "Check out this site for more info."

    def test_empty_string(self):
        assert strip_html("") == ""

    def test_attributes_stripped(self):
        assert strip_html('<span class="foo" id="bar">text</span>') == "text"

    def test_html_entities_decoded(self):
        result = strip_html("&lt;hello&gt; &amp; world")
        assert result == "<hello> & world"
