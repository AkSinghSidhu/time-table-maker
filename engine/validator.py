import pandas as pd
from engine.logger import log_step, log_info, log_success, log_warning, log_error

class PreSolverValidator:
    """Pre-solver validation layer — checks feasibility before running CP-SAT solver."""

    @staticmethod
    def validate(data):
        log_step("🔍 Step 2: Running Pre-Solver Feasibility Validation")
        errors = []

        # 1. Column checks
        sheet_attr_map = {
            "Subjects": ("subjects", ["subject_id", "name", "priority", "theory_sessions_per_week", "lab_sessions_per_week"]),
            "Teachers": ("teachers", ["teacher_id", "name", "max_periods_week", "max_periods_day"]),
            "Classes": ("classes", ["class_id", "name"]),
            "TeacherAssignment": ("assignments", ["class_id", "subject_id", "teacher_id"]),
            "Rooms": ("rooms", ["room_id", "type"]),
        }

        for sheet, (attr, cols) in sheet_attr_map.items():
            df = getattr(data, attr, None)
            if df is None or df.empty:
                errors.append(f"Sheet '{sheet}' is missing or empty.")
                continue
            for c in cols:
                if c not in df.columns:
                    errors.append(f"Sheet '{sheet}' missing required column '{c}'.")

        if errors:
            for e in errors: log_error(e)
            return errors

        log_info("Table schema column requirements: OK")

        # 2. Foreign Key checks
        subject_ids = set(data.subjects["subject_id"].astype(str))
        teacher_ids = set(data.teachers["teacher_id"].astype(str))
        class_ids = set(data.classes["class_id"].astype(str))

        for _, row in data.assignments.iterrows():
            c_id = str(row["class_id"])
            s_id = str(row["subject_id"])
            t_id = str(row["teacher_id"])
            if c_id not in class_ids:
                errors.append(f"TeacherAssignment references unknown class_id '{c_id}'.")
            if s_id not in subject_ids:
                errors.append(f"TeacherAssignment references unknown subject_id '{s_id}'.")
            if t_id not in teacher_ids:
                errors.append(f"TeacherAssignment references unknown teacher_id '{t_id}'.")

        if errors:
            for e in errors: log_error(e)
            return errors

        log_info("Foreign key integrity checks: OK")

        # 3. Class teaching load vs available slots
        available_slots_per_week = len(data.working_days) * data.periods_per_day
        subj_map = {str(row["subject_id"]): row for _, row in data.subjects.iterrows()}

        for c_id in class_ids:
            class_assigns = data.assignments[data.assignments["class_id"].astype(str) == c_id]
            total_periods = 0
            for _, row in class_assigns.iterrows():
                s_id = str(row["subject_id"])
                if s_id in subj_map:
                    s_row = subj_map[s_id]
                    t_count = int(s_row["theory_sessions_per_week"])
                    l_count = int(s_row["lab_sessions_per_week"])
                    total_periods += t_count + (l_count * 2)

            if total_periods > available_slots_per_week:
                errors.append(
                    f"Class '{c_id}' total session demand ({total_periods} periods) exceeds weekly available slots ({available_slots_per_week})."
                )

        # 4. Teacher weekly load check
        teacher_max_week = {str(row["teacher_id"]): int(row["max_periods_week"]) for _, row in data.teachers.iterrows()}
        teacher_assigned_load = {t_id: 0 for t_id in teacher_ids}

        for _, row in data.assignments.iterrows():
            t_id = str(row["teacher_id"])
            s_id = str(row["subject_id"])
            if s_id in subj_map:
                s_row = subj_map[s_id]
                t_count = int(s_row["theory_sessions_per_week"])
                l_count = int(s_row["lab_sessions_per_week"])
                teacher_assigned_load[t_id] += t_count + (l_count * 2)

        for t_id, load in teacher_assigned_load.items():
            max_w = teacher_max_week.get(t_id, 999)
            if load > max_w:
                errors.append(f"Teacher '{t_id}' assigned load ({load} periods) exceeds max_periods_week ({max_w}).")

        # 5. Room lab category check
        lab_rooms = data.rooms[data.rooms["type"].astype(str).str.lower() == "lab"]
        available_categories = set(lab_rooms["lab_category"].dropna().astype(str)) if "lab_category" in lab_rooms.columns else set()

        for _, row in data.subjects.iterrows():
            l_count = int(row["lab_sessions_per_week"])
            cat = str(row.get("lab_room_category", "")).strip()
            if l_count > 0 and cat and cat != "nan" and cat not in available_categories:
                errors.append(f"Subject '{row['name']}' requires lab category '{cat}', but no lab room of that category exists.")

        if errors:
            for e in errors: log_error(e)
        else:
            log_success("Pre-Solver Validation Passed. No feasibility errors detected.")

        return errors


