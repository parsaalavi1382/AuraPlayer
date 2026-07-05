import os
from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.id3 import ID3

# ==========================================
# 1. Gapless Playback Metadata Extractor
# ==========================================
def get_gapless_metadata(filepath: str) -> tuple[int, int]:
    """
    Extracts encoder delay and padding in milliseconds for MP3, FLAC, and M4A/AAC files.
    Returns:
        (encoder_delay_ms, padding_ms)
    """
    if not filepath or not os.path.exists(filepath):
        return 0, 0
    
    delay_ms = 0
    padding_ms = 0
    sample_rate = 44100  # Default fallback sample rate
    
    ext = os.path.splitext(filepath)[1].lower()
    
    try:
        if ext == ".mp3":
            try:
                mp3 = MP3(filepath)
                if mp3.info:
                    sample_rate = getattr(mp3.info, "sample_rate", 44100) or 44100
                    delay_samples = getattr(mp3.info, "encoder_delay", 0) or 0
                    padding_samples = getattr(mp3.info, "encoder_padding", 0) or 0
                    if delay_samples > 0:
                        delay_ms = int((delay_samples / sample_rate) * 1000)
                    if padding_samples > 0:
                        padding_ms = int((padding_samples / sample_rate) * 1000)
            except Exception:
                pass
            
            if delay_ms == 0 and padding_ms == 0:
                try:
                    id3 = ID3(filepath)
                    for key in id3.keys():
                        if "iTunSMPB" in key:
                            frame = id3[key]
                            text_val = frame.text[0] if getattr(frame, "text", None) else str(frame)
                            tokens = text_val.strip().split()
                            if len(tokens) >= 4:
                                delay_hex = tokens[1]
                                padding_hex = tokens[2]
                                delay_ms = int((int(delay_hex, 16) / sample_rate) * 1000)
                                padding_ms = int((int(padding_hex, 16) / sample_rate) * 1000)
                                break
                except Exception:
                    pass
                    
        elif ext in (".m4a", ".mp4", ".aac"):
            try:
                mp4 = MP4(filepath)
                if mp4.info:
                    sample_rate = getattr(mp4.info, "sample_rate", 44100) or 44100
                smpb_data = mp4.get("----:com.apple.iTunes:iTunSMPB")
                if smpb_data:
                    val = smpb_data[0]
                    if isinstance(val, bytes):
                        val = val.decode("utf-8", errors="replace")
                    tokens = val.strip().split()
                    if len(tokens) >= 4:
                        delay_hex = tokens[1]
                        padding_hex = tokens[2]
                        delay_ms = int((int(delay_hex, 16) / sample_rate) * 1000)
                        padding_ms = int((int(padding_hex, 16) / sample_rate) * 1000)
            except Exception:
                pass
                
        elif ext == ".flac":
            try:
                from mutagen.flac import FLAC
                flac = FLAC(filepath)
                if flac.info:
                    sample_rate = getattr(flac.info, "sample_rate", 44100) or 44100
                
                delay_val = flac.get("encoder delay") or flac.get("ENCODER DELAY") or flac.get("ENCODER_DELAY")
                padding_val = flac.get("encoder padding") or flac.get("ENCODER PADDING") or flac.get("ENCODER_PADDING")
                
                if delay_val:
                    try:
                        delay_ms = int((float(delay_val[0]) / sample_rate) * 1000)
                    except Exception:
                        pass
                if padding_val:
                    try:
                        padding_ms = int((float(padding_val[0]) / sample_rate) * 1000)
                    except Exception:
                        pass
                        
                if delay_ms == 0 and padding_ms == 0:
                    for key, val in flac.items():
                        if "iTunSMPB" in key:
                            val_str = val[0] if isinstance(val, list) else str(val)
                            tokens = val_str.strip().split()
                            if len(tokens) >= 4:
                                delay_hex = tokens[1]
                                padding_hex = tokens[2]
                                delay_ms = int((int(delay_hex, 16) / sample_rate) * 1000)
                                padding_ms = int((int(padding_hex, 16) / sample_rate) * 1000)
                                break
            except Exception:
                pass
                
    except Exception:
        pass
        
    return delay_ms, padding_ms


# ==========================================
# 2. Audio Quality Specs Extractor
# ==========================================
def get_audio_specs(filepath: str) -> dict:
    """
    Extracts precise audio quality metrics for UI representation.
    """
    specs = {
        "codec": "Unknown",
        "bitrate_kbps": 0,
        "sample_rate_hz": 0,
        "bit_depth": None,
        "channels": 2,
        "is_lossless": False,
        "quality_badge": "Standard"
    }
    
    if not filepath or not os.path.exists(filepath):
        return specs

    try:
        audio = MutagenFile(filepath)
        if audio is None or not audio.info:
            return specs

        info = audio.info
        ext = os.path.splitext(filepath)[1].lower()

        specs["sample_rate_hz"] = getattr(info, "sample_rate", 0)
        specs["channels"] = getattr(info, "channels", 2)

        bitrate_bps = getattr(info, "bitrate", 0)
        specs["bitrate_kbps"] = int(bitrate_bps / 1000) if bitrate_bps else 0

        if ext in (".flac", ".wav", ".alac", ".ape"):
            specs["is_lossless"] = True
            specs["bit_depth"] = getattr(info, "bits_per_sample", 16)
            specs["codec"] = ext[1:].upper()
        else:
            specs["is_lossless"] = False
            if ext == ".mp3":
                specs["codec"] = "MP3"
            elif ext in (".m4a", ".mp4", ".aac"):
                specs["codec"] = "AAC"

        specs["quality_badge"] = _determine_quality_badge(specs)

    except Exception:
        pass

    return specs

def _determine_quality_badge(specs: dict) -> str:
    """
    Determines the commercial tier of the audio quality for UI badges.
    """
    if specs["is_lossless"]:
        if (specs["bit_depth"] and specs["bit_depth"] >= 24) or (specs["sample_rate_hz"] > 48000):
            return "Hi-Res"
        return "Lossless"
    else:
        if specs["bitrate_kbps"] >= 320:
            return "High"
        elif specs["bitrate_kbps"] >= 256:
            return "HQ"
        else:
            return "Standard"