import contextlib
import copy
import io
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import pandas as pd
from ortools.sat.python import cp_model

from create_test_data import create_sample_dataset
from engine.cancellation import GenerationCancelled
from engine.cpsat_solver import TimetableCPSATSolver
from engine.data_loader import load_timetable_data
from engine.exporter import TimetableExporter
from engine.schedule import ScheduleDocument
from engine.scheduler import TimetableScheduler
from engine.validator import PreSolverValidator, IndependentValidator
from tests.helpers import fixture, write_workbook
import run_tool_check


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.data, self.schedule = fixture()
        self.output = io.StringIO()
        self.stdout = contextlib.redirect_stdout(self.output)
        self.stderr = contextlib.redirect_stderr(self.output)
        self.stdout.__enter__()
        self.stderr.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)
        self.addCleanup(self.stderr.__exit__, None, None, None)

    def test_valid_schedule(self):
        self.assertEqual(PreSolverValidator.validate(self.data), [])
        self.assertEqual(IndependentValidator.validate_schedule(self.schedule, self.data), [])

    def test_zero_demand_assignments_are_reported(self):
        self.data.subjects.loc[0, "theory_sessions_per_week"] = 0
        self.assertTrue(any("at least one weekly session" in error for error in PreSolverValidator.validate(self.data)))

    def test_invalid_counts_report_row_without_crashing(self):
        for value in (-1, 1.9, "", "abc", float("inf")):
            with self.subTest(value=value):
                data = copy.deepcopy(self.data)
                data.subjects.loc[0, "theory_sessions_per_week"] = value
                errors = PreSolverValidator.validate(data)
                self.assertTrue(any("Subjects row 2, theory_sessions_per_week" in error for error in errors))

    def test_duplicate_ids_and_assignments(self):
        for attr in ("subjects", "teachers", "classes", "rooms", "assignments"):
            with self.subTest(table=attr):
                data = copy.deepcopy(self.data)
                frame = getattr(data, attr)
                setattr(data, attr, pd.concat([frame, frame.iloc[[0]]], ignore_index=True))
                self.assertTrue(any("duplicate" in error for error in PreSolverValidator.validate(data)))

    def test_unavailability_rejects_bad_references_and_slots(self):
        for teacher, day, period in (("UNKNOWN", "Monday", 1), ("T1", "Mnday", 1), ("T1", "Monday", 7)):
            with self.subTest(teacher=teacher, day=day, period=period):
                data = copy.deepcopy(self.data)
                data.unavailability = pd.DataFrame([dict(teacher_id=teacher, day=day, period=period)])
                self.assertTrue(PreSolverValidator.validate(data))

    def test_multiple_unavailability_rows_for_same_teacher_are_valid(self):
        self.data.unavailability = pd.DataFrame([dict(teacher_id="T1", day="Monday", period=p) for p in (5, 6)])
        self.assertEqual(PreSolverValidator.validate(self.data), [])

    def test_daily_capacity_checked_before_solving(self):
        self.data.teachers.loc[1, "max_periods_day"] = 0
        self.assertTrue(any("daily caps" in error for error in PreSolverValidator.validate(self.data)))

    def test_no_lab_room_and_undersized_room_are_rejected(self):
        for mode in ("no lab", "too small", "wrong category"):
            with self.subTest(mode=mode):
                data = copy.deepcopy(self.data)
                if mode == "no lab":
                    data.rooms["type"] = "classroom"
                    data.subjects["lab_room_category"] = ""
                elif mode == "too small":
                    data.rooms["capacity"] = 1
                else:
                    data.rooms["lab_category"] = "Chemistry"
                self.assertTrue(any("no suitable lab room" in error for error in PreSolverValidator.validate(data)))
                with self.assertRaises(ValueError):
                    TimetableCPSATSolver(data)

    def test_invalid_schedules_are_rejected(self):
        cases = {}
        cases["empty"] = []
        cases["missing theory"] = self.schedule[1:]
        cases["incomplete lab"] = [row for i, row in enumerate(self.schedule) if i != 2]
        for name, changes in {
            "invalid day": {"day": "Sunday"}, "invalid period": {"period": 99},
            "fractional period": {"period": 1.5}, "unknown class": {"class_id": "UNKNOWN"},
            "unknown subject": {"subject_id": "UNKNOWN"}, "unknown teacher": {"teacher_id": "UNKNOWN"},
            "unknown room": {"room_id": "UNKNOWN"}, "wrong teacher": {"teacher_id": "T2"},
            "wrong type": {"type": "other"},
            "malformed type": {"type": []},
        }.items():
            rows = copy.deepcopy(self.schedule)
            rows[0].update(changes)
            cases[name] = rows
        for name, rows in cases.items():
            with self.subTest(name=name):
                self.assertTrue(IndependentValidator.validate_schedule(rows, self.data))

    def test_lab_continuity_break_and_room_validation(self):
        for name in ("separated", "break", "no room", "small room", "different rooms"):
            with self.subTest(name=name):
                rows = copy.deepcopy(self.schedule)
                if name == "separated":
                    rows[2]["period"] = 6
                elif name == "break":
                    rows[1]["period"], rows[2]["period"] = 3, 4
                elif name == "no room":
                    rows[1]["room_id"] = rows[2]["room_id"] = None
                elif name == "small room":
                    rows[1]["room_id"] = rows[2]["room_id"] = "SMALL"
                else:
                    rows[2]["room_id"] = "SMALL"
                self.assertTrue(IndependentValidator.validate_schedule(rows, self.data))

    def test_overlaps_and_teacher_caps(self):
        rows = self.schedule + [copy.deepcopy(self.schedule[0])]
        violations = IndependentValidator.validate_schedule(rows, self.data)
        self.assertTrue(any("Class Overlap" in v for v in violations))
        self.assertTrue(any("Teacher Overlap" in v for v in violations))
        self.data.teachers.loc[1, "max_periods_day"] = 1
        self.data.teachers.loc[1, "max_periods_week"] = 1
        violations = IndependentValidator.validate_schedule(self.schedule, self.data)
        self.assertTrue(any("Daily Cap" in v for v in violations))
        self.assertTrue(any("Weekly Cap" in v for v in violations))

    def test_lab_daily_caps(self):
        self.data.teachers.loc[1, "max_periods_day"] = 10
        self.data.subjects.loc[1, "lab_sessions_per_week"] = 3
        rows = [row for row in self.schedule if row["type"] != "lab" and row["class_id"] != "C1"]
        for sid, start in enumerate((1, 3, 5), 10):
            rows.extend(dict(self.schedule[1], session_id=sid, period=p) for p in (start, start + 1))
        violations = IndependentValidator.validate_schedule(rows, self.data)
        self.assertTrue(any("Daily Lab Cap" in v for v in violations))
        self.assertTrue(any("Subject Lab Cap" in v for v in violations))

    def test_swaps_update_all_projections_and_exports(self):
        document = ScheduleDocument(self.schedule, self.data)
        document.swap("class_id", "C1", ("Monday", 1), ("Tuesday", 1))
        classes, teachers = document.projections()
        self.assertEqual(classes["C1"].at["Monday", "Period 1"], "Free")
        self.assertEqual(teachers["T1"].at["Monday", "Period 1"], "Free")
        self.assertIn("Mathematics", classes["C1"].at["Tuesday", "Period 1"])
        self.assertIn("Mathematics", teachers["T1"].at["Tuesday", "Period 1"])
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "edited.xlsx"
            document.export_excel(target)
            self.assertIn("Mathematics", pd.read_excel(target, sheet_name="Tr_T1", index_col=0).at["Tuesday", "Period 1"])

    def test_teacher_view_can_move_complete_lab(self):
        document = ScheduleDocument(self.schedule, self.data)
        document.swap("teacher_id", "T2", ("Monday", 5), ("Tuesday", 4))
        lab = [row for row in document.master_schedule if row["type"] == "lab"]
        self.assertEqual([(row["day"], row["period"]) for row in lab], [("Tuesday", 4), ("Tuesday", 5)])

    def test_rejected_swaps_leave_original_schedule_unchanged(self):
        self.data.unavailability = pd.DataFrame([dict(teacher_id="T1", day="Tuesday", period=1)])
        document = ScheduleDocument(self.schedule, self.data)
        for first, second in ((("Monday", 1), ("Tuesday", 1)),
                              (("Monday", 1), ("Monday", 4)),
                              (("Monday", 4), ("Tuesday", 3)),
                              (("Monday", 4), ("Tuesday", 6))):
            with self.subTest(first=first, second=second):
                with self.assertRaises(ValueError):
                    document.swap("class_id", "C1", first, second)
                self.assertEqual(document.master_schedule, self.schedule)

    def test_export_names_are_safe_unique_and_do_not_lose_data(self):
        keys = ["A" * 25 + "X", "A" * 25 + "Y", "a" * 25 + "Y", "bad/[]:*?\\name"]
        grids = {key: pd.DataFrame([[index]], columns=["Period 1"], index=["Monday"])
                 for index, key in enumerate(keys)}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "export.xlsx"
            TimetableExporter.export_excel(grids, {}, path)
            with pd.ExcelFile(path) as xls:
                self.assertEqual(len(xls.sheet_names), len(keys))
                self.assertEqual(len({name.casefold() for name in xls.sheet_names}), len(keys))
                self.assertTrue(all(len(name) <= 31 for name in xls.sheet_names))
                self.assertEqual([pd.read_excel(xls, sheet_name=name, index_col=0).iloc[0, 0]
                                  for name in xls.sheet_names], list(range(len(keys))))

    def test_failed_export_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "existing.xlsx"
            path.write_bytes(b"original")
            with patch("engine.exporter.os.replace", side_effect=PermissionError("File is open")):
                with self.assertRaises(PermissionError):
                    TimetableExporter.export_excel({"C1": pd.DataFrame([[1]])}, {}, path)
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(list(Path(temp).iterdir()), [path])

    def test_export_keeps_formula_like_labels_as_text(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "labels.xlsx"
            TimetableExporter.export_excel({"C1": pd.DataFrame([["=SUM(1,2)"]])}, {}, path)
            import openpyxl
            workbook = openpyxl.load_workbook(path)
            try:
                self.assertEqual(workbook["Class_C1"]["B2"].data_type, "s")
                self.assertEqual(workbook["Class_C1"]["B2"].value, "=SUM(1,2)")
            finally:
                workbook.close()

    def test_loader_preserves_text_ids_and_releases_file(self):
        self.data.classes["class_id"] = self.data.classes["class_id"].replace({"C1": "001"})
        self.data.assignments["class_id"] = self.data.assignments["class_id"].replace({"C1": "001"})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.xlsx"
            write_workbook(self.data, path)
            loaded = load_timetable_data(path)
            self.assertIn("001", loaded.classes.class_id.tolist())
            path.unlink()  # Windows refuses this if the loader retains an open handle.

    def test_loader_rejects_unstructured_grid_with_missing_sheet_error(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "grid.xlsx"
            workbook = openpyxl.Workbook()
            workbook.active.title = "class wise"
            workbook.active["A1"] = "BCA 1st Sem Section A"
            workbook.save(path)
            workbook.close()
            with self.assertRaisesRegex(ValueError, "missing required sheet: 'Subjects'"):
                load_timetable_data(path)
            path.unlink()

    def test_structured_input_without_optional_sheets_uses_defaults(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.xlsx"
            write_workbook(self.data, path)
            workbook = openpyxl.load_workbook(path)
            del workbook["Config"]
            del workbook["TeacherUnavailability"]
            workbook.save(path)
            workbook.close()
            loaded = load_timetable_data(path)
            self.assertEqual(loaded.periods_per_day, 8)
            self.assertEqual(loaded.break_after_period, 4)
            self.assertEqual(loaded.working_days, ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
            self.assertTrue(loaded.unavailability.empty)
            self.assertEqual(PreSolverValidator.validate(loaded), [])

    def test_config_overrides_are_validated_without_mutating_input(self):
        scheduler = TimetableScheduler(self.data, {"periods_per_day": 4, "break_after_period": 2, "working_days": "wednesday, Thursday"})
        self.assertEqual(scheduler.data.working_days, ["Wednesday", "Thursday"])
        self.assertEqual(scheduler.data.periods_per_day, 4)
        self.assertEqual(scheduler.data.break_after_period, 2)
        self.assertEqual(self.data.periods_per_day, 6)
        for override in ({"periods_per_day": 0}, {"periods_per_day": 1.5},
                         {"break_after_period": 7}, {"working_days": "Monday, Monday"},
                         {"working_days": "Mnday"}, {"working_days": ""}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                TimetableScheduler(self.data, override)

    def test_real_solver_respects_configuration_rooms_and_counts(self):
        scheduler = TimetableScheduler(self.data, {"periods_per_day": 4, "break_after_period": 2,
                                                   "working_days": "Wednesday, Thursday"})
        rows, _, _ = scheduler.solve(5)
        self.assertEqual(len(rows), 4)
        self.assertEqual(IndependentValidator.validate_schedule(rows, scheduler.data), [])
        self.assertTrue(all(row["day"] in {"Wednesday", "Thursday"} and row["period"] <= 4 for row in rows))
        self.assertTrue(all(row["room_id"] == "L1" for row in rows if row["type"] == "lab"))

    def test_sample_workbook_solves_and_exports(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.xlsx"
            create_sample_dataset(path)
            scheduler = TimetableScheduler(path)
            rows, classes, teachers = scheduler.solve(5)
            self.assertEqual(len(rows), 44)
            self.assertEqual(IndependentValidator.validate_schedule(rows, scheduler.data), [])
            output = Path(temp) / "schedule.xlsx"
            scheduler.export_excel(classes, teachers, output)
            with pd.ExcelFile(output) as xls:
                self.assertEqual(len(xls.sheet_names), 7)

    def test_real_solver_counts_both_lab_periods_in_daily_load(self):
        self.data.teachers.loc[1, "max_periods_day"] = 2
        rows, _, _ = TimetableScheduler(self.data).solve(5)
        self.assertEqual(IndependentValidator.validate_schedule(rows, self.data), [])
        for day in self.data.working_days:
            self.assertLessEqual(sum(row["teacher_id"] == "T2" and row["day"] == day for row in rows), 2)

    def test_real_solver_prefers_high_priority_subject_earlier(self):
        self.data.classes = self.data.classes.iloc[[0]].copy()
        self.data.assignments = self.data.assignments.iloc[:2].copy()
        self.data.subjects.loc[1, "theory_sessions_per_week"] = 1
        self.data.subjects.loc[1, "lab_sessions_per_week"] = 0
        scheduler = TimetableScheduler(self.data, dict(working_days="Monday", periods_per_day=2, break_after_period=0))
        rows, _, _ = scheduler.solve(5)
        self.assertEqual(next(row["period"] for row in rows if row["subject_id"] == "S1"), 1)

    def test_acceptance_cli_success_and_bad_workbook_exit_codes(self):
        script = Path(__file__).resolve().parents[1] / "run_tool_check.py"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.xlsx"
            write_workbook(self.data, path)
            result = subprocess.run([sys.executable, "-X", "utf8", str(script), str(path), "5"],
                                    capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Total schedule entries: 4", result.stdout)
            result = subprocess.run([sys.executable, "-X", "utf8", str(script), str(path.with_name("missing.xlsx"))],
                                    capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Check failed:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_cancellation_before_generation(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(GenerationCancelled):
            TimetableScheduler(self.data).solve(30, cancel_event=event)

    def test_cancellation_interrupts_solver_search(self):
        event = threading.Event()
        entered = threading.Event()
        stopped = threading.Event()
        # Synchronize a blocking search to exercise cancellation without a timing-dependent large model.
        class BlockingSolver:
            parameters = type("Parameters", (), {})()
            def Solve(self, model):
                entered.set()
                if not stopped.wait(3):
                    raise AssertionError("Search was not stopped")
                return cp_model.UNKNOWN
            def StopSearch(self):
                stopped.set()
        def cancel_when_search_starts():
            if entered.wait(3):
                event.set()
        trigger = threading.Thread(target=cancel_when_search_starts)
        trigger.start()
        try:
            with patch("engine.cpsat_solver.cp_model.CpSolver", BlockingSolver):
                with self.assertRaises(GenerationCancelled):
                    TimetableCPSATSolver(self.data).solve(30, event)
        finally:
            stopped.set()
            trigger.join(3)
        self.assertTrue(stopped.is_set())

    def test_timeout_and_infeasibility_have_distinct_messages(self):
        for status, expected in ((cp_model.UNKNOWN, "infeasibility has not been proved"),
                                 (cp_model.INFEASIBLE, "No feasible timetable exists")):
            with self.subTest(status=status):
                solver = cp_model.CpSolver()
                with patch.object(solver, "Solve", return_value=status), patch("engine.cpsat_solver.cp_model.CpSolver", return_value=solver):
                    with self.assertRaisesRegex(RuntimeError, expected):
                        TimetableCPSATSolver(self.data).solve(5)

    def test_acceptance_check_fails_for_post_validation_errors(self):
        with patch.object(run_tool_check, "load_timetable_data", return_value=self.data), \
             patch.object(run_tool_check, "TimetableCPSATSolver") as solver, \
             patch.object(run_tool_check.IndependentValidator, "validate_schedule", return_value=["broken lab"]):
            solver.return_value.solve.return_value = self.schedule
            self.assertEqual(run_tool_check.main("unused.xlsx", 5), 1)


if __name__ == "__main__":
    unittest.main()