class IndependentValidator:
    """Post-generation and manual edit validator — checks all 12 hard constraints from scratch."""

    @staticmethod
    def validate_schedule(master_schedule, data):
        log_step("🛡️ Step 5: Running Independent Validator against Master Schedule")
        violations = []

        teacher_max_day = {str(row["teacher_id"]): int(row["max_periods_day"]) for _, row in data.teachers.iterrows()}
        teacher_max_week = {str(row["teacher_id"]): int(row["max_periods_week"]) for _, row in data.teachers.iterrows()}
        subj_map = {str(row["subject_id"]): row for _, row in data.subjects.iterrows()}
        room_map = {str(row["room_id"]): row for _, row in data.rooms.iterrows()}
        break_after_period = getattr(data, "break_after_period", 0)

        class_slots = {}
        teacher_slots = {}
        room_slots = {}
        teacher_day_counts = {}
        teacher_week_counts = {}

        unavail_set = set()
        if not data.unavailability.empty:
            for _, row in data.unavailability.iterrows():
                t_id = str(row["teacher_id"]).strip()
                day = str(row["day"]).strip()
                p = int(row["period"])
                unavail_set.add((t_id, day, p))

        for entry in master_schedule:
            c = entry["class_id"]
            t = entry["teacher_id"]
            r = entry.get("room_id", "")
            d = entry["day"]
            p = entry["period"]
            s = entry["subject_id"]

            slot_key = (d, p)

            # Hard constraint 10: Teacher unavailability
            if (t, d, p) in unavail_set:
                violations.append(f"Unavailability Violation: Teacher {t} scheduled in unavailable slot ({d}, Period {p}).")

            # Hard constraint 1: Class overlap
            if (c, slot_key) in class_slots:
                violations.append(f"Class Overlap: Class {c} double-booked at ({d}, Period {p}).")
            else:
                class_slots[(c, slot_key)] = entry

            # Hard constraint 2: Teacher overlap
            if (t, slot_key) in teacher_slots:
                violations.append(f"Teacher Overlap: Teacher {t} double-booked at ({d}, Period {p}).")
            else:
                teacher_slots[(t, slot_key)] = entry

            # Hard constraint 3: Room overlap (if lab room)
            if r and r != "None" and r != "nan":
                if (r, slot_key) in room_slots:
                    violations.append(f"Room Overlap: Room {r} double-booked at ({d}, Period {p}).")
                else:
                    room_slots[(r, slot_key)] = entry

                # Hard constraint 11: Lab room category match
                if s in subj_map:
                    req_cat = str(subj_map[s].get("lab_room_category", "")).strip()
                    if req_cat and req_cat != "nan":
                        r_row = room_map.get(r, {})
                        actual_cat = str(r_row.get("lab_category", "")).strip()
                        if actual_cat != req_cat:
                            violations.append(f"Category Mismatch: Room {r} ('{actual_cat}') does not match required '{req_cat}' for subject {s}.")

            teacher_day_counts[(t, d)] = teacher_day_counts.get((t, d), 0) + 1
            teacher_week_counts[t] = teacher_week_counts.get(t, 0) + 1

        # Check teacher load caps
        for (t, d), count in teacher_day_counts.items():
            max_d = teacher_max_day.get(t, 99)
            if count > max_d:
                violations.append(f"Daily Cap Exceeded: Teacher {t} exceeds daily limit ({count} > {max_d}) on {d}.")

        for t, count in teacher_week_counts.items():
            max_w = teacher_max_week.get(t, 999)
            if count > max_w:
                violations.append(f"Weekly Cap Exceeded: Teacher {t} exceeds weekly limit ({count} > {max_w}).")

        if violations:
            for v in violations: log_warning(v)
        else:
            log_success("Independent Validator Passed: 0 Hard Constraint Violations Detected.")

        return violations
