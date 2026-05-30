"""Backend package initialization."""
import sys
from pathlib import Path

# Ensure backend and root are in sys.path for imports
backend = Path(__file__).parent
root = backend.parent

if str(backend) not in sys.path:
    sys.path.insert(0, str(backend))
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
