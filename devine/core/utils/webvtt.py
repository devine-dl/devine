import re
import sys
import typing
from typing import Optional

from pycaption import Caption, CaptionList, CaptionNode, CaptionReadError, WebVTTReader, WebVTTWriter


class CaptionListExt(CaptionList):
    @typing.no_type_check
    def __init__(self, iterable=None, layout_info=None):
        self.first_segment_mpegts = 0
        super().__init__(iterable, layout_info)


class CaptionExt(Caption):
    @typing.no_type_check
    def __init__(self, start, end, nodes, style=None, layout_info=None, segment_index=0, mpegts=0, cue_time=0.0):
        style = style or {}
        self.segment_index: int = segment_index
        self.mpegts: float = mpegts
        self.cue_time: float = cue_time
        super().__init__(start, end, nodes, style, layout_info)


class WebVTTReaderExt(WebVTTReader):
    # HLS extension support <https://datatracker.ietf.org/doc/html/rfc8216#section-3.5>
    RE_TIMESTAMP_MAP = re.compile(r"X-TIMESTAMP-MAP.*")
    RE_MPEGTS = re.compile(r"MPEGTS:(\d+)")
    RE_LOCAL = re.compile(r"LOCAL:((?:(\d{1,}):)?(\d{2}):(\d{2})\.(\d{3}))")

    def _parse(self, lines: list[str]) -> CaptionList:
        captions = CaptionListExt()
        start = None
        end = None
        nodes: list[CaptionNode] = []
        layout_info = None
        found_timing = False
        segment_index = -1
        mpegts = 0
        cue_time = 0.0

        # The first segment MPEGTS is needed to calculate the rest. It is possible that
        # the first segment contains no cue and is ignored by pycaption, this acts as a fallback.
        captions.first_segment_mpegts = 0

        for i, line in enumerate(lines):
            if "-->" in line:
                found_timing = True
                timing_line = i
                last_start_time = captions[-1].start if captions else 0
                try:
                    start, end, layout_info = self._parse_timing_line(line, last_start_time)
                except CaptionReadError as e:
                    new_msg = f"{e.args[0]} (line {timing_line})"
                    tb = sys.exc_info()[2]
                    raise type(e)(new_msg).with_traceback(tb) from None

            elif "" == line:
                if found_timing and nodes:
                    found_timing = False
                    caption = CaptionExt(
                        start,
                        end,
                        nodes,
                        layout_info=layout_info,
                        segment_index=segment_index,
                        mpegts=mpegts,
                        cue_time=cue_time,
                    )
                    captions.append(caption)
                    nodes = []

            elif "WEBVTT" in line:
                # Merged segmented VTT doesn't have index information, track manually.
                segment_index += 1
                mpegts = 0
                cue_time = 0.0
            elif m := self.RE_TIMESTAMP_MAP.match(line):
                if r := self.RE_MPEGTS.search(m.group()):
                    mpegts = int(r.group(1))

                cue_time = self._parse_local(m.group())

                # Early assignment in case the first segment contains no cue.
                if segment_index == 0:
                    captions.first_segment_mpegts = mpegts

            else:
                if found_timing:
                    if nodes:
                        nodes.append(CaptionNode.create_break())
                    nodes.append(CaptionNode.create_text(self._decode(line)))
                else:
                    # it's a comment or some metadata; ignore it
                    pass

        # Add a last caption if there are remaining nodes
        if nodes:
            caption = CaptionExt(start, end, nodes, layout_info=layout_info, segment_index=segment_index, mpegts=mpegts)
            captions.append(caption)

        return captions

    @staticmethod
    def _parse_local(string: str) -> float:
        """
        Parse WebVTT LOCAL time and convert it to seconds.
        """
        m = WebVTTReaderExt.RE_LOCAL.search(string)
        if not m:
            return 0

        parsed = m.groups()
        if not parsed:
            return 0
        hours = int(parsed[1])
        minutes = int(parsed[2])
        seconds = int(parsed[3])
        milliseconds = int(parsed[4])
        return (milliseconds / 1000) + seconds + (minutes * 60) + (hours * 3600)


def merge_segmented_webvtt(vtt_raw: str, segment_durations: Optional[list[int]] = None, timescale: int = 1) -> str:
    """
    Merge Segmented WebVTT data.

    Parameters:
        vtt_raw: The concatenated WebVTT files to merge. All WebVTT headers must be
            appropriately spaced apart, or it may produce unwanted effects like
            considering headers as captions, timestamp lines, etc.
        segment_durations: A list of each segment's duration. If not provided it will try
            to get it from the X-TIMESTAMP-MAP headers, specifically the MPEGTS number.
        timescale: The number of time units per second.

    This parses the X-TIMESTAMP-MAP data to compute new absolute timestamps, replacing
    the old start and end timestamp values. All X-TIMESTAMP-MAP header information will
    be removed from the output as they are no longer of concern. Consider this function
    the opposite of a WebVTT Segmenter, a WebVTT Joiner of sorts.

    Algorithm borrowed from N_m3u8DL-RE and shaka-player.
    """
    MPEG_TIMESCALE = 90_000

    vtt = WebVTTReaderExt().read(vtt_raw)
    for lang in vtt.get_languages():
        prev_caption = None
        duplicate_index: list[int] = []
        captions = vtt.get_captions(lang)

        if captions[0].segment_index == 0:
            first_segment_mpegts = captions[0].mpegts
        else:
            first_segment_mpegts = segment_durations[0] if segment_durations else captions.first_segment_mpegts

        caption: CaptionExt
        for i, caption in enumerate(captions):
            # DASH WebVTT doesn't have MPEGTS timestamp like HLS. Instead,
            # calculate the timestamp from SegmentTemplate/SegmentList duration.
            likely_dash = first_segment_mpegts == 0 and caption.mpegts == 0
            if likely_dash and segment_durations:
                duration = segment_durations[caption.segment_index]
                caption.mpegts = MPEG_TIMESCALE * (duration / timescale)

            if caption.mpegts == 0:
                continue

            seconds = (caption.mpegts - first_segment_mpegts) / MPEG_TIMESCALE - caption.cue_time
            offset = seconds * 1_000_000  # pycaption use microseconds

            if caption.start < offset:
                caption.start += offset
                caption.end += offset

            # If the difference between current and previous captions is <=1ms
            # and the payload is equal then splice.
            if (
                prev_caption
                and not caption.is_empty()
                and (caption.start - prev_caption.end) <= 1000  # 1ms in microseconds
                and caption.get_text() == prev_caption.get_text()
            ):
                prev_caption.end = caption.end
                duplicate_index.append(i)

            prev_caption = caption

        # Remove duplicate
        captions[:] = [c for c_index, c in enumerate(captions) if c_index not in set(duplicate_index)]

    return WebVTTWriter().write(vtt)
