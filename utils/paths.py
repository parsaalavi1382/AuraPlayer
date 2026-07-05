import os
import sys

def get_resource_path(*relative_parts: str) -> str:
    """
    Get the absolute path to a resource.
    Supports PyInstaller's standalone single-file / single-folder bundling
    by resolving paths relative to sys._MEIPASS when frozen.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller unpacks data files to sys._MEIPASS at runtime
        base_path = sys._MEIPASS
    else:
        # Standard execution: project root is one level above 'utils/' directory
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    return os.path.join(base_path, *relative_parts)
