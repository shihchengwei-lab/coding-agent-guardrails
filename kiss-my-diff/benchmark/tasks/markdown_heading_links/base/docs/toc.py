from .slug import slugify


def heading_anchors(markdown):
    anchors = []
    for line in markdown.splitlines():
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            anchors.append(slugify(title))
    return anchors
