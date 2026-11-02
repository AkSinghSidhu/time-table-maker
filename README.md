# 📅 Time Table Maker

Desktop timetable generator for university departments, driven by Google OR-Tools
CP-SAT. Upload a structured Excel workbook of subjects, teachers, classes and
lab rooms, and the tool validates feasibility and schedules a conflict-free
timetable (12 hard constraints incl. class/teacher/room no-overlap, 2-period
lab blocks, daily caps, teacher unavailability) with soft optimisation
(lunch balance, fewer same-subject repeats, priority weighting).

## Quick start (first time)

```bash
./setup.sh     # creates ./venv, installs deps, smoke-tests the engine
./run.sh       # launches the GUI (runs setup.sh automatically if venv is missing)
```

Then in the GUI:
1. **Browse** → select an input workbook (see format below), or **Download Template**
   to get a ready-filled sample workbook.
2. Set the **Solver time limit (seconds)** — small toy data is fine in seconds,
   real department-scale workloads (250+ sessions) need ~30-60s+.
3. ⚡ **Generate Timetable** → preview class/teacher grids → 📥 Export Excel / 📄 Export PDF.

Command-line acceptance check for a converted workbook (no GUI needed):

```bash
./venv/bin/python run_tool_check.py "path/to/workbook.xlsx" 120
```

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

Notes:
- Each lab block occupies 2 consecutive periods, on the same day, not
  straddling the lunch break.
- One subject row defines the session counts used for **all** of its
  `TeacherAssignment` rows — if the same subject is taught to different classes
  with different weekly hours, make a separate subject entry per class
  (e.g. `PYTHON-BCA3A`, `PYTHON-BT3`).
- Lab subjects must match a `lab_category` that exists in the `Rooms` sheet.

## Converting an existing hand-made timetable

`convert_to_tool_format.py` converts a real-world weekly-grid workbook
(Final Load + class-wise grids, like a department's production spreadsheet)
into the structured input format above. Its decisions/exclusions are
documented in the `ConversionNotes` sheet it adds to the output.

```bash
./venv/bin/python convert_to_tool_format.py
```

## Project layout

```
main.py                 GUI entry point (PySide6)
gui/                    Qt interface (app, theme, preview with live validation)
engine/                 Loader, pre-solver validator, CP-SAT solver, exporter
create_test_data.py     Generates the sample/template dataset
convert_to_tool_format.py  Real-timetable xlsx → tool format converter
run_tool_check.py       Headless pipeline run (load → validate → solve → verify)
```

## Requirements

- Python 3.9+
- Dependencies per `requirements.txt`: `PySide6`, `pandas`, `openpyxl`, `ortools`
