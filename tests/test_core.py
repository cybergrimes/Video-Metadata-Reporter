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

    def test_kbps_zero_blank_and_tiny_not_zero(self):
        self.assertEqual(core.kbps("0"), "")
        self.assertEqual(core.kbps(300), "1 kb/s")

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


class TestRootAndContext(unittest.TestCase):
    def test_content_type_ignores_folders_above_root(self):
        p = Path("D:/Extras/Movies/Film/a.mkv")
        self.assertEqual(core.content_type(p), "Extras")
        self.assertEqual(core.content_type(p, root=Path("D:/Extras/Movies")), "Main")
        self.assertEqual(core.content_type(Path("D:/Extras/Movies/Film/Scenes/a.mkv"),
                                           root=Path("D:/Extras/Movies")), "Scenes")

    def test_content_type_file_outside_root_falls_back(self):
        self.assertEqual(core.content_type(Path("D:/x/Extras/a.mkv"), root=Path("E:/other")), "Extras")

    def test_parse_extras(self):
        self.assertEqual(core.parse_extras(" Extras, ,Bonus ,"), ["Extras", "Bonus"])
        self.assertEqual(core.parse_extras(""), [])

    def test_context_picks_deepest_root_and_lists_once(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "tv").mkdir()
            for n in ("a.mkv", "b.mkv", "a.en.srt"):
                (root / "tv" / n).write_bytes(b"")
            ctx = core.ScanContext([root, root / "tv"])
            self.assertEqual(ctx.root_for(root / "tv" / "a.mkv"), root / "tv")
            self.assertIsNone(ctx.root_for(Path(d).parent / "elsewhere" / "x.mkv"))
            first = ctx.listing(root / "tv")
            self.assertIs(ctx.listing(root / "tv"), first)
            self.assertEqual(first.subtitles, ["a.en.srt"])
            self.assertEqual(first.video_stems, {"a", "b"})

    def test_missing_folder_listing_is_empty(self):
        self.assertEqual(core.read_listing(Path("Z:/definitely/not/here")).subtitles, [])


class TestSidecarSubs(unittest.TestCase):
    V = Path("D:/m/Movie (2020).mkv")

    def test_language_flags_and_name(self):
        f = core.sidecar_fields(self.V, "Movie (2020).en.forced.srt")
        self.assertEqual(f, ["English", "SRT (external)", "", "Forced", ""])
        f = core.sidecar_fields(self.V, "Movie (2020).French.SDH.default.ass")
        self.assertEqual(f, ["French", "ASS (external)", "SDH", "", "Default"])

    def test_no_language_is_und(self):
        self.assertEqual(core.sidecar_fields(self.V, "Movie (2020).srt")[0], "und")
        self.assertEqual(core.sidecar_fields(self.V, "Movie (2020).Commentary.srt"),
                         ["und", "SRT (external)", "Commentary", "", ""])

    def test_not_a_match(self):
        self.assertIsNone(core.sidecar_fields(self.V, "Movie (2020) Part 2.en.srt"))
        self.assertIsNone(core.sidecar_fields(self.V, "Other.en.srt"))
        self.assertIsNone(core.sidecar_fields(self.V, "Movie (2020).nfo"))
        self.assertIsNone(core.sidecar_fields(self.V, "movie (2020).idx".replace("idx", "txt")))

    def test_case_insensitive_and_sup(self):
        self.assertEqual(core.sidecar_fields(self.V, "MOVIE (2020).EN.SUP")[:2], ["English", "PGS (external)"])

    def test_vobsub_pair_counts_once(self):
        names = ["Movie (2020).idx", "Movie (2020).sub", "Movie (2020).en.srt", "readme.txt"]
        rows = core.sidecar_subs(self.V, names)
        self.assertEqual([r[1] for r in rows], ["SRT (external)", "VobSub (external)"])

    def test_sub_without_idx(self):
        self.assertEqual(core.sidecar_subs(self.V, ["Movie (2020).sub"])[0][1], "SUB (external)")

    def test_record_appends_after_embedded(self):
        tracks = [NS(track_type="General"), NS(track_type="Video"),
                  NS(track_type="Text", language="en", format="PGS")]
        r = core.record_from_tracks(self.V, tracks, sibling_names=["Movie (2020).de.srt"])
        self.assertEqual(r.subs, ["en | PGS", "German | SRT | External"])
        self.assertEqual(r.subs_split[1], ["German", "SRT (external)", "", "", ""])
        self.assertEqual(len(r.subs), len(r.subs_split))

    def test_longer_named_video_owns_its_subs(self):
        names = ["Movie.mkv", "Movie.Trailer.mkv", "Movie.en.srt", "Movie.Trailer.en.srt"]
        main = core.sidecar_subs(Path("D:/m/Movie.mkv"), names)
        trailer = core.sidecar_subs(Path("D:/m/Movie.Trailer.mkv"), names)
        self.assertEqual([r[0] for r in main], ["English"])
        self.assertEqual(main[0][2], "")
        self.assertEqual([r[0] for r in trailer], ["English"])
        self.assertEqual(len(trailer), 1)

    def test_prefix_overlap_without_listing_still_matches(self):
        self.assertIsNotNone(core.sidecar_fields(Path("D:/m/Movie.mkv"), "Movie.Trailer.en.srt"))

    def test_ambiguous_codes_need_lower_case(self):
        v = Path("D:/m/Movie.mkv")
        self.assertEqual(core.sidecar_fields(v, "Movie.it.srt")[0], "Italian")
        self.assertEqual(core.sidecar_fields(v, "Movie.It.srt")[:3], ["und", "SRT (external)", "It"])
        self.assertEqual(core.sidecar_fields(v, "Movie.No.srt")[2], "No")
        self.assertEqual(core.sidecar_fields(v, "Movie.no.srt")[0], "Norwegian")
        self.assertEqual(core.sidecar_fields(v, "Movie.EN.srt")[0], "English")

    def test_no_siblings_unchanged(self):
        r = core.record_from_tracks(self.V, [NS(track_type="General")])
        self.assertEqual((r.subs, r.subs_split), ([], []))


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
        self.assertEqual(r.category, "Extras")
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
        self.assertEqual(vals[-1], 2)      # '# Audio' is last; '# Subs' sits before the Sub columns

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


