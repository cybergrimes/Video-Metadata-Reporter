import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from mediareport import core


class TestHelpers(unittest.TestCase):
    def test_channels(self):
        self.assertEqual(core.channels(NS(channel_s=6, channel_layout="L R C LFE Ls Rs")), "5.1")
        self.assertEqual(core.channels(NS(channel_s=6, channel_layout="L R C Ls Rs Lb")), "5.1")
        self.assertEqual(core.channels(NS(channel_s="6 channels")), "5.1")
        self.assertEqual(core.channels(NS(channel_s=8)), "7.1")
        self.assertEqual(core.channels(NS(channel_s=2, channel_layout="L R")), "2.0")
        self.assertEqual(core.channels(NS(channel_s=1)), "1.0")
        self.assertEqual(core.channels(NS()), "")
        self.assertEqual(core.channels(NS(channel_s="garbage")), "")
        self.assertEqual(core.channels(None), "")

    def test_kbps(self):
        self.assertEqual(core.kbps("640000"), "640 kb/s")
        self.assertEqual(core.kbps(None), "")
        self.assertEqual(core.kbps("abc"), "")
        self.assertEqual(core.kbps(4000000), "4,000 kb/s")

    def test_lang(self):
        self.assertEqual(core.lang(NS(other_language=["English", "en"], language="en")), "English")
        self.assertEqual(core.lang(NS(other_language=None, language="fr")), "fr")
        self.assertEqual(core.lang(NS(language="und")), "und")
        self.assertEqual(core.lang(NS()), "und")

    def test_hdr(self):
        self.assertEqual(core.hdr(NS(hdr_format="Dolby Vision")), "Dolby Vision")
        self.assertEqual(core.hdr(NS(hdr_format="Dolby Vision", hdr_format_compatibility="HDR10")), "Dolby Vision + HDR10")
        self.assertEqual(core.hdr(NS(hdr_format="SMPTE ST 2094 App 4")), "HDR10+")
        self.assertEqual(core.hdr(NS(hdr_format="SMPTE ST 2086", hdr_format_compatibility="HDR10")), "HDR10")
        self.assertEqual(core.hdr(NS(transfer_characteristics="HLG")), "HLG")
        self.assertEqual(core.hdr(NS()), "SDR")

    def test_describe_audio(self):
        t = NS(other_language=["English"], commercial_name="Dolby TrueHD with Dolby Atmos",
               channel_s=8, channel_layout="L R C LFE Ls Rs Lb Rb", bit_rate="4000000",
               title="Main", default="Yes")
        self.assertEqual(core.describe_audio(t),
                         'English | Dolby TrueHD with Dolby Atmos | 7.1 | 4,000 kb/s | "Main" | Default')
        t2 = NS(language="de", format="AC-3", channel_s=6, bit_rate="640000", default="No")
        self.assertEqual(core.describe_audio(t2), "de | AC-3 | 5.1 | 640 kb/s")
        self.assertEqual(core.describe_audio(NS()), "und | ?")

    def test_kbps_thousands_separator(self):
        self.assertEqual(core.kbps("1234567"), "1,235 kb/s")
        self.assertEqual(core.kbps("999000"), "999 kb/s")

    def test_audio_fields(self):
        t = NS(other_language=["English"], commercial_name="DTS-HD MA", channel_s=8,
               channel_layout="L R C LFE Ls Rs Lb Rb", bit_rate="4000000", title="Main", default="Yes")
        self.assertEqual(core.audio_fields(t), ["English", "DTS-HD MA", "7.1", "4,000 kb/s", "Main", "Default"])
        self.assertEqual(len(core.audio_fields(NS())), len(core.AUDIO_FIELDS))
        self.assertEqual(core.audio_fields(NS(language="de", format="AC-3", default="No"))[5], "")

    def test_sub_fields(self):
        t = NS(language="fr", format="UTF-8", title="Forced", forced="Yes", default="No")
        self.assertEqual(core.sub_fields(t), ["fr", "SRT", "Forced", "Forced", ""])
        self.assertEqual(len(core.sub_fields(NS())), len(core.SUB_FIELDS))

    def test_describe_sub(self):
        t = NS(other_language=["English"], format="PGS", title="SDH", forced="Yes", default="Yes")
        self.assertEqual(core.describe_sub(t), 'English | PGS | "SDH" | Forced | Default')
        self.assertEqual(core.describe_sub(NS(language="en", format="UTF-8")), "en | SRT")
        self.assertEqual(core.describe_sub(NS(language="en", format="ASS", default="Yes")), "en | ASS | Default")
        self.assertEqual(core.describe_sub(NS(language="en", format="Weird")), "en | Weird")
        self.assertEqual(core.describe_sub(NS(language="en", format="VobSub", forced="Yes")), "en | VobSub | Forced")


