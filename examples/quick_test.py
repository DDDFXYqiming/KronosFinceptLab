"""Quick test: can we load model on CPU?"""
import sys, os
from pathlib import Path
sys.path.insert(0, 'src')
sys.path.insert(0, r'external/Kronos')
PROJ = Path(__file__).resolve().parents[1]
os.environ.setdefault('KRONOS_REPO_PATH', str(PROJ / 'external' / 'Kronos'))

from model import Kronos
print('Loading...', flush=True)
m = Kronos.from_pretrained(str(PROJ / 'external' / 'Kronos-small'))
print('OK', flush=True)
