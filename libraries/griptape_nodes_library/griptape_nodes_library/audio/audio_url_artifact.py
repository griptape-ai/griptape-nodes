from griptape.artifacts.url_artifact import UrlArtifact


class AudioUrlArtifact(UrlArtifact):
    """AudioUrlArtifact is a specialized artifact for handling audio URLs.

    Keeping to maintain backward compatibility for workflows created with this import.
    Prefer to import from griptape directly.
    """
