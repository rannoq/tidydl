# tidydl

Sort a messy Downloads folder into tidy subfolders (Images, Documents, Videos, Archives, Installers...).
One file, no dependencies, Python 3.8+. Works on Windows and Linux.

It can run once, keep watching the folder, or start automatically when you log in.

**Safe by default:** without options it only shows a preview. Nothing moves until you add `--apply` or `--watch`, and `--undo` puts files back.

```
$ python tidydl.py
holiday.jpg  ->  Images/holiday.jpg
invoice.pdf  ->  Documents/invoice.pdf
setup.exe  ->  Installers/setup.exe

3 file(s). Preview only. Add --apply to move them.
```

## Start automatically at login (recommended)

```
python tidydl.py --install
```

That is all. From now on tidydl starts by itself every time you log in, sorts what is already in the folder,
and keeps sorting new downloads a few seconds after they finish. It runs in the background with no window.

- **Windows:** creates a Task Scheduler task called `tidydl` (no admin rights needed).
  Check it with `schtasks /query /tn tidydl`.
- **Linux:** creates a systemd user service `tidydl.service`.

Remove it again with:

```
python tidydl.py --uninstall
```

Keep the script where it is after installing. If you move or delete `tidydl.py`, run `--uninstall` and `--install` again.

## Other usage

```
python tidydl.py                      # preview for ~/Downloads
python tidydl.py --apply              # sort once
python tidydl.py --watch              # keep sorting in this window (Ctrl+C to stop)
python tidydl.py --undo               # put the moved files back
python tidydl.py --older-than 7 --apply   # one-off run, leave the last 7 days alone
python tidydl.py "D:\Some\Folder"     # any other folder
```

| Option | Meaning |
|---|---|
| `--apply` | actually move the files |
| `--watch` | keep running and sort new files |
| `--interval SEC` | how often `--watch` checks (default 5) |
| `--settle SEC` | wait until a file has not changed for this long (default 10) |
| `--older-than DAYS` | only files not modified in the last DAYS days |
| `--install` / `--uninstall` | add or remove autostart at login |
| `--undo` | restore the moves recorded in the log |

## What it does

- Sorts by file extension into: Images, Documents, Spreadsheets, Videos, Audio, Archives, Installers, Code, Other.
- Never overwrites: if `a.png` already exists, the new one becomes `a (1).png`.
- Skips unfinished downloads (`.crdownload`, `.part`, `.tmp`...), hidden files and folders.
- In watch mode it waits until a file stops changing, and skips files another program still has open.
- `.tidydl-log.json` records moves (last 500) so `--undo` can restore them.
- `.tidydl.log` in the folder shows what the background job did.

## Customize

Add or change extensions in the `CATEGORIES` dictionary at the top of `tidydl.py`.

## Tests

```
python -m unittest discover -s tests -v
```

## License

MIT
