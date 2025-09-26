"""Registry for managing artifact load providers."""

from pathlib import Path
from typing import ClassVar

from .artifact_load_provider import ArtifactLoadProvider


class ProviderRegistry:
    """Registry for managing artifact load providers."""

    _providers: ClassVar[list[ArtifactLoadProvider]] = []
    _initialized: ClassVar[bool] = False

    @classmethod
    def register_provider(cls, provider: ArtifactLoadProvider) -> None:
        """Register a new provider.

        Args:
            provider: Provider instance to register
        """
        cls._providers.append(provider)

    @classmethod
    def get_all_providers(cls) -> list[ArtifactLoadProvider]:
        """Get all registered providers.

        Returns:
            List of all registered providers
        """
        if not cls._initialized:
            cls._initialize_providers()
        return cls._providers.copy()

    @classmethod
    def get_provider_by_name(cls, provider_name: str) -> ArtifactLoadProvider | None:
        """Get a provider by name.

        Args:
            provider_name: Name of the provider to find

        Returns:
            Provider instance or None if not found
        """
        if not cls._initialized:
            cls._initialize_providers()

        for provider in cls._providers:
            if provider.provider_name == provider_name:
                return provider
        return None

    @classmethod
    def auto_detect_provider(cls, file_path: Path | None = None, url: str | None = None) -> ArtifactLoadProvider | None:
        """Automatically detect the best provider for a file path or URL.

        Args:
            file_path: Path to check (mutually exclusive with url)
            url: URL to check (mutually exclusive with file_path)

        Returns:
            Best matching provider or None if no provider can handle the input
        """
        if not cls._initialized:
            cls._initialize_providers()

        if file_path is None and url is None:
            return None

        if file_path is not None and url is not None:
            msg = "Cannot specify both file_path and url"
            raise ValueError(msg)

        candidates = []

        for provider in cls._providers:
            if file_path is not None:
                if provider.can_handle_file(file_path):
                    priority = provider.get_priority_score(file_path)
                    candidates.append((provider, priority))
            elif url is not None and provider.can_handle_url(url):
                candidates.append((provider, 0))  # URLs don't have priority scoring yet

        if not candidates:
            return None

        # Sort by priority (highest first) and return the best candidate
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    @classmethod
    def get_supported_extensions(cls) -> set[str]:
        """Get all supported file extensions across all providers.

        Returns:
            Set of all supported extensions
        """
        if not cls._initialized:
            cls._initialize_providers()

        extensions = set()
        for provider in cls._providers:
            extensions.update(provider.supported_extensions)
        return extensions

    @classmethod
    def _initialize_providers(cls) -> None:
        """Initialize all providers by importing and registering them."""
        if cls._initialized:
            return

        # Import all provider modules to trigger registration
        try:
            from .image.loader import ImageLoadProvider

            cls.register_provider(ImageLoadProvider())
        except ImportError:
            pass  # Provider not available

        # Other providers (audio, video, text) removed temporarily while focusing on image implementation

        cls._initialized = True
