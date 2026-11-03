# 📅 Time Table Maker

Desktop timetable generator for university departments, driven by Google OR-Tools
CP-SAT. Upload a structured Excel workbook of subjects, teachers, classes and
lab rooms, and the tool validates feasibility and schedules a conflict-free
timetable (including class/teacher/lab-room no-overlap, 2-period
lab blocks, daily caps, teacher unavailability) with soft optimisation
(lunch balance, fewer same-subject repeats, priority weighting).

## Quick start (first time)

Windows PowerShell (Python 3.11+):

```powershell
.\setup.ps1    # creates .venv, installs pinned dependencies, runs regression checks
.\run.ps1      # launches the GUI
```

If script execution is disabled, use a one-process policy override:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

Linux/macOS or Git Bash:

```bash
./setup.sh     # creates .venv, installs pinned dependencies, runs regression checks
./run.sh       # launches the GUI (runs setup.sh automatically if .venv is missing)
```

Then in the GUI:
1. **Browse** → select an input workbook (see format below), or **Download Template**
   to get a ready-filled sample workbook.
2. The workbook's days, periods and break settings load into the controls. Edit them
   to override the workbook for this generation. Set the **Solver time limit (seconds)** — small toy data is fine in seconds,
   real department-scale workloads (250+ sessions) need ~30-60s+.
3. ⚡ **Generate Timetable** → preview class/teacher grids → 📥 Export Excel / 📄 Export PDF.
4. To change a schedule, select two cells in one class or teacher view and click
   **Swap / Move Sessions**. Labs move as complete two-period blocks. Swaps between
   occupied sessions require equal lengths; moving a lab to a free slot requires
   two consecutive free periods. Changes that violate constraints are rejected.
   All tabs and exports use the same validated schedule; cell text is read-only.
5. **Cancel Generation** stops a running search. Closing during generation requests
   cancellation and waits for the worker to finish before closing.

Command-line acceptance check for a converted workbook (no GUI needed):

```bash
./.venv/bin/python -X utf8 run_tool_check.py "path/to/workbook.xlsx" 120
```

On Windows use `.\.venv\Scripts\python.exe -X utf8 run_tool_check.py "path\to\workbook.xlsx" 120`.
Input errors, solver failures and post-validation violations return a nonzero exit code.

Headless usage without cloning concerns: all engine logic lives in `engine/`
and can be driven independently of the GUI.

## Input workbook format

Seven sheets (the first five are mandatory):

| Sheet | Columns |
|---|---|
| `Subjects` | subject_id, name, priority, theory_sessions_per_week, lab_sessions_per_week, lab_room_category |
| `Teachers` | teacher_id, name, max_periods_week, max_periods_day |
| `Classes` | class_id, name, strength |
| `TeacherAssignment` | class_id, subject_id, teacher_id |
| `Rooms` | room_id, type (`lab`/`classroom`), lab_category, capacity |
| `TeacherUnavailability` *(optional)* | teacher_id, day, period |
| `Config` *(optional)* | field / value rows: `periods_per_day`, `break_after_period`, `working_days` |

Uploads must use this structured sheet layout. Hand-made class-wise and faculty-wise
grids are not read directly by the app. Use **Download Template** for a supported example.

Notes:
- Each lab block occupies 2 consecutive periods, on the same day, not
  straddling the lunch break.
- One subject row defines the session counts used for **all** of its
  `TeacherAssignment` rows — if the same subject is taught to different classes
  with different weekly hours, make a separate subject entry per class
  (e.g. `PYTHON-BCA3A`, `PYTHON-BT3`).
- Lab subjects must match a `lab_category` that exists in the `Rooms` sheet.
  A blank required category permits any lab. Every assigned lab must have a room
  with capacity at least the class strength. Classroom rows are kept for reference;
  theory classroom allocation is not modeled.
- IDs must be unique in their entity sheets; each class/subject pair has one teacher
  assignment. Store IDs as Excel text to preserve leading zeros. Counts and load caps
  must be nonnegative whole numbers; each assignment needs at least one session.
  Priorities are 1–3 (1 is highest); class strengths and room capacities must be positive.
- `periods_per_day` is 1–24, `break_after_period` is 0–periods_per_day, and working
  days must be unique full weekday names. Unavailability must refer to a known teacher,
  a configured working day and a valid teaching period.
- A class can have at most two lab blocks per day, with at most one block of the same
  subject per day. Both generation and manual changes enforce these limits.

## Converting an existing hand-made timetable

`convert_to_tool_format.py` converts a real-world weekly-grid workbook
(Final Load + class-wise grids, like a department's production spreadsheet)
into the structured input format above. Its decisions/exclusions are
documented in the `ConversionNotes` sheet it adds to the output.

```bash
./.venv/bin/python convert_to_tool_format.py
```

## Project layout

```
main.py                 GUI entry point (PySide6)
gui/                    Qt interface (app, theme, preview with live validation)
engine/                 Loader, pre-solver validator, CP-SAT solver, exporter
create_test_data.py     Generates the sample/template dataset
convert_to_tool_format.py  Real-timetable xlsx → tool format converter
run_tool_check.py       Headless pipeline run (load → validate → solve → verify)
tests/                  Engine, real solver and offscreen Qt regression checks
```

## Requirements

- Python 3.11+ (verified with Python 3.14 on Windows)
- Tested dependency versions are pinned in `requirements.txt`.

Run the checks without opening desktop windows:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```