class TestContentType(unittest.TestCase):
    def test_main(self):
        self.assertEqual(core.content_type(Path("D:/Movies/Film/Film.mkv")), "Main")

    def test_extras_case_insensitive_title(self):
        self.assertEqual(core.content_type(Path("D:/Movies/Film/EXTRAS/a.mkv")), "Extras")
        self.assertEqual(core.content_type(Path("D:/Movies/Film/featurettes/a.mkv")), "Featurettes")
        self.assertEqual(core.content_type(Path("D:/Movies/Film/Scenes/a.mkv")), "Scenes")

    def test_nearest_wins(self):
        self.assertEqual(core.content_type(Path("D:/Extras/Film/Scenes/a.mkv")), "Scenes")
        self.assertEqual(core.content_type(Path("D:/Scenes/Film/extras/a.mkv")), "Extras")

    def test_deep_parent(self):
        self.assertEqual(core.content_type(Path("D:/Film/Extras/Disc 1/a.mkv")), "Extras")

    def test_custom_list(self):
        self.assertEqual(core.content_type(Path("D:/Film/Bonus/a.mkv"), ["bonus"]), "Bonus")
        self.assertEqual(core.content_type(Path("D:/Film/Extras/a.mkv"), ["bonus"]), "Main")

    def test_filename_not_considered(self):
        self.assertEqual(core.content_type(Path("D:/Film/Extras.mkv")), "Main")


class TestFindFiles(unittest.TestCase):
    def test_find(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "sub").mkdir()
            for n in ["b.MKV", "a.mp4", "notes.txt", "sub/c.m2ts", "sub/d.srt", "z.Webm"]:
                (root / n).write_bytes(b"")
            res = core.find_files([root])
            self.assertEqual(res, sorted(res))
            self.assertEqual({p.name for p in res}, {"b.MKV", "a.mp4", "c.m2ts", "z.Webm"})

    def test_overlap_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "sub").mkdir()
            (root / "sub" / "a.mkv").write_bytes(b"")
            (root / "b.mkv").write_bytes(b"")
            res = core.find_files([root, root / "sub", root])
            self.assertEqual(len(res), 2)

    def test_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(core.find_files([d]), [])

    def test_should_stop(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "sub").mkdir()
            (root / "a.mkv").write_bytes(b"")
            (root / "sub" / "b.mkv").write_bytes(b"")
            self.assertEqual(core.find_files([root], should_stop=lambda: True), [])
            self.assertEqual(len(core.find_files([root], should_stop=lambda: False)), 2)
            self.assertEqual(len(core.find_files([root], should_stop=None)), 2)


class TestRecord(unittest.TestCase):
    def test_full(self):
        tracks = [
            NS(track_type="General", format="Matroska", duration="7200000", file_size=str(2 * 1024**3), overall_bit_rate="9000000"),
            NS(track_type="Video", format="HEVC", format_profile="Main 10", width=3840, height=2160,
               other_display_aspect_ratio=["16:9"], display_aspect_ratio="1.778", frame_rate="23.976",
               bit_depth=10, hdr_format="Dolby Vision", hdr_format_compatibility="HDR10", bit_rate="50000000"),
            NS(track_type="Audio", language="en", format="AC-3", channel_s=6, bit_rate="640000"),
            NS(track_type="Audio", language="fr", format="AAC", channel_s=2),
            NS(track_type="Text", language="en", format="UTF-8"),
        ]
        r = core.record_from_tracks(Path("D:/Movies/Film/Extras/a.mkv"), tracks)
        self.assertEqual(r.folder, str(Path("D:/Movies/Film/Extras")))
        self.assertEqual(r.file, "a.mkv")
        self.assertEqual(r.type, "Extras")
        self.assertEqual(r.container, "Matroska")
        self.assertEqual(r.size_gb, 2.0)
        self.assertEqual(r.duration_min, 120)
        self.assertEqual(r.video_codec, "HEVC (Main 10)")
        self.assertEqual(r.resolution, "3840x2160")
        self.assertEqual(r.aspect, "16:9")
        self.assertEqual(r.frame_rate, "23.976")
        self.assertEqual(r.bit_depth, 10)
        self.assertEqual(r.hdr, "Dolby Vision + HDR10")
        self.assertEqual(r.video_bitrate, "50,000 kb/s")
        self.assertEqual(r.audio, ["en | AC-3 | 5.1 | 640 kb/s", "fr | AAC | 2.0"])
        self.assertEqual(r.subs, ["en | SRT"])
        vals = r.base_values()
        self.assertEqual(len(vals), len(core.BASE_COLUMNS))
        self.assertEqual(vals[13:15], [2, 1])

    def test_no_video(self):
        tracks = [NS(track_type="General", format="MPEG-4", duration="60000", overall_bit_rate="1000000"),
                  NS(track_type="Audio", language="en", format="AAC", channel_s=2)]
        r = core.record_from_tracks(Path("x/a.mp4"), tracks)
        self.assertEqual(r.video_codec, "")
        self.assertEqual(r.resolution, "")
        self.assertEqual(r.hdr, "")
        self.assertEqual(r.video_bitrate, "1,000 kb/s")  # falls back to overall bitrate
        self.assertIsNone(r.aspect)
        self.assertEqual(len(r.audio), 1)

    def test_no_general(self):
        tracks = [NS(track_type="Video", format="AVC", width=1920, height=1080)]
        r = core.record_from_tracks(Path("x/a.avi"), tracks)
        self.assertIsNone(r.container)
        self.assertIsNone(r.size_gb)
        self.assertIsNone(r.duration_min)
        self.assertEqual(r.resolution, "1920x1080")
        self.assertEqual(r.hdr, "SDR")

    def test_empty_tracks(self):
        r = core.record_from_tracks(Path("x/a.avi"), [])
        self.assertEqual((r.audio, r.subs, r.hdr), ([], [], ""))


if __name__ == "__main__":
    unittest.main()
