"""
Tests the REAL threaded scan path (ScanWorker on an actual QThread),
not the synchronous shortcut used in smoketest.py. This is the part
most likely to hide a real concurrency bug (signal not firing, UI
update from wrong thread, race on cache.save()), so it gets its own
dedicated test with a Qt event loop actually pumping.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEventLoop, QTimer

from core.library_cache import LibraryCache
from ui.scan_worker import ScanWorker

CACHE_PATH = os.path.join(os.path.dirname(__file__), "_threadtest_cache.json")
TEST_MUSIC = os.path.join(os.path.dirname(__file__), "test_music")

if os.path.exists(CACHE_PATH):
    os.remove(CACHE_PATH)


def main():
    app = QApplication(sys.argv)

    cache = LibraryCache(CACHE_PATH)
    cache.load()

    worker = ScanWorker(cache, [TEST_MUSIC])

    progress_calls = []
    result = {}

    worker.progress.connect(lambda c, t, f: progress_calls.append((c, t, f)))

    loop = QEventLoop()

    def on_finished(summary):
        result["summary"] = summary
        loop.quit()

    worker.finished_scan.connect(on_finished)

    # Safety timeout in case the thread hangs -- fail loudly rather than
    # the test script hanging forever.
    timeout_fired = {"yes": False}

    def on_timeout():
        timeout_fired["yes"] = True
        loop.quit()

    QTimer.singleShot(15000, on_timeout)

    worker.start()
    loop.exec()

    if timeout_fired["yes"]:
        print("FAIL: scan worker did not finish within 15s (possible thread hang)")
        sys.exit(1)

    print(f"Progress signal fired {len(progress_calls)} times")
    print(f"Final summary: {result.get('summary')}")

    assert len(progress_calls) == 8, f"Expected 8 progress calls, got {len(progress_calls)}"
    assert result["summary"]["added"] == 8, "Expected 8 tracks added on first scan"

    # Reload from disk to confirm the worker thread's cache.save() call
    # actually persisted correctly (this is the real concurrency-
    # sensitive bit: save() running on the worker thread, read back on
    # the main thread).
    reloaded = LibraryCache(CACHE_PATH)
    reloaded.load()
    assert len(reloaded.tracks) == 8, f"Expected 8 tracks in reloaded cache, got {len(reloaded.tracks)}"

    print("\nPASS: threaded scan worker completed correctly, signals fired, cache persisted.")

    worker.wait()
    if os.path.exists(CACHE_PATH):
        os.remove(CACHE_PATH)


if __name__ == "__main__":
    main()
