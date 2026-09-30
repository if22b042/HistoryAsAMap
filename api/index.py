import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from frontend.app import app as application
    app = application
except Exception as e:
    import traceback
    print(f"ERROR importing app: {e}")
    print(traceback.format_exc())
    raise