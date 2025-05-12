from griptape.artifacts import UrlArtifact


class AudioUrlArtifact(UrlArtifact):
    """Artifact that contains a URL to an audio file."""

    def __init__(self, url: str, name: str = "AudioUrlArtifact"):
        super().__init__(value=url, name=name)
