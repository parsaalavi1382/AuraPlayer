"""
On first launch with no folders added yet, every tab will show its
"no music folder selected" empty state -- that's correct, not a bug.
Open Settings (⚙ in the top-right) and add the bundled test_music/
folder (or your own real music folder) to see the views populate.
"""

import sys

from PyQt6.QtWidgets import QApplication

from core.library_store import LibraryStore
from ui.main_window import MainWindow
from ui.theme import build_stylesheet
from utils.paths import get_writable_data_path
from core.constants import CURRENT_VERSION

CACHE_PATH = get_writable_data_path("library_cache.json")

import os
import ctypes

def _apply_global_scaling():
    """
    Dynamically set QT_SCALE_FACTOR based on the primary monitor's resolution
    so that the app appears proportionally the same across all screen sizes.
    
    1080p is the baseline (scale = 1.0) and remains completely unaffected.
    For smaller screens (e.g. 720p), scale down to prevent UI clipping.
    For larger screens (e.g. 1440p, 4K), scale up so UI elements are not tiny.
    """
    if sys.platform == "win32":
        try:
            # Enable Per-Monitor DPI Awareness V2 so Windows reports true physical pixels
            try:
                ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            except Exception:
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(2)
                except Exception:
                    pass

            user32 = ctypes.windll.user32
            screen_h = user32.GetSystemMetrics(1)
            
            # Baseline is 1080p. If the screen is standard 1080p (~1080h),
            # keep scale strictly 1.0 so 1080p displays are 100% unaffected.
            if 1000 <= screen_h <= 1120:
                scale = 1.0
            else:
                dpi = 96
                try:
                    dpi = user32.GetDpiForSystem()
                except Exception:
                    pass
                system_dpi_scale = max(1.0, dpi / 96.0)
                effective_logical_h = screen_h / system_dpi_scale
                
                # If effective logical height is close to 1080p (e.g. 4K at 200% = 1080 logical),
                # Qt's built-in DPI scaling is already handling it perfectly.
                if 800 <= effective_logical_h <= 1120:
                    scale = 1.0
                else:
                    scale = max(0.6, min(2.5, effective_logical_h / 1080.0))
            
            existing_scale = float(os.environ.get("QT_SCALE_FACTOR", "1.0"))
            final_scale = scale * existing_scale
            
            if round(final_scale, 2) != 1.0:
                os.environ["QT_SCALE_FACTOR"] = f"{final_scale:.2f}"
            elif "QT_SCALE_FACTOR" in os.environ:
                del os.environ["QT_SCALE_FACTOR"]
        except Exception as e:
            print(f"Error applying global scaling: {e}")

def main():
    _apply_global_scaling()


    app = QApplication(sys.argv)
    app.setApplicationName("AuraPlayer")
    app.setOrganizationName("Parsa Alavi")
    app.setApplicationDisplayName("AuraPlayer")

    store = LibraryStore(CACHE_PATH)
    # Apply the user's saved theme on startup (not just the hardcoded
    # default) -- store must be constructed first so settings.theme is
    # actually loaded from disk before we style the app.
    app.setStyleSheet(build_stylesheet(store.cache.settings.theme))

    window = MainWindow(store)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
