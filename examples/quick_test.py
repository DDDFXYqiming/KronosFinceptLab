"""Quick test: can we load model on CPU?"""
import sys, os
sys.path.insert(0, 'src')
sys.path.insert(0, r'external/Kronos')
os.environ.setdefault('KRONOS_REPO_PATH', r'E:\AI_Projects\KronosFinceptLab\external\Kronos')

from model import Kronos
print('Loading...', flush=True)
m = Kronos.from_pretrained(r'E:\AI_Projects\KronosFinceptLab\external\Kronos-small')
print('OK', flush=True)
