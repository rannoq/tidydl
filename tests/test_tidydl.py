import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tidydl as t


def make(folder, *names):
    for n in names:
        (folder / n).write_text("x")


class Tests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_category(self):
        self.assertEqual(t.category_for(Path("a.PNG")), "Images")
        self.assertEqual(t.category_for(Path("a.pdf")), "Documents")
        self.assertEqual(t.category_for(Path("a.xyz")), "Other")
        self.assertIsNone(t.category_for(Path("a.crdownload")))
        self.assertIsNone(t.category_for(Path(".hidden.png")))

    def test_preview_moves_nothing(self):
        make(self.dir, "a.png")
        self.assertEqual(t.main([str(self.dir)]), 0)
        self.assertTrue((self.dir / "a.png").exists())

    def test_apply_and_undo(self):
        make(self.dir, "a.png", "b.pdf", "c.zip")
        t.main([str(self.dir), "--apply"])
        self.assertTrue((self.dir / "Images" / "a.png").exists())
        self.assertFalse((self.dir / "a.png").exists())
        t.main([str(self.dir), "--undo"])
        self.assertTrue((self.dir / "a.png").exists())
        self.assertFalse((self.dir / "Images").exists())

    def test_name_collision(self):
        (self.dir / "Images").mkdir()
        make(self.dir / "Images", "a.png")
        make(self.dir, "a.png")
        t.main([str(self.dir), "--apply"])
        self.assertTrue((self.dir / "Images" / "a (1).png").exists())

    def test_older_than(self):
        make(self.dir, "new.png", "old.png")
        old = time.time() - 10 * 86400
        os.utime(self.dir / "old.png", (old, old))
        moves = t.plan_moves(self.dir, older_than_days=7)
        self.assertEqual([m[0].name for m in moves], ["old.png"])

    def test_watch_waits_for_settle(self):
        make(self.dir, "fresh.png", "settled.png")
        old = time.time() - 60
        os.utime(self.dir / "settled.png", (old, old))
        done = t.watch_once(self.dir, settle=10)
        self.assertEqual([Path(d["from"]).name for d in done], ["settled.png"])
        self.assertTrue((self.dir / "fresh.png").exists())

    def test_watch_appends_undo_log(self):
        old = time.time() - 60
        for name in ("a.png", "b.pdf"):
            make(self.dir, name)
            os.utime(self.dir / name, (old, old))
            t.watch_once(self.dir, settle=10)
        t.main([str(self.dir), "--undo"])
        self.assertTrue((self.dir / "a.png").exists())
        self.assertTrue((self.dir / "b.pdf").exists())

    def test_schtasks_command(self):
        args = t.build_schtasks_create(Path("C:/Users/x/Downloads"),
                                       script="C:/tools/tidydl.py",
                                       python="C:/Python/pythonw.exe")
        self.assertEqual(args[:2], ["schtasks", "/create"])
        self.assertIn("onlogon", args)
        self.assertIn("--watch", args[args.index("/tr") + 1])

    def test_systemd_unit(self):
        unit = t.build_systemd_unit(Path("/home/x/Downloads"),
                                    script="/opt/tidydl.py", python="/usr/bin/python3")
        self.assertIn("--watch", unit)
        self.assertIn("WantedBy=default.target", unit)

    def test_skips_folders(self):
        (self.dir / "somefolder").mkdir()
        self.assertEqual(t.plan_moves(self.dir), [])


if __name__ == "__main__":
    unittest.main()
