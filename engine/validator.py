"""Validate input and independently verify schedules, including manual changes."""

from collections import Counter, defaultdict
from collections.abc import Mapping

from engine.input_utils import integer
from engine.logger import log_step, log_success, log_warning, log_error


class PreSolverValidator:
    @staticmethod
    def validate(data):
        log_step("🔍 Step 2: Running Pre-Solver Feasibility Validation")
        errors = []
        schemas = {
            "Subjects": (data.subjects, ["subject_id", "name", "priority", "theory_sessions_per_week", "lab_sessions_per_week"]),
            "Teachers": (data.teachers, ["teacher_id", "name", "max_periods_week", "max_periods_day"]),
            "Classes": (data.classes, ["class_id", "name", "strength"]),
            "TeacherAssignment": (data.assignments, ["class_id", "subject_id", "teacher_id"]),
            "Rooms": (data.rooms, ["room_id", "type", "capacity"]),
            "TeacherUnavailability": (data.unavailability, ["teacher_id", "day", "period"]),
        }
        for sheet, (df, columns) in schemas.items():
            if sheet != "TeacherUnavailability" and df.empty:
                errors.append(f"Sheet '{sheet}' is empty.")
            for column in columns:
                if column not in df.columns:
                    errors.append(f"Sheet '{sheet}' missing required column '{column}'.")
        if errors:
            return PreSolverValidator._finish(errors)

        numbers = {
            "Subjects": {"priority": (1, 3), "theory_sessions_per_week": (0, None), "lab_sessions_per_week": (0, None)},
            "Teachers": {"max_periods_week": (0, None), "max_periods_day": (0, None)},
            "Classes": {"strength": (1, None)}, "Rooms": {"capacity": (1, None)},
            "TeacherUnavailability": {"period": (1, data.periods_per_day)},
        }
        for sheet, (df, columns) in schemas.items():
            for row_number, (_, row) in enumerate(df.iterrows(), 2):
                for column in columns:
                    label = f"{sheet} row {row_number}, {column}"
                    if column in numbers.get(sheet, {}):
                        try:
                            integer(row[column], label, *numbers[sheet][column])
                        except ValueError as exc:
                            errors.append(str(exc))
                    elif not str(row[column]).strip():
                        errors.append(f"{label} must not be blank.")
            id_columns = [column for column in columns if column.endswith("_id")]
            unique_columns = [id_columns[0]] if sheet in {"Subjects", "Teachers", "Classes", "Rooms"} else []
            if sheet == "TeacherAssignment":
                unique_columns = ["class_id", "subject_id"]
            if unique_columns:
                keys = df[unique_columns].astype(str).apply(lambda col: col.str.strip())
                if keys.duplicated().any():
                    errors.append(f"{sheet} contains duplicate {', '.join(unique_columns)} values.")
        for row_number, (_, row) in enumerate(data.rooms.iterrows(), 2):
            if str(row["type"]).strip().lower() not in {"lab", "classroom"}:
                errors.append(f"Rooms row {row_number}: type must be 'lab' or 'classroom'.")
        if errors:
            return PreSolverValidator._finish(errors)

        subjects = {str(row.subject_id): row for _, row in data.subjects.iterrows()}
        teachers = {str(row.teacher_id): row for _, row in data.teachers.iterrows()}
        classes = {str(row.class_id): row for _, row in data.classes.iterrows()}
        for row_number, (_, row) in enumerate(data.assignments.iterrows(), 2):
            for column, known in (("class_id", classes), ("subject_id", subjects), ("teacher_id", teachers)):
                if str(row[column]) not in known:
                    errors.append(f"TeacherAssignment row {row_number}: unknown {column} '{row[column]}'.")
        unavailable = set()
        for row_number, (_, row) in enumerate(data.unavailability.iterrows(), 2):
            if str(row.teacher_id) not in teachers:
                errors.append(f"TeacherUnavailability row {row_number}: unknown teacher_id '{row.teacher_id}'.")
            if str(row.day) not in data.working_days:
                errors.append(f"TeacherUnavailability row {row_number}: day '{row.day}' is not a working day.")
            unavailable.add((str(row.teacher_id), str(row.day), integer(row.period, "period", 1)))
        if errors:
            return PreSolverValidator._finish(errors)

        class_load = Counter()
        class_labs = Counter()
        teacher_load = Counter()
        for _, row in data.assignments.iterrows():
            c, s, t = str(row.class_id), str(row.subject_id), str(row.teacher_id)
            subject = subjects[s]
            theory = integer(subject.theory_sessions_per_week, "theory")
            labs = integer(subject.lab_sessions_per_week, "labs")
            load = theory + 2 * labs
            if load == 0:
                errors.append(f"Class '{c}', subject '{s}' must request at least one weekly session.")
            class_load[c] += load
            teacher_load[t] += load
            class_labs[c] += labs
            if labs > len(data.working_days):
                errors.append(f"Class '{c}', subject '{s}' needs more lab blocks than working days (one per subject per day).")
            if labs:
                category = str(subject.get("lab_room_category", "")).strip()
                strength = integer(classes[c].strength, "strength", 1)
                candidates = [room for _, room in data.rooms.iterrows()
                              if str(room.type).lower() == "lab"
                              and (not category or str(room.get("lab_category", "")).strip() == category)
                              and integer(room.capacity, "capacity", 1) >= strength]
                if not candidates:
                    errors.append(f"Class '{c}', subject '{s}': no suitable lab room for category '{category or 'any'}' and {strength} students.")
                valid_starts = [(day, period) for day in data.working_days
                                for period in range(1, data.periods_per_day)
                                if period != data.break_after_period
                                and (t, day, period) not in unavailable
                                and (t, day, period + 1) not in unavailable]
                if not valid_starts:
                    errors.append(f"Class '{c}', subject '{s}': no consecutive available periods for a lab.")
        weekly_slots = len(data.working_days) * data.periods_per_day
        for c, load in class_load.items():
            if load > weekly_slots:
                errors.append(f"Class '{c}' demand ({load}) exceeds weekly available periods ({weekly_slots}).")
            if class_labs[c] > 2 * len(data.working_days):
                errors.append(f"Class '{c}' exceeds the limit of two lab blocks per day.")
        for t, load in teacher_load.items():
            teacher = teachers[t]
            weekly_cap = integer(teacher.max_periods_week, "max_periods_week")
            daily_cap = integer(teacher.max_periods_day, "max_periods_day")
            capacity = sum(min(daily_cap, sum((t, day, period) not in unavailable
                                            for period in range(1, data.periods_per_day + 1)))
                           for day in data.working_days)
            if load > weekly_cap:
                errors.append(f"Teacher '{t}' assigned load ({load}) exceeds max_periods_week ({weekly_cap}).")
            if load > capacity:
                errors.append(f"Teacher '{t}' assigned load ({load}) exceeds availability and daily caps ({capacity}).")
        return PreSolverValidator._finish(errors)

    @staticmethod
    def _finish(errors):
        if errors:
            for error in errors:
                log_error(error)
        else:
            log_success("Pre-Solver Validation Passed.")
        return errors


