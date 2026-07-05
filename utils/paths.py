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


def get_writable_data_path(*relative_parts: str) -> str:
    """
    Get a writable directory path for application data (cache, settings).
    When frozen, uses the user's AppData (Windows) or ~/.auraplayer (macOS/Linux)
    to ensure we have write permissions even when installed in Program Files.
    When running as a script, falls back to the project root for developer convenience.
    """
    if getattr(sys, 'frozen', False):
        if sys.platform == 'win32':
            base_path = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'AuraPlayer')
        else:
            base_path = os.path.join(os.path.expanduser('~'), '.auraplayer')
    else:
        # Developer execution: project root
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
    os.makedirs(base_path, exist_ok=True)
    return os.path.join(base_path, *relative_parts)
