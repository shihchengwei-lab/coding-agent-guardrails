from docs.toc import heading_anchors


def test_ignores_fenced_code_blocks():
    markdown = """# Intro

```python
# not a heading
## also not a heading
```

## Usage
"""

    assert heading_anchors(markdown) == ["intro", "usage"]