class IndependentValidator:
    @staticmethod
    def validate_schedule(master_schedule, data):
        log_step("🛡️ Step 5: Running Independent Validator against Master Schedule")
        violations = []
        subjects = {str(row.subject_id): row for _, row in data.subjects.iterrows()}
        teachers = {str(row.teacher_id): row for _, row in data.teachers.iterrows()}
        classes = {str(row.class_id): row for _, row in data.classes.iterrows()}
        rooms = {str(row.room_id): row for _, row in data.rooms.iterrows()}
        assignments = {(str(row.class_id), str(row.subject_id), str(row.teacher_id))
                       for _, row in data.assignments.iterrows()}
        unavailable = {(str(row.teacher_id), str(row.day), integer(row.period, "period", 1))
                       for _, row in data.unavailability.iterrows()}
        occupied = {"Class": set(), "Teacher": set(), "Room": set()}
        daily = Counter()
        weekly = Counter()
        actual = Counter()
        labs = defaultdict(list)
        sessions = defaultdict(list)
        if not master_schedule:
            violations.append("Schedule is empty.")

        for index, entry in enumerate(master_schedule or [], 1):
            required = {"class_id", "subject_id", "teacher_id", "day", "period", "type"}
            if not isinstance(entry, Mapping) or not required.issubset(entry):
                violations.append(f"Entry {index}: missing schedule fields.")
                continue
            c, s, t = (str(entry[key]) for key in ("class_id", "subject_id", "teacher_id"))
            r = str(entry.get("room_id") or "")
            day = str(entry["day"])
            kind = entry["type"]
            invalid = False
            for label, key, known in (("class", c, classes), ("subject", s, subjects), ("teacher", t, teachers)):
                if key not in known:
                    violations.append(f"Entry {index}: unknown {label} '{key}'.")
                    invalid = True
            if day not in data.working_days:
                violations.append(f"Entry {index}: invalid working day '{day}'.")
                invalid = True
            try:
                period = integer(entry["period"], f"Entry {index} period", 1, data.periods_per_day)
            except ValueError as exc:
                violations.append(str(exc))
                invalid = True
            if not isinstance(kind, str) or kind not in {"theory", "lab"}:
                violations.append(f"Entry {index}: unknown session type '{kind}'.")
                invalid = True
            if invalid:
                continue
            if (c, s, t) not in assignments:
                violations.append(f"Entry {index}: unassigned class/subject/teacher combination ({c}, {s}, {t}).")
            actual[(c, s, t, kind)] += 1
            if (t, day, period) in unavailable:
                violations.append(f"Unavailability Violation: Teacher {t} at {day}, Period {period}.")
            for label, key in (("Class", c), ("Teacher", t), ("Room", r)):
                if key:
                    slot = (key, day, period)
                    if slot in occupied[label]:
                        violations.append(f"{label} Overlap: {key} at {day}, Period {period}.")
                    occupied[label].add(slot)
            daily[(t, day)] += 1
            weekly[t] += 1
            if r and r not in rooms:
                violations.append(f"Entry {index}: unknown room '{r}'.")
            if r in rooms and integer(rooms[r].capacity, "capacity", 1) < integer(classes[c].strength, "strength", 1):
                violations.append(f"Room Capacity: {r} cannot hold class {c}.")
            if kind == "lab":
                if r not in rooms or str(rooms[r].type).lower() != "lab":
                    violations.append(f"Lab Room: class {c}, subject {s} requires an existing lab room.")
                category = str(subjects[s].get("lab_room_category", "")).strip()
                if r in rooms and category and str(rooms[r].get("lab_category", "")).strip() != category:
                    violations.append(f"Category Mismatch: room {r} does not match '{category}' for {s}.")
                labs[(c, s, t, r, day)].append(period)
            if "session_id" in entry:
                sessions[str(entry["session_id"])].append((c, s, t, r, day, period, kind))

        expected = Counter()
        for _, row in data.assignments.iterrows():
            c, s, t = str(row.class_id), str(row.subject_id), str(row.teacher_id)
            expected[(c, s, t, "theory")] += integer(subjects[s].theory_sessions_per_week, "theory")
            expected[(c, s, t, "lab")] += 2 * integer(subjects[s].lab_sessions_per_week, "labs")
        for key in expected.keys() | actual.keys():
            if actual[key] != expected[key]:
                violations.append(f"Session Count: {key} requires {expected[key]} periods, found {actual[key]}.")
        for (t, day), count in daily.items():
            if count > integer(teachers[t].max_periods_day, "max_periods_day"):
                violations.append(f"Daily Cap Exceeded: teacher {t} on {day}.")
        for t, count in weekly.items():
            if count > integer(teachers[t].max_periods_week, "max_periods_week"):
                violations.append(f"Weekly Cap Exceeded: teacher {t}.")

        class_lab_blocks = Counter()
        subject_lab_blocks = Counter()
        for (c, s, t, r, day), periods in labs.items():
            periods.sort()
            for offset in range(0, len(periods), 2):
                pair = periods[offset:offset + 2]
                if len(pair) != 2 or pair[1] != pair[0] + 1:
                    violations.append(f"Lab Continuity: {c}, {s} on {day} must occupy two consecutive periods.")
                elif pair[0] == data.break_after_period:
                    violations.append(f"Lab Break: {c}, {s} on {day} crosses lunch.")
                class_lab_blocks[(c, day)] += 1
                subject_lab_blocks[(c, s, day)] += 1
        for (c, day), count in class_lab_blocks.items():
            if count > 2:
                violations.append(f"Daily Lab Cap: class {c} has {count} lab blocks on {day} (maximum 2).")
        for (c, s, day), count in subject_lab_blocks.items():
            if count > 1:
                violations.append(f"Subject Lab Cap: class {c}, subject {s} has multiple labs on {day}.")
        for sid, entries in sessions.items():
            kind = entries[0][-1]
            length = 2 if kind == "lab" else 1
            if (len(entries) != length or any(row[:5] != entries[0][:5] or row[-1] != kind for row in entries)
                    or (length == 2 and abs(entries[0][5] - entries[1][5]) != 1)):
                violations.append(f"Session Integrity: session {sid} is incomplete or inconsistent.")
        if violations:
            for violation in violations:
                log_warning(violation)
        else:
            log_success("Independent Validator Passed: 0 Hard Constraint Violations Detected.")
        return violations
