from griptape.artifacts import UrlArtifact


class VideoUrlArtifact(UrlArtifact):
    """Artifact that contains a URL to a video."""

    def __init__(self, url: str, name: str = "VideoUrlArtifact"):
        super().__init__(value=url, name=name)
