import os
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

MODULE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ghostpad.pyw")

# .pyw is not a recognised source suffix, so load it with an explicit loader and
# register it in sys.modules (required by dataclasses) before executing it.
_loader = SourceFileLoader("ghostpad", MODULE_PATH)
_spec = spec_from_loader("ghostpad", _loader)
ghostpad = module_from_spec(_spec)
sys.modules["ghostpad"] = ghostpad
_loader.exec_module(ghostpad)


class GhostpadFileTests(unittest.TestCase):
    def test_load_document_reads_utf8_text(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as fh:
            fh.write("hello\nworld")
            temp_path = fh.name
        try:
            self.assertEqual(ghostpad.load_document(temp_path), "hello\nworld")
        finally:
            os.unlink(temp_path)

    def test_save_document_writes_utf8_text(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "note.txt")
            ghostpad.save_document(target, "save me")
            with open(target, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "save me")

    def test_load_document_strips_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "bom.txt")
            with open(target, "w", encoding="utf-8-sig") as fh:
                fh.write("bom text")
            self.assertEqual(ghostpad.load_document(target), "bom text")

    def test_save_document_creates_parent_dirs_and_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "nested", "note.txt")
            ghostpad.save_document(target, "first")
            ghostpad.save_document(target, "second")
            self.assertEqual(ghostpad.load_document(target), "second")
            self.assertEqual(os.listdir(os.path.dirname(target)), ["note.txt"])

    def test_clamp_limits_value_to_range(self):
        self.assertEqual(ghostpad.clamp(5, 0, 3), 3)
        self.assertEqual(ghostpad.clamp(-1, 0, 3), 0)
        self.assertEqual(ghostpad.clamp(2, 0, 3), 2)

    def test_get_text_stats_counts_characters_words_and_lines(self):
        stats = ghostpad.get_text_stats("hello\nworld\n")
        self.assertEqual(stats["characters"], 11)
        self.assertEqual(stats["words"], 2)
        self.assertEqual(stats["lines"], 2)

    def test_get_text_stats_handles_empty_document(self):
        stats = ghostpad.get_text_stats("")
        self.assertEqual(stats["characters"], 0)
        self.assertEqual(stats["words"], 0)
        self.assertEqual(stats["lines"], 1)


class SettingsTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "settings.json")
            original = ghostpad.Settings(
                geometry="600x400+10+20", font_size=15, alpha=0.8, wrap=False, topmost=False, last_path="C:/notes/a.txt"
            )
            ghostpad.save_settings(path, original)
            self.assertEqual(ghostpad.load_settings(path), original)

    def test_missing_or_corrupt_file_gives_defaults(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "settings.json")
            self.assertEqual(ghostpad.load_settings(path), ghostpad.Settings())
            for junk in ("{not json", "[1, 2]", '{"font_size": "huge"}'):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(junk)
                self.assertEqual(ghostpad.load_settings(path), ghostpad.Settings(), junk)

    def test_out_of_range_values_are_clamped_and_unknown_keys_ignored(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "settings.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"font_size": 500, "alpha": 0.01, "geometry": "bogus", "extra": 1}')
            settings = ghostpad.load_settings(path)
            self.assertEqual(settings.font_size, ghostpad.FONT_SIZE_RANGE[1])
            self.assertEqual(settings.alpha, ghostpad.ALPHA_RANGE[0])
            self.assertIsNone(settings.geometry)


class GeometryTests(unittest.TestCase):
    def test_parses_tk_geometry_strings(self):
        self.assertEqual(ghostpad.parse_geometry("560x380+120+80"), (560, 380, 120, 80))
        self.assertEqual(ghostpad.parse_geometry("560x380+-1920+-5"), (560, 380, -1920, -5))

    def test_rejects_invalid_geometry(self):
        for bad in (None, "", "560x380", "axb+1+2", "0x380+1+2"):
            self.assertIsNone(ghostpad.parse_geometry(bad), bad)

    def test_resource_path_finds_bundled_icon(self):
        self.assertTrue(ghostpad.resource_path(ghostpad.ICON_FILE).is_file())


class DisplayAffinityTests(unittest.TestCase):
    def test_uses_full_exclusion_on_windows_10_2004_and_later(self):
        self.assertEqual(ghostpad.choose_display_affinity(19041), ghostpad.WDA_EXCLUDEFROMCAPTURE)
        self.assertEqual(ghostpad.choose_display_affinity(26100), ghostpad.WDA_EXCLUDEFROMCAPTURE)

    def test_falls_back_to_black_box_on_older_windows(self):
        self.assertEqual(ghostpad.choose_display_affinity(18363), ghostpad.WDA_MONITOR)


@unittest.skipUnless(sys.platform == "win32", "capture protection is Windows-only")
class CaptureShieldTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk

        self.tk = tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.shield = ghostpad.CaptureShield(ghostpad.choose_display_affinity(sys.getwindowsversion().build))
        self.assertTrue(self.shield.install())

    def tearDown(self):
        self.shield.uninstall()
        self.root.destroy()

    def _top_hwnd(self, widget):
        widget.update_idletasks()
        return ghostpad.user32.GetAncestor(widget.winfo_id(), ghostpad.GA_ROOT)

    def test_protects_window_while_still_hidden(self):
        hwnd = self._top_hwnd(self.root)
        self.assertTrue(self.shield.protect(hwnd))
        self.assertTrue(self.shield.is_protected(hwnd))

    def test_hook_protects_new_windows_automatically(self):
        popup = self.tk.Toplevel(self.root)
        popup.geometry("120x80+50+50")
        popup.update()
        try:
            self.assertTrue(self.shield.is_protected(self._top_hwnd(popup)))
        finally:
            popup.destroy()

    def test_sweep_reports_no_failures(self):
        popup = self.tk.Toplevel(self.root)
        popup.update()
        try:
            self.assertEqual(self.shield.sweep(), [])
        finally:
            popup.destroy()


@unittest.skipUnless(sys.platform == "win32", "the app targets Windows")
class AppSessionTests(unittest.TestCase):
    """Drive the real app against a temporary data folder."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _start(self):
        app = ghostpad.GhostpadApp(data_dir=self.data_dir)
        app.root.update()
        return app

    def _stop(self, app):
        app.quit()

    def test_untitled_note_and_settings_survive_restart(self):
        app = self._start()
        app.text.insert("1.0", "remember the milk")
        app.change_font_size(+3)
        app.change_opacity(-ghostpad.ALPHA_STEP)
        app.root.geometry("500x300+150+160")
        app.root.update()
        self._stop(app)

        app = self._start()
        try:
            self.assertEqual(app.text.get("1.0", "end-1c"), "remember the milk")
            self.assertEqual(app.state.font_size, ghostpad.DEFAULT_FONT_SIZE + 3)
            self.assertAlmostEqual(app.state.alpha, ghostpad.DEFAULT_ALPHA - ghostpad.ALPHA_STEP)
            self.assertTrue(app.root.geometry().endswith("+150+160"))
            self.assertIsNone(app.state.path)
        finally:
            self._stop(app)

    def test_last_opened_file_is_reopened(self):
        note = os.path.join(self.data_dir, "talk.txt")
        ghostpad.save_document(note, "slide 1\nslide 2")
        app = self._start()
        app.open_file(note)
        self._stop(app)

        app = self._start()
        try:
            self.assertEqual(str(app.state.path), note)
            self.assertEqual(app.text.get("1.0", "end-1c"), "slide 1\nslide 2")
        finally:
            self._stop(app)

    def test_find_counts_and_cycles_through_matches(self):
        app = self._start()
        try:
            app.text.insert("1.0", "Alpha beta\nalpha gamma ALPHA")
            app.text.mark_set("insert", "1.0")
            app.open_find()
            app.find_var.set("alpha")
            app.root.update()
            self.assertEqual(len(app._matches), 3)
            self.assertEqual(app.find_count.cget("text"), "1 of 3")
            app.find_step(+1)
            self.assertEqual(app.find_count.cget("text"), "2 of 3")
            app.find_step(+1)
            app.find_step(+1)  # wraps around
            self.assertEqual(app.find_count.cget("text"), "1 of 3")
            app.find_step(-1)  # wraps backwards
            self.assertEqual(app.find_count.cget("text"), "3 of 3")
            app.find_var.set("zzz")
            self.assertEqual(app.find_count.cget("text"), "No results")
            app.close_find()
            self.assertEqual(app.text.tag_ranges("match"), ())
        finally:
            self._stop(app)

    def test_scroll_notes_moves_view(self):
        app = self._start()
        try:
            app.text.insert("1.0", "\n".join(f"line {i}" for i in range(200)))
            app.text.yview_moveto(0)
            app.root.update()
            app.scroll_notes(+1)
            app.root.update()
            self.assertGreater(app.text.yview()[0], 0)
        finally:
            self._stop(app)


if __name__ == "__main__":
    unittest.main()
