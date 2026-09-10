import requests
from packaging import version
from PyQt6.QtCore import QThread, pyqtSignal
from dataclasses import dataclass
import typing

@dataclass
class ReleaseInfo:
    version: str
    is_prerelease: bool
    body_markdown: str
    url: str
    assets: list[dict]

class UpdateCheckWorker(QThread):
    finished = pyqtSignal(object, object)  # latest_official, latest_prerelease
    error = pyqtSignal(str)

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self.api_url = "https://api.github.com/repos/parsaalavi1382/AuraPlayer/releases"

    def run(self):
        try:
            headers = {"Accept": "application/vnd.github.v3+json"}
            response = requests.get(self.api_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            releases = response.json()
            if not isinstance(releases, list):
                self.error.emit("Unexpected response format from GitHub API.")
                return

            latest_official = None
            latest_prerelease = None

            try:
                curr_v = version.parse(self.current_version)
            except Exception:
                # If current_version is unparseable for some reason, fallback
                curr_v = version.parse("0.0.0")

            highest_official_v = curr_v
            highest_pre_v = curr_v

            for release in releases:
                tag_name = release.get("tag_name", "").lstrip("vV")
                if not tag_name:
                    continue
                
                try:
                    rel_v = version.parse(tag_name)
                except Exception:
                    continue

                is_pre = release.get("prerelease", False)
                rel_info = ReleaseInfo(
                    version=tag_name,
                    is_prerelease=is_pre,
                    body_markdown=release.get("body", "No changelog provided."),
                    url=release.get("html_url", ""),
                    assets=release.get("assets", [])
                )

                if is_pre:
                    if rel_v > highest_pre_v:
                        highest_pre_v = rel_v
                        latest_prerelease = rel_info
                else:
                    if rel_v > highest_official_v:
                        highest_official_v = rel_v
                        latest_official = rel_info

            self.finished.emit(latest_official, latest_prerelease)

        except requests.RequestException as e:
            self.error.emit(f"Network error: {str(e)}")
        except Exception as e:
            self.error.emit(f"Update check failed: {str(e)}")