class TestCleanWritingApp(unittest.TestCase):
    def test_keeps_name_and_version_only(self):
        cases = {
            "mkvmerge v51.0.0 ('I Wish') 64-bit": "mkvmerge 51.0.0",
            "mkvmerge v97.0 ('You Don't Have A Clue') 64-bit": "mkvmerge 97.0",
            "MakeMKV v1.18.3 win(x64-release)": "MakeMKV 1.18.3",
            "MakeMKV v2.0.0 win(x64-release)": "MakeMKV 2.0.0",
            "HandBrake 1.6.1 2023010900": "HandBrake 1.6.1",
            "mkvmerge v60": "mkvmerge 60",
        }
        for raw, want in cases.items():
            self.assertEqual(core.clean_writing_app(raw), want, raw)

    def test_unparseable_left_alone(self):
        self.assertEqual(core.clean_writing_app("Lavf58.76.100"), "Lavf58.76.100")
        self.assertEqual(core.clean_writing_app("  Some Tool  "), "Some Tool")
        self.assertEqual(core.clean_writing_app(None), "")

    # Strings seen in a real 185-file MKV library (MediaInfo 24.12 and 26.10 report them identically).
    REAL = {
        "MakeMKV v1.14.2 win(x64-release)": "MakeMKV 1.14.2",
        "MakeMKV v1.15.0 win(x64-release)": "MakeMKV 1.15.0",
        "MakeMKV v1.18.3 win(x64-release)": "MakeMKV 1.18.3",
        "MakeMKV v2.0.0 win(x64-release)": "MakeMKV 2.0.0",
        "mkvmerge v43.0.0 ('The Quartermaster') 64-bit": "mkvmerge 43.0.0",
        "mkvmerge v51.0.0 ('I Wish') 64-bit": "mkvmerge 51.0.0",
        "mkvmerge v63.0.0 ('Everything') 64-bit": "mkvmerge 63.0.0",
        "mkvmerge v79.0 ('Funeral Pyres') 64-bit": "mkvmerge 79.0",
        "mkvmerge v88.0 ('All I Know') 64-bit": "mkvmerge 88.0",
        "mkvmerge v96.0 ('It's My Life') 64-bit": "mkvmerge 96.0",
        "mkvmerge v97.0 ('You Don't Have A Clue') 64-bit": "mkvmerge 97.0",
        "mkvmerge v99.0 ('Buka') 64-bit": "mkvmerge 99.0",
    }

    # Other common writers, and awkward shapes.
    OTHER = {
        "mkvmerge v8.2.0 ('World of Adventure') 64bit built on Jun 12 2015 11:26:22": "mkvmerge 8.2.0",
        "mkvmerge v81.0-beta1 ('x') 64-bit": "mkvmerge 81.0-beta1",
        "MKVToolNix 20.0.0": "MKVToolNix 20.0.0",
        "HandBrake 1.6.1 2023010900": "HandBrake 1.6.1",
        "HandBrake 0.10.2 2015060900": "HandBrake 0.10.2",
        "Adobe Premiere Pro 2020.0 (Windows)": "Adobe Premiere Pro 2020.0",
        "Adobe Media Encoder 2020 (Windows)": "Adobe Media Encoder 2020",
        "VirtualDub 1.10.4 (build 35491/release)": "VirtualDub 1.10.4",
        "Shutter Encoder 17.1 - FFmpeg": "Shutter Encoder 17.1",
        "MakeMKV v1.17.7 linux(x64-release)": "MakeMKV 1.17.7",
        "mkvmerge  v97.0  ('x')": "mkvmerge 97.0",          # extra spaces
        "Name v1": "Name 1",
        # No separate version token: left as MediaInfo reported it.
        "Lavf58.76.100": "Lavf58.76.100",
        "ffmpeg": "ffmpeg",
        "Apple QuickTime": "Apple QuickTime",
        "v1.2.3": "v1.2.3",
        "1.2.3": "1.2.3",
        "": "",
        "   ": "",
    }

    def test_real_library_strings(self):
        for raw, want in self.REAL.items():
            self.assertEqual(core.clean_writing_app(raw), want, raw)

    def test_other_writers_and_edge_shapes(self):
        for raw, want in self.OTHER.items():
            self.assertEqual(core.clean_writing_app(raw), want, raw)

    def test_idempotent(self):
        for raw in list(self.REAL) + list(self.OTHER):
            once = core.clean_writing_app(raw)
            self.assertEqual(core.clean_writing_app(once), once, raw)

    def test_never_raises_on_odd_input(self):
        import random
        import string
        rng = random.Random(1)
        alphabet = string.ascii_letters + string.digits + " .-_()'/+v\t\u00e9\u4e2d"
        for _ in range(20000):
            raw = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
            once = core.clean_writing_app(raw)
            self.assertIsInstance(once, str)
            self.assertEqual(core.clean_writing_app(once), once, raw)

    def test_ends_up_in_the_report_cell(self):
        from mediareport import excel
        gen = NS(track_type="General", format="Matroska",
                 writing_application="mkvmerge v97.0 ('You Don't Have A Clue') 64-bit")
        rec = core.record_from_tracks(Path("D:/L/a.mkv"), [gen])
        ws = excel.build_workbook([rec], [], excel.ExcelOptions())["Library"]
        hdr = [c.value for c in ws[1]]
        self.assertEqual(ws[2][hdr.index("Writing application")].value, "mkvmerge 97.0")

    def test_missing_writing_application_is_blank(self):
        rec = core.record_from_tracks(Path("D:/L/a.mkv"), [NS(track_type="General", format="Matroska")])
        self.assertEqual(rec.writing_app, "")


