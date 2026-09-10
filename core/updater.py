import os
import sys
import tempfile
import zipfile
import tarfile
import shutil
import requests
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal

def is_portable() -> bool:
    """Check if the current app instance on Windows is portable or installed."""
    if not getattr(sys, 'frozen', False):
        return True # Running from source is considered 'portable' for update purposes
    
    app_dir = os.path.dirname(sys.executable)
    # Inno Setup creates unins000.exe
    if os.path.exists(os.path.join(app_dir, "unins000.exe")):
        return False
    return True

def get_target_state() -> str:
    """Detect which of the four update states applies to this system:
    - 'windows-portable'
    - 'windows-setup'
    - 'mac'
    - 'linux'
    """
    if sys.platform == "win32":
        return "windows-portable" if is_portable() else "windows-setup"
    elif sys.platform == "darwin":
        return "mac"
    elif sys.platform.startswith("linux"):
        return "linux"
    return "windows-portable" if is_portable() else "windows-setup"

def select_asset(assets: list[dict], target_state: str) -> tuple[str, str]:
    """
    Selects (download_url, filename) from release assets matching target_state:
    - 'windows-portable': AuraPlayer_Windows.zip
    - 'windows-setup': AuraPlayer_Setup_*.exe
    - 'mac': AuraPlayer_macOS.zip
    - 'linux': AuraPlayer_Linux.tar.gz
    """
    # 1. Exact / Preferred matches
    for asset in assets:
        name = asset.get("name", "")
        url = asset.get("browser_download_url", "")
        if not url or not name:
            continue
        
        name_lower = name.lower()

        if target_state == "windows-portable":
            # Must be windows zip, NOT mac
            if name_lower.endswith(".zip") and ("windows" in name_lower or "win" in name_lower) and "mac" not in name_lower:
                return url, name

        elif target_state == "windows-setup":
            if name_lower.endswith(".exe") and ("setup" in name_lower or "installer" in name_lower or "auraplayer" in name_lower):
                return url, name

        elif target_state == "mac":
            if ("mac" in name_lower or "darwin" in name_lower) and (name_lower.endswith(".zip") or name_lower.endswith(".dmg")):
                return url, name

        elif target_state == "linux":
            if ("linux" in name_lower or "ubuntu" in name_lower) and (name_lower.endswith(".tar.gz") or name_lower.endswith(".tgz") or name_lower.endswith(".appimage")):
                return url, name

    # 2. Fallback heuristic
    for asset in assets:
        name = asset.get("name", "")
        url = asset.get("browser_download_url", "")
        if not url or not name:
            continue
        name_lower = name.lower()
        if target_state == "windows-portable" and name_lower.endswith(".zip") and "mac" not in name_lower:
            return url, name
        elif target_state == "windows-setup" and name_lower.endswith(".exe"):
            return url, name
        elif target_state == "mac" and "mac" in name_lower:
            return url, name
        elif target_state == "linux" and ("linux" in name_lower or name_lower.endswith(".tar.gz")):
            return url, name

    return "", ""

