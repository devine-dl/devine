from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from enum import Enum
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import pycaption
import requests
from construct import Container
from pycaption import Caption, CaptionList, CaptionNode, WebVTTReader
from pycaption.geometry import Layout
from pymp4.parser import MP4
from subtitle_filter import Subtitles

from devine.core.tracks.track import Track
from devine.core.utilities import get_binary_path, try_ensure_utf8


class Subtitle(Track):
    class Codec(str, Enum):
        SubRip = "SRT"                # https://wikipedia.org/wiki/SubRip
        SubStationAlpha = "SSA"       # https://wikipedia.org/wiki/SubStation_Alpha
        SubStationAlphav4 = "ASS"     # https://wikipedia.org/wiki/SubStation_Alpha#Advanced_SubStation_Alpha=
        TimedTextMarkupLang = "TTML"  # https://wikipedia.org/wiki/Timed_Text_Markup_Language
        WebVTT = "VTT"                # https://wikipedia.org/wiki/WebVTT
        # MPEG-DASH box-encapsulated subtitle formats
        fTTML = "STPP"  # https://www.w3.org/TR/2018/REC-ttml-imsc1.0.1-20180424
        fVTT = "WVTT"   # https://www.w3.org/TR/webvtt1

        @property
        def extension(self) -> str:
            return self.value.lower()

        @staticmethod
        def from_mime(mime: str) -> Subtitle.Codec:
            mime = mime.lower().strip().split(".")[0]
            if mime == "srt":
                return Subtitle.Codec.SubRip
            elif mime == "ssa":
                return Subtitle.Codec.SubStationAlpha
            elif mime == "ass":
                return Subtitle.Codec.SubStationAlphav4
            elif mime == "ttml":
                return Subtitle.Codec.TimedTextMarkupLang
            elif mime == "vtt":
                return Subtitle.Codec.WebVTT
            elif mime == "stpp":
                return Subtitle.Codec.fTTML
            elif mime == "wvtt":
                return Subtitle.Codec.fVTT
            raise ValueError(f"The MIME '{mime}' is not a supported Subtitle Codec")

        @staticmethod
        def from_codecs(codecs: str) -> Subtitle.Codec:
            for codec in codecs.lower().split(","):
                mime = codec.strip().split(".")[0]
                try:
                    return Subtitle.Codec.from_mime(mime)
                except ValueError:
                    pass
            raise ValueError(f"No MIME types matched any supported Subtitle Codecs in '{codecs}'")

        @staticmethod
        def from_netflix_profile(profile: str) -> Subtitle.Codec:
            profile = profile.lower().strip()
            if profile.startswith("webvtt"):
                return Subtitle.Codec.WebVTT
            if profile.startswith("dfxp"):
                return Subtitle.Codec.TimedTextMarkupLang
            raise ValueError(f"The Content Profile '{profile}' is not a supported Subtitle Codec")

    def __init__(self, *args: Any, codec: Subtitle.Codec, cc: bool = False, sdh: bool = False, forced: bool = False,
                 **kwargs: Any):
        """
        Information on Subtitle Types:
            https://bit.ly/2Oe4fLC (3PlayMedia Blog on SUB vs CC vs SDH).
            However, I wouldn't pay much attention to the claims about SDH needing to
            be in the original source language. It's logically not true.

            CC == Closed Captions. Source: Basically every site.
            SDH = Subtitles for the Deaf or Hard-of-Hearing. Source: Basically every site.
            HOH = Exact same as SDH. Is a term used in the UK. Source: https://bit.ly/2PGJatz (ICO UK)

            More in-depth information, examples, and stuff to look for can be found in the Parameter
            explanation list below.

        Parameters:
            cc: Closed Caption.
                - Intended as if you couldn't hear the audio at all.
                - Can have Sound as well as Dialogue, but doesn't have to.
                - Original source would be from an EIA-CC encoded stream. Typically all
                  upper-case characters.
                Indicators of it being CC without knowing original source:
                  - Extracted with CCExtractor, or
                  - >>> (or similar) being used at the start of some or all lines, or
                  - All text is uppercase or at least the majority, or
                  - Subtitles are Scrolling-text style (one line appears, oldest line
                    then disappears).
                Just because you downloaded it as a SRT or VTT or such, doesn't mean it
                 isn't from an EIA-CC stream. And I wouldn't take the streaming services
                 (CC) as gospel either as they tend to get it wrong too.
            sdh: Deaf or Hard-of-Hearing. Also known as HOH in the UK (EU?).
                 - Intended as if you couldn't hear the audio at all.
                 - MUST have Sound as well as Dialogue to be considered SDH.
                 - It has no "syntax" or "format" but is not transmitted using archaic
                   forms like EIA-CC streams, would be intended for transmission via
                   SubRip (SRT), WebVTT (VTT), TTML, etc.
                 If you can see important audio/sound transcriptions and not just dialogue
                  and it doesn't have the indicators of CC, then it's most likely SDH.
                 If it doesn't have important audio/sounds transcriptions it might just be
                  regular subtitling (you wouldn't mark as CC or SDH). This would be the
                  case for most translation subtitles. Like Anime for example.
            forced: Typically used if there's important information at some point in time
                     like watching Dubbed content and an important Sign or Letter is shown
                     or someone talking in a different language.
                    Forced tracks are recommended by the Matroska Spec to be played if
                     the player's current playback audio language matches a subtitle
                     marked as "forced".
                    However, that doesn't mean every player works like this but there is
                     no other way to reliably work with Forced subtitles where multiple
                     forced subtitles may be in the output file. Just know what to expect
                     with "forced" subtitles.
        """
        super().__init__(*args, **kwargs)
        self.codec = codec
        self.cc = bool(cc)
        self.sdh = bool(sdh)
        if self.cc and self.sdh:
            raise ValueError("A text track cannot be both CC and SDH.")
        self.forced = bool(forced)
        if (self.cc or self.sdh) and self.forced:
            raise ValueError("A text track cannot be CC/SDH as well as Forced.")

        # Called after Track has been converted to another format
        self.OnConverted: Optional[Callable[[Subtitle.Codec], None]] = None

    def get_track_name(self) -> Optional[str]:
        """Return the base Track Name."""
        track_name = super().get_track_name() or ""
        flag = self.cc and "CC" or self.sdh and "SDH" or self.forced and "Forced"
        if flag:
            if track_name:
                flag = f" ({flag})"
            track_name += flag
        return track_name or None

    def download(
        self,
        session: requests.Session,
        prepare_drm: partial,
        max_workers: Optional[int] = None,
        progress: Optional[partial] = None
    ):
        super().download(session, prepare_drm, max_workers, progress)
        if not self.path:
            return

        if self.codec == Subtitle.Codec.fTTML:
            self.convert(Subtitle.Codec.TimedTextMarkupLang)
        elif self.codec == Subtitle.Codec.fVTT:
            self.convert(Subtitle.Codec.WebVTT)

    def convert(self, codec: Subtitle.Codec) -> Path:
        """
        Convert this Subtitle to another Format.

        The file path location of the Subtitle data will be kept at the same
        location but the file extension will be changed appropriately.

        Supported formats:
        - SubRip - SubtitleEdit or pycaption.SRTWriter
        - TimedTextMarkupLang - SubtitleEdit or pycaption.DFXPWriter
        - WebVTT - SubtitleEdit or pycaption.WebVTTWriter
        - SubStationAlphav4 - SubtitleEdit
        - fTTML* - custom code using some pycaption functions
        - fVTT* - custom code using some pycaption functions
        *: Can read from format, but cannot convert to format

        Note: It currently prioritizes using SubtitleEdit over PyCaption as
        I have personally noticed more oddities with PyCaption parsing over
        SubtitleEdit. Especially when working with TTML/DFXP where it would
        often have timecodes and stuff mixed in/duplicated.

        Returns the new file path of the Subtitle.
        """
        if not self.path or not self.path.exists():
            raise ValueError("You must download the subtitle track first.")

        if self.codec == codec:
            return self.path

        output_path = self.path.with_suffix(f".{codec.value.lower()}")

        sub_edit_executable = get_binary_path("SubtitleEdit")
        if sub_edit_executable and self.codec not in (Subtitle.Codec.fTTML, Subtitle.Codec.fVTT):
            sub_edit_format = {
                Subtitle.Codec.SubStationAlphav4: "AdvancedSubStationAlpha",
                Subtitle.Codec.TimedTextMarkupLang: "TimedText1.0"
            }.get(codec, codec.name)
            sub_edit_args = [
                sub_edit_executable,
                "/Convert", self.path, sub_edit_format,
                f"/outputfilename:{output_path.name}",
                "/encoding:utf8"
            ]
            if codec == Subtitle.Codec.SubRip:
                sub_edit_args.append("/ConvertColorsToDialog")
            subprocess.run(
                sub_edit_args,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            writer = {
                # pycaption generally only supports these subtitle formats
                Subtitle.Codec.SubRip: pycaption.SRTWriter,
                Subtitle.Codec.TimedTextMarkupLang: pycaption.DFXPWriter,
                Subtitle.Codec.WebVTT: pycaption.WebVTTWriter,
            }.get(codec)
            if writer is None:
                raise NotImplementedError(f"Cannot yet convert {self.codec.name} to {codec.name}.")

            caption_set = self.parse(self.path.read_bytes(), self.codec)
            Subtitle.merge_same_cues(caption_set)
            subtitle_text = writer().write(caption_set)

            output_path.write_text(subtitle_text, encoding="utf8")

        self.path = output_path
        self.codec = codec

        if callable(self.OnConverted):
            self.OnConverted(codec)

        return output_path

    @staticmethod
    def parse(data: bytes, codec: Subtitle.Codec) -> pycaption.CaptionSet:
        if not isinstance(data, bytes):
            raise ValueError(f"Subtitle data must be parsed as bytes data, not {type(data).__name__}")

        try:
            if codec == Subtitle.Codec.SubRip:
                text = try_ensure_utf8(data).decode("utf8")
                caption_set = pycaption.SRTReader().read(text)
            elif codec == Subtitle.Codec.fTTML:
                caption_lists: dict[str, pycaption.CaptionList] = defaultdict(pycaption.CaptionList)
                for segment in (
                    Subtitle.parse(box.data, Subtitle.Codec.TimedTextMarkupLang)
                    for box in MP4.parse_stream(BytesIO(data))
                    if box.type == b"mdat"
                ):
                    for lang in segment.get_languages():
                        caption_lists[lang].extend(segment.get_captions(lang))
                caption_set: pycaption.CaptionSet = pycaption.CaptionSet(caption_lists)
            elif codec == Subtitle.Codec.TimedTextMarkupLang:
                text = try_ensure_utf8(data).decode("utf8")
                text = text.replace("tt:", "")
                # negative size values aren't allowed in TTML/DFXP spec, replace with 0
                text = re.sub(r'"(-\d+(\.\d+)?(px|em|%|c|pt))"', '"0"', text)
                caption_set = pycaption.DFXPReader().read(text)
            elif codec == Subtitle.Codec.fVTT:
                caption_lists: dict[str, pycaption.CaptionList] = defaultdict(pycaption.CaptionList)
                caption_list, language = Subtitle.merge_segmented_wvtt(data)
                caption_lists[language] = caption_list
                caption_set: pycaption.CaptionSet = pycaption.CaptionSet(caption_lists)
            elif codec == Subtitle.Codec.WebVTT:
                text = try_ensure_utf8(data).decode("utf8")
                # Segmented VTT when merged may have the WEBVTT headers part of the next caption
                # if they are not separated far enough from the previous caption, hence the \n\n
                text = text. \
                    replace("WEBVTT", "\n\nWEBVTT"). \
                    replace("\r", ""). \
                    replace("\n\n\n", "\n \n\n"). \
                    replace("\n\n<", "\n<")
                caption_set = pycaption.WebVTTReader().read(text)
            else:
                raise ValueError(f"Unknown Subtitle format \"{codec}\"...")
        except pycaption.exceptions.CaptionReadSyntaxError as e:
            raise SyntaxError(f"A syntax error has occurred when reading the \"{codec}\" subtitle: {e}")
        except pycaption.exceptions.CaptionReadNoCaptions:
            return pycaption.CaptionSet({"en": []})

        # remove empty caption lists or some code breaks, especially if it's the first list
        for language in caption_set.get_languages():
            if not caption_set.get_captions(language):
                # noinspection PyProtectedMember
                del caption_set._captions[language]

        return caption_set

    @staticmethod
    def merge_same_cues(caption_set: pycaption.CaptionSet):
        """Merge captions with the same timecodes and text as one in-place."""
        for lang in caption_set.get_languages():
            captions = caption_set.get_captions(lang)
            last_caption = None
            concurrent_captions = pycaption.CaptionList()
            merged_captions = pycaption.CaptionList()
            for caption in captions:
                if last_caption:
                    if (caption.start, caption.end) == (last_caption.start, last_caption.end):
                        if caption.get_text() != last_caption.get_text():
                            concurrent_captions.append(caption)
                        last_caption = caption
                        continue
                    else:
                        merged_captions.append(pycaption.base.merge(concurrent_captions))
                concurrent_captions = [caption]
                last_caption = caption

            if concurrent_captions:
                merged_captions.append(pycaption.base.merge(concurrent_captions))
            if merged_captions:
                caption_set.set_captions(lang, merged_captions)

    @staticmethod
    def merge_segmented_wvtt(data: bytes, period_start: float = 0.) -> tuple[CaptionList, Optional[str]]:
        """
        Convert Segmented DASH WebVTT cues into a pycaption Caption List.
        Also returns an ISO 639-2 alpha-3 language code if available.

        Code ported originally by xhlove to Python from shaka-player.
        Has since been improved upon by rlaphoenix using pymp4 and
        pycaption functions.
        """
        captions = CaptionList()

        # init:
        saw_wvtt_box = False
        timescale = None
        language = None

        # media:
        # > tfhd
        default_duration = None
        # > tfdt
        saw_tfdt_box = False
        base_time = 0
        # > trun
        saw_trun_box = False
        samples = []

        def flatten_boxes(box: Container) -> Iterable[Container]:
            for child in box:
                if hasattr(child, "children"):
                    yield from flatten_boxes(child.children)
                    del child["children"]
                if hasattr(child, "entries"):
                    yield from flatten_boxes(child.entries)
                    del child["entries"]
                # some boxes (mainly within 'entries') uses format not type
                child["type"] = child.get("type") or child.get("format")
                yield child

        for box in flatten_boxes(MP4.parse_stream(BytesIO(data))):
            # init
            if box.type == b"mdhd":
                timescale = box.timescale
                language = box.language

            if box.type == b"wvtt":
                saw_wvtt_box = True

            # media
            if box.type == b"styp":
                # essentially the start of each segment
                # media var resets
                # > tfhd
                default_duration = None
                # > tfdt
                saw_tfdt_box = False
                base_time = 0
                # > trun
                saw_trun_box = False
                samples = []

            if box.type == b"tfhd":
                if box.flags.default_sample_duration_present:
                    default_duration = box.default_sample_duration

            if box.type == b"tfdt":
                saw_tfdt_box = True
                base_time = box.baseMediaDecodeTime

            if box.type == b"trun":
                saw_trun_box = True
                samples = box.sample_info

            if box.type == b"mdat":
                if not timescale:
                    raise ValueError("Timescale was not found in the Segmented WebVTT.")
                if not saw_wvtt_box:
                    raise ValueError("The WVTT box was not found in the Segmented WebVTT.")
                if not saw_tfdt_box:
                    raise ValueError("The TFDT box was not found in the Segmented WebVTT.")
                if not saw_trun_box:
                    raise ValueError("The TRUN box was not found in the Segmented WebVTT.")

                vttc_boxes = MP4.parse_stream(BytesIO(box.data))
                current_time = base_time + period_start

                for sample, vttc_box in zip(samples, vttc_boxes):
                    duration = sample.sample_duration or default_duration
                    if sample.sample_composition_time_offsets:
                        current_time += sample.sample_composition_time_offsets

                    start_time = current_time
                    end_time = current_time + (duration or 0)
                    current_time = end_time

                    if vttc_box.type == b"vtte":
                        # vtte is a vttc that's empty, skip
                        continue

                    layout: Optional[Layout] = None
                    nodes: list[CaptionNode] = []

                    for cue_box in vttc_box.children:
                        if cue_box.type == b"vsid":
                            # this is a V(?) Source ID box, we don't care
                            continue
                        if cue_box.type == b"sttg":
                            layout = Layout(webvtt_positioning=cue_box.settings)
                        elif cue_box.type == b"payl":
                            nodes.extend([
                                node
                                for line in cue_box.cue_text.split("\n")
                                for node in [
                                    CaptionNode.create_text(WebVTTReader()._decode(line)),
                                    CaptionNode.create_break()
                                ]
                            ])
                            nodes.pop()

                    if nodes:
                        caption = Caption(
                            start=start_time * timescale,  # as microseconds
                            end=end_time * timescale,
                            nodes=nodes,
                            layout_info=layout
                        )
                        p_caption = captions[-1] if captions else None
                        if p_caption and caption.start == p_caption.end and str(caption.nodes) == str(p_caption.nodes):
                            # it's a duplicate, but lets take its end time
                            p_caption.end = caption.end
                            continue
                        captions.append(caption)

        return captions, language

    def strip_hearing_impaired(self) -> None:
        """
        Strip captions for hearing impaired (SDH).
        It uses SubtitleEdit if available, otherwise filter-subs.
        """
        if not self.path or not self.path.exists():
            raise ValueError("You must download the subtitle track first.")

        executable = get_binary_path("SubtitleEdit")
        if executable:
            if self.codec == Subtitle.Codec.SubStationAlphav4:
                output_format = "AdvancedSubStationAlpha"
            elif self.codec == Subtitle.Codec.TimedTextMarkupLang:
                output_format = "TimedText1.0"
            else:
                output_format = self.codec.name
            subprocess.run(
                [
                    executable,
                    "/Convert", self.path, output_format,
                    "/encoding:utf8",
                    "/overwrite",
                    "/RemoveTextForHI"
                ],
                check=True,
                stdout=subprocess.DEVNULL
            )
        else:
            sub = Subtitles(self.path)
            sub.filter(
                rm_fonts=True,
                rm_ast=True,
                rm_music=True,
                rm_effects=True,
                rm_names=True,
                rm_author=True
            )
            sub.save()

    def reverse_rtl(self) -> None:
        """
        Reverse RTL (Right to Left) Start/End on Captions.
        This can be used to fix the positioning of sentence-ending characters.
        """
        if not self.path or not self.path.exists():
            raise ValueError("You must download the subtitle track first.")

        executable = get_binary_path("SubtitleEdit")
        if not executable:
            raise EnvironmentError("SubtitleEdit executable not found...")

        if self.codec == Subtitle.Codec.SubStationAlphav4:
            output_format = "AdvancedSubStationAlpha"
        elif self.codec == Subtitle.Codec.TimedTextMarkupLang:
            output_format = "TimedText1.0"
        else:
            output_format = self.codec.name

        subprocess.run(
            [
                executable,
                "/Convert", self.path, output_format,
                "/ReverseRtlStartEnd",
                "/encoding:utf8",
                "/overwrite"
            ],
            check=True,
            stdout=subprocess.DEVNULL
        )

    def __str__(self) -> str:
        return " | ".join(filter(bool, [
            "SUB",
            f"[{self.codec.value}]",
            str(self.language),
            self.get_track_name()
        ]))


__all__ = ("Subtitle",)
