"""
Template loader — provides the path to bundled template files.

Template files live in ``src/claudetool/templates/`` and are copied
as-is to the target project by the ``setup`` command.
"""

import os
from pathlib import Path

# Root of the bundled templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"

# Model defaults — resolved from env vars at runtime
DEFAULT_SONNET_MODEL = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "sonnet-4-6")
DEFAULT_OPUS_MODEL = os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL", "opus-4-6")
