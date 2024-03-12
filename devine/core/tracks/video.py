from __future__ import annotations

import logging
import math
import re
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from langcodes import Language

from devine.core.config import config
from devine.core.tracks.subtitle import Subtitle
from devine.core.tracks.track import Track
from devine.core.utilities import FPS, get_binary_path, get_boxes


class Video(Track):
    class Codec(str, Enum):
        AVC = "H.264"
        HEVC = "H.265"
        VC1 = "VC-1"
        VP8 = "VP8"
        VP9 = "VP9"
        AV1 = "AV1"

        @property
        def extension(self) -> str:
            return self.value.lower().replace(".", "").replace("-", "")

        @staticmethod
        def from_mime(mime: str) -> Video.Codec:
            mime = mime.lower().strip().split(".")[0]
            if mime in (
                "avc1", "avc2", "avc3",
                "dva1", "dvav",  # Dolby Vision
            ):
                return Video.Codec.AVC
            if mime in (
                "hev1", "hev2", "hev3", "hvc1", "hvc2", "hvc3",
                "dvh1", "dvhe",  # Dolby Vision
                "lhv1", "lhe1",  # Layered
            ):
                return Video.Codec.HEVC
            if mime == "vc-1":
                return Video.Codec.VC1
            if mime in ("vp08", "vp8"):
                return Video.Codec.VP8
            if mime in ("vp09", "vp9"):
                return Video.Codec.VP9
            if mime == "av01":
                return Video.Codec.AV1
            raise ValueError(f"The MIME '{mime}' is not a supported Video Codec")

        @staticmethod
        def from_codecs(codecs: str) -> Video.Codec:
            for codec in codecs.lower().split(","):
                codec = codec.strip()
                mime = codec.split(".")[0]
                try:
                    return Video.Codec.from_mime(mime)
                except ValueError:
                    pass
            raise ValueError(f"No MIME types matched any supported Video Codecs in '{codecs}'")

        @staticmethod
        def from_netflix_profile(profile: str) -> Video.Codec:
            profile = profile.lower().strip()
            if profile.startswith(("h264", "playready-h264")):
                return Video.Codec.AVC
            if profile.startswith("hevc"):
                return Video.Codec.HEVC
            if profile.startswith("vp9"):
                return Video.Codec.VP9
            if profile.startswith("av1"):
                return Video.Codec.AV1
            raise ValueError(f"The Content Profile '{profile}' is not a supported Video Codec")

    class Range(str, Enum):
        SDR = "SDR"        # No Dynamic Range
        HLG = "HLG"        # https://en.wikipedia.org/wiki/Hybrid_log%E2%80%93gamma
        HDR10 = "HDR10"    # https://en.wikipedia.org/wiki/HDR10
        HDR10P = "HDR10+"  # https://en.wikipedia.org/wiki/HDR10%2B
        DV = "DV"          # https://en.wikipedia.org/wiki/Dolby_Vision

        @staticmethod
        def from_cicp(primaries: int, transfer: int, matrix: int) -> Video.Range:
            """
            ISO/IEC 23001-8 Coding-independent code points to Video Range.

            Sources:
            https://www.itu.int/rec/T-REC-H.Sup19-202104-I
            """
            class Primaries(Enum):
                Unspecified = 0
                BT_709 = 1
                BT_601_625 = 5
                BT_601_525 = 6
                BT_2020_and_2100 = 9
                SMPTE_ST_2113_and_EG_4321 = 12  # P3D65

            class Transfer(Enum):
                Unspecified = 0
                BT_709 = 1
                BT_601 = 6
                BT_2020 = 14
                BT_2100 = 15
                BT_2100_PQ = 16
                BT_2100_HLG = 18

            class Matrix(Enum):
                RGB = 0
                YCbCr_BT_709 = 1
                YCbCr_BT_601_625 = 5
                YCbCr_BT_601_525 = 6
                YCbCr_BT_2020_and_2100 = 9  # YCbCr BT.2100 shares the same CP
                ICtCp_BT_2100 = 14

            if transfer == 5:
                # While not part of any standard, it is typically used as a PAL variant of Transfer.BT_601=6.
                # i.e. where Transfer 6 would be for BT.601-NTSC and Transfer 5 would be for BT.601-PAL.
                # The codebase is currently agnostic to either, so a manual conversion to 6 is done.
                transfer = 6

            primaries = Primaries(primaries)
            transfer = Transfer(transfer)
            matrix = Matrix(matrix)

            # primaries and matrix does not strictly correlate to a range

            if (primaries, transfer, matrix) == (0, 0, 0):
                return Video.Range.SDR
            elif primaries in (Primaries.BT_601_625, Primaries.BT_601_525):
                return Video.Range.SDR
            elif transfer == Transfer.BT_2100_PQ:
                return Video.Range.HDR10
            elif transfer == Transfer.BT_2100_HLG:
                return Video.Range.HLG
            else:
                return Video.Range.SDR

        @staticmethod
        def from_m3u_range_tag(tag: str) -> Video.Range:
            tag = (tag or "").upper().replace('"', '').strip()
            if not tag or tag == "SDR":
                return Video.Range.SDR
            elif tag == "PQ":
                return Video.Range.HDR10  # technically could be any PQ-transfer range
            elif tag == "HLG":
                return Video.Range.HLG
            # for some reason there's no Dolby Vision info tag
            raise ValueError(f"The M3U Range Tag '{tag}' is not a supported Video Range")

    def __init__(self, *args: Any, codec: Video.Codec, range_: Video.Range, bitrate: Union[str, int, float],
                 width: int, height: int, fps: Optional[Union[str, int, float]] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # required
        self.codec = codec
        self.range = range_ or Video.Range.SDR
        self.bitrate = int(math.ceil(float(bitrate))) if bitrate else None
        self.width = int(width)
        self.height = int(height)
        # optional
        self.fps = FPS.parse(str(fps)) if fps else None

    def __str__(self) -> str:
        fps = f"{self.fps:.3f}" if self.fps else "Unknown"
        return " | ".join(filter(bool, [
            "VID",
            f"[{self.codec.value}, {self.range.name}]",
            str(self.language),
            f"{self.width}x{self.height} @ {self.bitrate // 1000 if self.bitrate else '?'} kb/s, {fps} FPS",
            self.edition
        ]))

    def change_color_range(self, range_: int) -> None:
        """Change the Video's Color Range to Limited (0) or Full (1)."""
        if not self.path or not self.path.exists():
            raise ValueError("Cannot repackage a Track that has not been downloaded.")

        executable = get_binary_path("ffmpeg")
        if not executable:
            raise EnvironmentError("FFmpeg executable \"ffmpeg\" was not found but is required for this call.")

        filter_key = {
            Video.Codec.AVC: "h264_metadata",
            Video.Codec.HEVC: "hevc_metadata"
        }[self.codec]

        original_path = self.path
        output_path = original_path.with_stem(f"{original_path.stem}_{['limited', 'full'][range_]}_range")

        subprocess.run([
            executable, "-hide_banner",
            "-loglevel", "panic",
            "-i", original_path,
            "-codec", "copy",
            "-bsf:v", f"{filter_key}=video_full_range_flag={range_}",
            str(output_path)
        ], check=True)

        self.path = output_path
        original_path.unlink()

    def ccextractor(
        self, track_id: Any, out_path: Union[Path, str], language: Language, original: bool = False
    ) -> Optional[Subtitle]:
        """Return a TextTrack object representing CC track extracted by CCExtractor."""
        if not self.path:
            raise ValueError("You must download the track first.")

        executable = get_binary_path("ccextractor", "ccextractorwin", "ccextractorwinfull")
        if not executable:
            raise EnvironmentError("ccextractor executable was not found.")

        # ccextractor often fails in weird ways unless we repack
        self.repackage()

        out_path = Path(out_path)

        try:
            subprocess.run([
                executable,
                "-trim",
                "-nobom",
                "-noru", "-ru1",
                "-o", out_path,
                self.path
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            out_path.unlink(missing_ok=True)
            if not e.returncode == 10:  # No captions found
                raise

        if out_path.exists():
            cc_track = Subtitle(
                id_=track_id,
                url="",  # doesn't need to be downloaded
                codec=Subtitle.Codec.SubRip,
                language=language,
                is_original_lang=original,
                cc=True
            )
            cc_track.path = out_path
            return cc_track

        return None

    def extract_c608(self) -> list[Subtitle]:
        """
        Extract Apple-Style c608 box (CEA-608) subtitle using ccextractor.

        This isn't much more than a wrapper to the track.ccextractor function.
        All this does, is actually check if a c608 box exists and only if so
        does it actually call ccextractor.

        Even though there is a possibility of more than one c608 box, only one
        can actually be extracted. Not only that but it's very possible this
        needs to be done before any decryption as the decryption may destroy
        some of the metadata.

        TODO: Need a test file with more than one c608 box to add support for
              more than one CEA-608 extraction.
        """
        if not self.path:
            raise ValueError("You must download the track first.")
        with self.path.open("rb") as f:
            # assuming 20KB is enough to contain the c608 box.
            # ffprobe will fail, so a c608 box check must be done.
            c608_count = len(list(get_boxes(f.read(20000), b"c608")))
        if c608_count > 0:
            # TODO: Figure out the real language, it might be different
            #       CEA-608 boxes doesnt seem to carry language information :(
            # TODO: Figure out if the CC language is original lang or not.
            #       Will need to figure out above first to do so.
            track_id = f"ccextractor-{self.id}"
            cc_lang = self.language
            cc_track = self.ccextractor(
                track_id=track_id,
                out_path=config.directories.temp / config.filenames.subtitle.format(
                    id=track_id,
                    language=cc_lang
                ),
                language=cc_lang,
                original=False
            )
            if not cc_track:
                return []
            return [cc_track]
        return []

    def remove_eia_cc(self) -> bool:
        """
        Remove EIA-CC data from Bitstream while keeping SEI data.

        This works by removing all NAL Unit's with the Type of 6 from the bistream
        and then re-adding SEI data (effectively a new NAL Unit with just the SEI data).
        Only bitstreams with x264 encoding information is currently supported due to the
        obscurity on the MDAT mp4 box structure. Therefore, we need to use hacky regex.
        """
        if not self.path or not self.path.exists():
            raise ValueError("Cannot clean a Track that has not been downloaded.")

        executable = get_binary_path("ffmpeg")
        if not executable:
            raise EnvironmentError("FFmpeg executable \"ffmpeg\" was not found but is required for this call.")

        log = logging.getLogger("x264-clean")
        log.info("Removing EIA-CC from Video Track with FFMPEG")

        with open(self.path, "rb") as f:
            file = f.read(60000)

        x264 = re.search(br"(.{16})(x264)", file)
        if not x264:
            log.info(" - No x264 encode settings were found, unsupported...")
            return False

        uuid = x264.group(1).hex()
        i = file.index(b"x264")
        encoding_settings = file[i: i + file[i:].index(b"\x00")].replace(b":", br"\\:").replace(b",", br"\,").decode()

        original_path = self.path
        cleaned_path = original_path.with_suffix(f".cleaned{original_path.suffix}")
        subprocess.run([
            executable, "-hide_banner",
            "-loglevel", "panic",
            "-i", original_path,
            "-map_metadata", "-1",
            "-fflags", "bitexact",
            "-bsf:v", f"filter_units=remove_types=6,h264_metadata=sei_user_data={uuid}+{encoding_settings}",
            "-codec", "copy",
            str(cleaned_path)
        ], check=True)

        log.info(" + Removed")

        self.path = cleaned_path
        original_path.unlink()

        return True


__all__ = ("Video",)