class TestResolveMediaInfo(unittest.TestCase):
    """The shipped MediaInfo is required on Windows (no fallback). No real DLL is loaded here."""

    def setUp(self):
        from unittest import mock
        self._mock = mock
        core._choice = None
        self.addCleanup(setattr, core, "_choice", None)

    def resolve(self, vendored, probe, platform="win32", expected="26.10"):
        with self._mock.patch("mediareport.paths.vendored_mediainfo", return_value=vendored),                 self._mock.patch("mediareport.paths.vendored_mediainfo_dir", return_value=Path("v")),                 self._mock.patch.object(core, "_probe_mediainfo", side_effect=probe),                 self._mock.patch.object(core, "_vendored_version", return_value=expected),                 self._mock.patch.object(core.sys, "platform", platform):
            return core.resolve_mediainfo(refresh=True)

    def test_vendored_used_when_it_loads(self):
        c = self.resolve(Path("v/MediaInfo.dll"), lambda lib: ("26.10", ""))
        self.assertEqual((c.library, c.version), (str(Path("v/MediaInfo.dll")), "26.10"))

    def test_load_failure_raises_with_reason(self):
        with self.assertRaises(core.MediaInfoUnavailable) as cm:
            self.resolve(Path("v/MediaInfo.dll"), lambda lib: ("", "bad image"))
        msg = str(cm.exception)
        for part in ("MediaInfo 26.10", "couldn't be loaded", "bad image", str(Path("v/MediaInfo.dll"))):
            self.assertIn(part, msg)

    def test_no_fallback_probe_of_the_bundled_library(self):
        calls = []

        def probe(lib):
            calls.append(lib)
            return "", "bad image"
        with self.assertRaises(core.MediaInfoUnavailable):
            self.resolve(Path("v/MediaInfo.dll"), probe)
        self.assertEqual(calls, [str(Path("v/MediaInfo.dll"))])   # pymediainfo's own copy is never tried

    def test_missing_dll_raises(self):
        with self.assertRaises(core.MediaInfoUnavailable) as cm:
            self.resolve(None, lambda lib: ("24.12", ""))
        self.assertIn("MediaInfo 26.10 isn't available", str(cm.exception))
        self.assertIn("is missing", str(cm.exception))

    def test_missing_dll_and_unknown_version_still_a_clear_error(self):
        with self.assertRaises(core.MediaInfoUnavailable) as cm:
            self.resolve(None, lambda lib: ("", ""), expected="")
        self.assertTrue(str(cm.exception).startswith("MediaInfo isn't available"))

    def test_wrong_version_raises(self):
        with self.assertRaises(core.MediaInfoUnavailable) as cm:
            self.resolve(Path("v/MediaInfo.dll"), lambda lib: ("24.12", ""))
        self.assertIn("Expected MediaInfo 26.10", str(cm.exception))
        self.assertIn("24.12", str(cm.exception))

    def test_unknown_expected_version_accepts_whatever_loads(self):
        c = self.resolve(Path("v/MediaInfo.dll"), lambda lib: ("26.10", ""), expected="")
        self.assertEqual(c.version, "26.10")

    def test_off_windows_uses_pymediainfos_library(self):
        c = self.resolve(None, lambda lib: ("24.12", ""), platform="linux")
        self.assertEqual((c.library, c.version), (None, "24.12"))

    def test_off_windows_load_failure_raises(self):
        with self.assertRaises(core.MediaInfoUnavailable):
            self.resolve(None, lambda lib: ("", "no libmediainfo"), platform="linux")

    def test_result_is_cached_but_failures_are_not(self):
        with self._mock.patch("mediareport.paths.vendored_mediainfo", return_value=Path("v/M.dll")),                 self._mock.patch.object(core, "_vendored_version", return_value="26.10"),                 self._mock.patch.object(core, "_probe_mediainfo", return_value=("26.10", "")) as probe:
            core.resolve_mediainfo(refresh=True)
            core.resolve_mediainfo()
            core.mediainfo_library()
            self.assertEqual(probe.call_count, 1)
        core._choice = None
        with self._mock.patch("mediareport.paths.vendored_mediainfo", return_value=Path("v/M.dll")),                 self._mock.patch.object(core, "_vendored_version", return_value="26.10"),                 self._mock.patch.object(core, "_probe_mediainfo", return_value=("", "boom")) as probe:
            for _ in range(2):
                with self.assertRaises(core.MediaInfoUnavailable):
                    core.resolve_mediainfo()
            self.assertEqual(probe.call_count, 2)

    def test_scan_file_passes_the_library(self):
        core._choice = core.MediaInfoChoice("C:/x/MediaInfo.dll", "26.10")
        with self._mock.patch("pymediainfo.MediaInfo.parse", return_value=NS(tracks=[])) as parse:
            core.scan_file(Path("D:/L/a.mkv"))
        self.assertEqual(parse.call_args.kwargs["library_file"], "C:/x/MediaInfo.dll")

    def test_real_vendored_dll_loads_and_matches_version_file(self):
        """The committed DLL is the version vendor/mediainfo/VERSION says (no mocks, no media files)."""
        c = core.resolve_mediainfo(refresh=True)
        self.assertEqual(c.version, core._vendored_version())
        self.assertTrue(Path(c.library).is_file())


if __name__ == "__main__":
    unittest.main()