class UpdateDownloaderWorker(QThread):
    progress = pyqtSignal(int, str) # percentage, message
    finished = pyqtSignal(bool, str) # success, message or path
    error = pyqtSignal(str)

    def __init__(self, assets: list[dict], parent=None):
        super().__init__(parent)
        self.assets = assets
        self.target_state = get_target_state()
        self.download_url, self.filename = select_asset(self.assets, self.target_state)

    @property
    def is_port(self) -> bool:
        return self.target_state == "windows-portable"

    def run(self):
        if not self.download_url:
            self.error.emit(f"Could not find a suitable release asset for '{self.target_state}'.")
            return

        try:
            self.progress.emit(0, f"Downloading {self.filename}...")
            
            temp_dir = tempfile.gettempdir()
            download_path = os.path.join(temp_dir, self.filename)
            
            # Download file with progress
            with requests.get(self.download_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_length = r.headers.get('content-length')
                
                with open(download_path, 'wb') as f:
                    if total_length is None:
                        f.write(r.content)
                        self.progress.emit(100, "Download complete.")
                    else:
                        dl = 0
                        total_length = int(total_length)
                        for data in r.iter_content(chunk_size=8192):
                            dl += len(data)
                            f.write(data)
                            done = int(100 * dl / total_length)
                            self.progress.emit(done, f"Downloading... {done}%")
            
            if self.target_state == "windows-setup":
                # Windows Installer: just return the path to the exe
                self.finished.emit(True, download_path)

            elif self.target_state == "windows-portable":
                self.progress.emit(100, "Extracting update...")
                extract_dir = os.path.join(temp_dir, "AuraPlayer_Update")
                if os.path.exists(extract_dir):
                    shutil.rmtree(extract_dir, ignore_errors=True)
                os.makedirs(extract_dir, exist_ok=True)
                
                with zipfile.ZipFile(download_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # Check if archive contains a top-level directory (e.g. 'AuraPlayer')
                items = [i for i in os.listdir(extract_dir) if not i.startswith('.')]
                if len(items) == 1 and os.path.isdir(os.path.join(extract_dir, items[0])):
                    source_dir = os.path.join(extract_dir, items[0])
                else:
                    source_dir = extract_dir
                
                self.progress.emit(100, "Preparing installation script...")
                
                if getattr(sys, 'frozen', False):
                    target_dir = os.path.dirname(sys.executable)
                    exe_path = sys.executable
                else:
                    target_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    exe_path = os.path.join(target_dir, "dist", "AuraPlayer", "AuraPlayer.exe")
                    if not os.path.exists(exe_path):
                        exe_path = sys.executable
                
                # Create batch script
                bat_path = os.path.join(temp_dir, "update_auraplayer.bat")
                with open(bat_path, "w") as f:
                    f.write("@echo off\n")
                    f.write("timeout /t 2 /nobreak >nul\n") # Wait for app to close
                    # Copy files, overwriting silently (/y), subdirectories (/s), empty directories (/e)
                    f.write(f'xcopy /s /e /y "{source_dir}\\*" "{target_dir}\\"\n')
                    f.write(f'start "" "{exe_path}"\n')
                    f.write('del "%~f0"\n') # Delete script itself
                
                self.finished.emit(True, bat_path)

            elif self.target_state == "mac":
                self.progress.emit(100, "Extracting update...")
                extract_dir = os.path.join(temp_dir, "AuraPlayer_Update_mac")
                if os.path.exists(extract_dir):
                    shutil.rmtree(extract_dir, ignore_errors=True)
                os.makedirs(extract_dir, exist_ok=True)

                with zipfile.ZipFile(download_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)

                # Locate AuraPlayer.app
                source_app = os.path.join(extract_dir, "AuraPlayer.app")
                if not os.path.exists(source_app):
                    for root, dirs, _ in os.walk(extract_dir):
                        for d in dirs:
                            if d.endswith(".app"):
                                source_app = os.path.join(root, d)
                                break

                if getattr(sys, 'frozen', False):
                    p = sys.executable
                    while p and not p.endswith('.app') and os.path.dirname(p) != p:
                        p = os.path.dirname(p)
                    target_app = p if p.endswith('.app') else "/Applications/AuraPlayer.app"
                else:
                    target_app = "/Applications/AuraPlayer.app"

                sh_path = os.path.join(temp_dir, "update_auraplayer.sh")
                with open(sh_path, "w", newline="\n") as f:
                    f.write("#!/bin/bash\n")
                    f.write("sleep 2\n")
                    if os.path.exists(source_app):
                        f.write(f'rm -rf "{target_app}"\n')
                        f.write(f'cp -R "{source_app}" "{target_app}"\n')
                    f.write(f'open "{target_app}"\n')
                    f.write('rm -- "$0"\n')

                os.chmod(sh_path, 0o755)
                self.finished.emit(True, sh_path)

            elif self.target_state == "linux":
                self.progress.emit(100, "Extracting update...")
                extract_dir = os.path.join(temp_dir, "AuraPlayer_Update_linux")
                if os.path.exists(extract_dir):
                    shutil.rmtree(extract_dir, ignore_errors=True)
                os.makedirs(extract_dir, exist_ok=True)

                if download_path.endswith(".tar.gz") or download_path.endswith(".tgz"):
                    with tarfile.open(download_path, "r:gz") as tar_ref:
                        tar_ref.extractall(extract_dir)

                items = [i for i in os.listdir(extract_dir) if not i.startswith('.')]
                if len(items) == 1 and os.path.isdir(os.path.join(extract_dir, items[0])):
                    source_dir = os.path.join(extract_dir, items[0])
                else:
                    source_dir = extract_dir

                if getattr(sys, 'frozen', False):
                    target_dir = os.path.dirname(sys.executable)
                    exe_path = sys.executable
                else:
                    target_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    exe_path = os.path.join(target_dir, "dist", "AuraPlayer", "AuraPlayer")

                sh_path = os.path.join(temp_dir, "update_auraplayer.sh")
                with open(sh_path, "w", newline="\n") as f:
                    f.write("#!/bin/bash\n")
                    f.write("sleep 2\n")
                    f.write(f'cp -rf "{source_dir}/." "{target_dir}/"\n')
                    f.write(f'chmod +x "{exe_path}"\n')
                    f.write(f'"{exe_path}" &\n')
                    f.write('rm -- "$0"\n')

                os.chmod(sh_path, 0o755)
                self.finished.emit(True, sh_path)

        except Exception as e:
            self.error.emit(f"Update failed: {str(e)}")

def apply_update(file_path: str, target_state_or_portable=None):
    """Executes the update (installer, batch script, or shell script) and closes the app."""
    try:
        if isinstance(target_state_or_portable, bool):
            target_state = "windows-portable" if target_state_or_portable else "windows-setup"
        elif isinstance(target_state_or_portable, str) and target_state_or_portable:
            target_state = target_state_or_portable
        else:
            target_state = get_target_state()

        if target_state == "windows-setup":
            if sys.platform == "win32":
                os.startfile(file_path)
            else:
                subprocess.Popen([file_path])
        elif target_state == "windows-portable":
            if sys.platform == "win32":
                subprocess.Popen([file_path], shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.Popen([file_path])
        elif target_state in ("mac", "linux"):
            subprocess.Popen(["/bin/bash", file_path], start_new_session=True)

        from PyQt6.QtWidgets import QApplication
        QApplication.quit()
    except Exception as e:
        print(f"Failed to apply update: {e}")
