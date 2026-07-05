from docs.toc import heading_anchors


def test_heading_anchors_basic_page():
    markdown = "# Intro\n\n## Setup Guide\n\n### API Reference\n"

    assert heading_anchors(markdown) == ["intro", "setup-guide", "api-reference"]


def test_duplicate_headings_get_suffixes():
    markdown = "# Intro\n\n## Install\n\n## Install\n\n## Install!\n"

    assert heading_anchors(markdown) == ["intro", "install", "install-1", "install-2"]


def test_ignores_headings_inside_fenced_code():
    markdown = "# Intro\n\n```python\n# not a heading\n```\n\n## Usage\n"

    assert heading_anchors(markdown) == ["intro", "usage"]
