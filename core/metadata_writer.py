"""
Writes updated metadata back to the actual audio files using mutagen.
Supports MP3, FLAC, M4A, and OGG formats.
"""

from __future__ import annotations

import os
import base64
from typing import Optional, List

from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis


def _get_image_mime_and_bytes(image_path: str) -> tuple[str, bytes]:
    """Read image bytes and return the mime type and raw bytes."""
    with open(image_path, "rb") as f:
        data = f.read()
    
    ext = os.path.splitext(image_path.lower())[1]
    mime = "image/png" if ext == ".png" else "image/jpeg"
    return mime, data


def write_track_metadata(
    filepath: str,
    title: str,
    artists: list[str],
    album: str,
    album_artists: list[str],
    genres: list[str],
    year: str,
    disc_number: int,
    track_number: Optional[int],
    cover_image_path: Optional[str] = None
) -> None:
    """
    Write metadata back to the physical audio file.
    """
    ext = os.path.splitext(filepath)[1].lower()
    
    # Read image bytes if a new cover was provided
    img_mime = None
    img_bytes = None
    if cover_image_path and os.path.exists(cover_image_path):
        img_mime, img_bytes = _get_image_mime_and_bytes(cover_image_path)

    if ext == ".mp3":
        # 1. Save general tags using EasyID3 for safety and convenience
        try:
            audio = EasyID3(filepath)
        except Exception:
            # If EasyID3 fails or file has no ID3 tags, create ID3 tags
            try:
                id3 = ID3(filepath)
            except Exception:
                id3 = ID3()
            id3.save(filepath)
            audio = EasyID3(filepath)
            
        audio["title"] = title
        audio["artist"] = artists
        audio["album"] = album
        audio["albumartist"] = album_artists
        audio["date"] = year
        audio["genre"] = genres
        audio["discnumber"] = str(disc_number)
        audio["tracknumber"] = str(track_number) if track_number is not None else ""
        audio.save()

        # 2. Save album art if provided using standard ID3 path
        if img_bytes:
            id3 = ID3(filepath)
            id3.delall("APIC")
            id3.add(APIC(
                encoding=3,  # utf-8
                mime=img_mime,
                type=3,  # front cover
                desc=u"Cover",
                data=img_bytes
            ))
            id3.save()

    elif ext == ".flac":
        audio = FLAC(filepath)
        audio["title"] = title
        audio["artist"] = artists
        audio["album"] = album
        audio["albumartist"] = album_artists
        audio["date"] = year
        audio["genre"] = genres
        audio["discnumber"] = str(disc_number)
        audio["tracknumber"] = str(track_number) if track_number is not None else ""
        
        if img_bytes:
            audio.clear_pictures()
            picture = Picture()
            picture.data = img_bytes
            picture.type = 3
            picture.mime = img_mime
            audio.add_picture(picture)
            
        audio.save()

    elif ext == ".m4a":
        audio = MP4(filepath)
        # MP4 uses atom keys
        audio["\xa9nam"] = [title]
        audio["\xa9ART"] = artists
        audio["\xa9alb"] = [album]
        audio["aART"] = album_artists
        audio["\xa9day"] = [year]
        audio["\xa9gen"] = genres
        audio["disk"] = [(disc_number, 0)]
        audio["trkn"] = [(track_number or 0, 0)]
        
        if img_bytes:
            cover_format = MP4Cover.FORMAT_PNG if img_mime == "image/png" else MP4Cover.FORMAT_JPEG
            audio["covr"] = [MP4Cover(img_bytes, imageformat=cover_format)]
            
        audio.save()

    elif ext == ".ogg":
        audio = OggVorbis(filepath)
        audio["title"] = title
        audio["artist"] = artists
        audio["album"] = album
        audio["albumartist"] = album_artists
        audio["date"] = year
        audio["genre"] = genres
        audio["discnumber"] = str(disc_number)
        audio["tracknumber"] = str(track_number) if track_number is not None else ""
        
        if img_bytes:
            picture = Picture()
            picture.data = img_bytes
            picture.type = 3
            picture.mime = img_mime
            audio["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]
            
        audio.save()
        
    else:
        # Fallback to easy mutagen File interface for unrecognized or basic formats (e.g. WAV if tagged)
        audio = MutagenFile(filepath, easy=True)
        if audio is not None:
            audio["title"] = title
            audio["artist"] = artists
            audio["album"] = album
            audio["albumartist"] = album_artists
            audio["date"] = year
            audio["genre"] = genres
            audio["discnumber"] = str(disc_number)
            audio["tracknumber"] = str(track_number) if track_number is not None else ""
            audio.save()
