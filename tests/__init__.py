"""Test package for the fuel pricing alert service.

Ensures the project root is importable so tests can ``import fuel_alert``
regardless of the directory the test runner is invoked from.
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
