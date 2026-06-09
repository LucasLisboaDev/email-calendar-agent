"""
ingestion/html_cleaner.py

Strips HTML from email bodies and returns clean plain text.
This runs before any LLM call — the AI should never see raw HTML.

Why this matters:
- HTML emails can be 50-500x larger than their text content
- Raw HTML burns tokens and confuses classification
- Clean text = better LLM performance + lower API costs
"""

import re
from html.parser import HTMLParser


class _HTMLStripper(HTMLParser):
    """
    Minimal HTML parser that extracts text content only.
    Ignores scripts, styles, and all tags.
    """

    def __init__(self):
        super().__init__()
        self.reset()
        self._fed = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("script", "style", "head"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style", "head"):
            self._skip = False
        # Add a newline after block-level elements for readability
        if tag.lower() in ("p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4"):
            self._fed.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._fed.append(data)

    def get_text(self):
        return "".join(self._fed)


def clean_email_body(body: str) -> str:
    """
    Clean an email body for LLM consumption.

    Steps:
      1. Detect if the body is HTML
      2. Strip all HTML tags if so
      3. Decode HTML entities (&amp; → &, &nbsp; → space, etc.)
      4. Normalize whitespace
      5. Truncate to max token-safe length

    Args:
        body: Raw email body string (HTML or plain text).

    Returns:
        Clean, normalized plain text string.
    """
    if not body or not body.strip():
        return ""

    text = body

    # Strip HTML if detected
    if _is_html(text):
        text = _strip_html(text)

    # Decode common HTML entities manually (no external deps)
    text = _decode_entities(text)

    # Normalize whitespace — collapse multiple newlines and spaces
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    # Truncate to ~3000 chars — enough context for classification
    # without burning tokens on footers, legal text, etc.
    if len(text) > 3000:
        text = text[:3000] + "\n\n[... truncated]"

    return text


def _is_html(text: str) -> bool:
    """Detect if a string contains HTML markup."""
    return bool(re.search(r"<[a-zA-Z][^>]*>", text))


def _strip_html(html: str) -> str:
    """Strip HTML tags using the stdlib HTMLParser."""
    stripper = _HTMLStripper()
    try:
        stripper.feed(html)
        return stripper.get_text()
    except Exception:
        # Fallback: regex strip if parser fails on malformed HTML
        return re.sub(r"<[^>]+>", " ", html)


def _decode_entities(text: str) -> str:
    """Decode common HTML entities to their text equivalents."""
    entities = {
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&nbsp;": " ",
        "&zwnj;": "",
        "&copy;": "©",
        "&reg;": "®",
        "&#8203;": "",  # zero-width space
    }
    for entity, replacement in entities.items():
        text = text.replace(entity, replacement)
    # Handle numeric entities like &#123;
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    return text


if __name__ == "__main__":
    # Quick test with a sample HTML email snippet
    sample = """
    <html><body>
    <h1>Hello!</h1>
    <p>Can we meet <strong>tomorrow at 2pm</strong>?</p>
    <p>Let me know if that works &amp; we can set it up.</p>
    <div style="display:none">tracking pixel</div>
    </body></html>
    """
    print(clean_email_body(sample))
