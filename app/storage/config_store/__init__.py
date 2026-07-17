"""Purpose: Public exports for JSON configuration persistence.
Directory: app/storage/config_store.
Dependencies: loader and validator modules.
Connection: Imported by the platform configuration facade.
"""

from app.storage.config_store.loader import deep_merge, load_directory, load_json_file
from app.storage.config_store.validator import validate_platform_config

__all__ = ["deep_merge", "load_directory", "load_json_file", "validate_platform_config"]

