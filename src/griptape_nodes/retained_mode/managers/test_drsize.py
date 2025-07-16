import os
from pathlib import Path


def _get_directory_size_mb(directory_path: str) -> float:
        """Get total size of directory in MB.

        Args:
            directory_path: Path to the directory

        Returns:
            Total size in MB
        """
        total_size = 0
        path = Path(directory_path)

        if not path.exists():
            return 0.0

        for _, _, files in os.walk(directory_path):
            for f in files:
                fp = os.path.join(directory_path, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
        return total_size / (1024 * 1024) # Convert to MB


if __name__ == "__main__":
    print(_get_directory_size_mb("/Users/kateforsberg/Griptape/griptape-nodes/GriptapeNodes/staticfiles/intermediates"))