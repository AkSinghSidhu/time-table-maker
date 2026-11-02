import time
import os
from ortools.sat.python import cp_model
import pandas as pd
from engine.logger import log_step, log_info, log_success, log_warning, log_error

class TimetableCPSATSolver:
    """Google OR-Tools CP-SAT solver implementing the specification in timetable-generator-planning-report.md."""

    def __init__(self, data):
        self.data = data
        self.days = data.working_days
        self.periods_per_day = data.periods_per_day
        self.break_after_period = getattr(data, "break_after_period", 0)

        # Slot indexing for all teaching lectures 1..periods_per_day
        self.slot_map = {}
        self.inverse_slot_map = {}
        idx = 0
        for day in self.days:
            for p in range(1, self.periods_per_day + 1):
                self.slot_map[idx] = (day, p)
                self.inverse_slot_map[(day, p)] = idx
                idx += 1

        self.total_slots = idx

        # All periods 1..periods_per_day are valid teaching lectures
        self.valid_theory_slots = list(range(self.total_slots))

        # Valid lab start slots: 2 consecutive periods on same day that DO NOT straddle the break
        self.valid_lab_start_slots = []
        for i, (d, p) in self.slot_map.items():
            # Must have next period on same day
            if p + 1 <= self.periods_per_day:
                # Cannot start at break_after_period (as p would be before break and p+1 after break)
                if self.break_after_period > 0 and p == self.break_after_period:
                    continue
                self.valid_lab_start_slots.append(i)

        self.subjects_map = {str(row["subject_id"]): row for _, row in data.subjects.iterrows()}
        self.teachers_map = {str(row["teacher_id"]): row for _, row in data.teachers.iterrows()}
        self.classes_map = {str(row["class_id"]): row for _, row in data.classes.iterrows()}
        self.rooms_map = {str(row["room_id"]): row for _, row in data.rooms.iterrows()}

        self.teacher_unavail_slots = set()
        if not data.unavailability.empty:
            for _, row in data.unavailability.iterrows():
                t_id = str(row["teacher_id"]).strip()
                d = str(row["day"]).strip()
                p = int(row["period"])
                if (d, p) in self.inverse_slot_map:
                    self.teacher_unavail_slots.add((t_id, self.inverse_slot_map[(d, p)]))

    def solve(self, time_limit_seconds=30):
        log_step("⚡ Step 3: Formulating Google OR-Tools CP-SAT Model")
        start_solve_time = time.time()
        model = cp_model.CpModel()

        sessions = []
        session_id = 0

        for _, row in self.data.assignments.iterrows():
            c_id = str(row["class_id"])
            s_id = str(row["subject_id"])
            t_id = str(row["teacher_id"])

            s_row = self.subjects_map.get(s_id)
            if s_row is None:
                continue

            t_count = int(s_row["theory_sessions_per_week"])
            l_count = int(s_row["lab_sessions_per_week"])
            priority = int(s_row.get("priority", 2))
            req_lab_cat = str(s_row.get("lab_room_category", "")).strip()

            for _ in range(t_count):
                sessions.append({
                    "id": session_id,
                    "class_id": c_id,
                    "subject_id": s_id,
                    "teacher_id": t_id,
                    "type": "theory",
                    "length": 1,
                    "priority": priority,
                    "req_lab_cat": None,
                })
                session_id += 1

            for _ in range(l_count):
                sessions.append({
                    "id": session_id,
                    "class_id": c_id,
                    "subject_id": s_id,
                    "teacher_id": t_id,
                    "type": "lab",
                    "length": 2,
                    "priority": priority,
                    "req_lab_cat": req_lab_cat,
                })
                session_id += 1

        th_cnt = sum(1 for s in sessions if s["type"] == "theory")
        lab_cnt = sum(1 for s in sessions if s["type"] == "lab")
        log_info(f"Formulated {len(sessions)} total sessions ({th_cnt} theory, {lab_cnt} lab blocks).")

        session_vars = {}
        class_intervals = {c_id: [] for c_id in self.classes_map}
        teacher_intervals = {t_id: [] for t_id in self.teachers_map}
        room_optional_intervals = {r_id: [] for r_id in self.rooms_map}

        lab_rooms_by_cat = {}
        for r_id, r_row in self.rooms_map.items():
            if str(r_row.get("type", "")).lower() == "lab":
                cat = str(r_row.get("lab_category", "")).strip()
                lab_rooms_by_cat.setdefault(cat, []).append(r_id)

        for sess in sessions:
            sid = sess["id"]
            c_id = sess["class_id"]
            t_id = sess["teacher_id"]
            stype = sess["type"]
            length = sess["length"]

            if stype == "theory":
                allowed_starts = [
                    s for s in self.valid_theory_slots
                    if (t_id, s) not in self.teacher_unavail_slots
                ]
            else:
                allowed_starts = [
                    s for s in self.valid_lab_start_slots
                    if (t_id, s) not in self.teacher_unavail_slots and (t_id, s + 1) not in self.teacher_unavail_slots
                ]

            if not allowed_starts:
                raise ValueError(f"No valid time slots available for session {sess['subject_id']} (class {c_id}, teacher {t_id}).")

            start_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(allowed_starts), f"start_{sid}")
            end_var = model.NewIntVar(0, self.total_slots, f"end_{sid}")
            model.Add(end_var == start_var + length)
            interval_var = model.NewIntervalVar(start_var, length, end_var, f"interval_{sid}")

            sess_info = {
                "start": start_var,
                "end": end_var,
                "interval": interval_var,
                "room_literals": {}
            }

            class_intervals.setdefault(c_id, []).append(interval_var)
            teacher_intervals.setdefault(t_id, []).append(interval_var)

            if stype == "lab":
                cat = sess["req_lab_cat"]
                cand_rooms = lab_rooms_by_cat.get(cat, [])
                if not cand_rooms:
                    cand_rooms = [r for r, r_row in self.rooms_map.items() if str(r_row.get("type", "")).lower() == "lab"]

                room_lits = []
                for r_id in cand_rooms:
                    r_lit = model.NewBoolVar(f"room_{sid}_{r_id}")
                    opt_interval = model.NewOptionalIntervalVar(start_var, length, end_var, r_lit, f"opt_interval_{sid}_{r_id}")
                    room_optional_intervals.setdefault(r_id, []).append(opt_interval)
                    sess_info["room_literals"][r_id] = r_lit
                    room_lits.append(r_lit)

                if room_lits:
                    model.AddExactlyOne(room_lits)

            session_vars[sid] = sess_info

        log_info("Formulated 12 Hard Constraints (Class, Teacher & Room NoOverlap, Lab Block Continuity, Daily Caps, Exclusions)...")

        # 1. Class No-Overlap
        for c_id, intervals in class_intervals.items():
            if intervals:
                model.AddNoOverlap(intervals)

        # 2. Teacher No-Overlap
        for t_id, intervals in teacher_intervals.items():
            if intervals:
                model.AddNoOverlap(intervals)

        # 3. Room No-Overlap
        for r_id, opt_intervals in room_optional_intervals.items():
            if opt_intervals:
                model.AddNoOverlap(opt_intervals)

        # 4, 5, 6. Daily Lab Caps per Class
        day_slot_indices = {day: [self.inverse_slot_map[(day, p)] for p in range(1, self.periods_per_day + 1)] for day in self.days}

        for c_id in self.classes_map:
            c_sessions = [s for s in sessions if s["class_id"] == c_id]
            c_labs = [s for s in c_sessions if s["type"] == "lab"]

            for day, d_slots in day_slot_indices.items():
                min_s, max_s = min(d_slots), max(d_slots)
                day_domain = cp_model.Domain.FromIntervals([[min_s, max_s]])

                day_lab_starts = []
                for sess in c_labs:
                    sid = sess["id"]
                    start_v = session_vars[sid]["start"]
                    is_on_day = model.NewBoolVar(f"lab_{sid}_on_{day}")
                    model.AddLinearExpressionInDomain(start_v, day_domain).OnlyEnforceIf(is_on_day)
                    model.AddLinearExpressionInDomain(start_v, day_domain.complement()).OnlyEnforceIf(is_on_day.Not())
                    day_lab_starts.append(is_on_day)

                if day_lab_starts:
                    model.Add(sum(day_lab_starts) <= 2)

                subjs_in_class = set(s["subject_id"] for s in c_labs)
                for s_id in subjs_in_class:
                    same_subj_labs_on_day = []
                    for sess in c_labs:
                        if sess["subject_id"] == s_id:
                            sid = sess["id"]
                            start_v = session_vars[sid]["start"]
                            b_on_day = model.NewBoolVar(f"lab_{sid}_{s_id}_on_{day}")
                            model.AddLinearExpressionInDomain(start_v, day_domain).OnlyEnforceIf(b_on_day)
                            model.AddLinearExpressionInDomain(start_v, day_domain.complement()).OnlyEnforceIf(b_on_day.Not())
                            same_subj_labs_on_day.append(b_on_day)

                    if len(same_subj_labs_on_day) > 1:
                        model.Add(sum(same_subj_labs_on_day) <= 1)

        # 7. Teacher Daily Max Periods
        for t_id, t_row in self.teachers_map.items():
            max_d = int(t_row.get("max_periods_day", 5))
            t_sessions = [s for s in sessions if s["teacher_id"] == t_id]

            for day, d_slots in day_slot_indices.items():
                slot_occs = []
                for s_idx in d_slots:
                    sess_covers = []
                    for sess in t_sessions:
                        sid = sess["id"]
                        start_v = session_vars[sid]["start"]
                        end_v = session_vars[sid]["end"]

                        b1 = model.NewBoolVar(f"b1_{s_idx}_{sid}")
                        b2 = model.NewBoolVar(f"b2_{s_idx}_{sid}")
                        model.Add(start_v <= s_idx).OnlyEnforceIf(b1)
                        model.Add(start_v > s_idx).OnlyEnforceIf(b1.Not())
                        model.Add(end_v > s_idx).OnlyEnforceIf(b2)
                        model.Add(end_v <= s_idx).OnlyEnforceIf(b2.Not())

                        covers = model.NewBoolVar(f"t_{t_id}_cov_{s_idx}_{sid}")
                        model.AddBoolAnd([b1, b2]).OnlyEnforceIf(covers)
                        model.AddBoolOr([b1.Not(), b2.Not()]).OnlyEnforceIf(covers.Not())
                        sess_covers.append(covers)

                    slot_occ = model.NewBoolVar(f"t_occ_{t_id}_{s_idx}")
                    if sess_covers:
                        model.Add(sum(sess_covers) >= 1).OnlyEnforceIf(slot_occ)
                        model.Add(sum(sess_covers) == 0).OnlyEnforceIf(slot_occ.Not())
                        slot_occs.append(slot_occ)

                if slot_occs:
                    model.Add(sum(slot_occs) <= max_d)

        # --- SOFT OBJECTIVES ---
        log_info("Formulated Soft Objectives (Subject Priority Rewards, Lunch-Half Balance, Same-Subject Repeat Penalties)...")
        obj_terms = []

        for sess in sessions:
            sid = sess["id"]
            start_v = session_vars[sid]["start"]
            priority = sess["priority"]
            p_weight = (4 - min(priority, 3)) * 10
            for s_idx, (day, p) in self.slot_map.items():
                is_at_slot = model.NewBoolVar(f"at_slot_{sid}_{s_idx}")
                model.Add(start_v == s_idx).OnlyEnforceIf(is_at_slot)
                model.Add(start_v != s_idx).OnlyEnforceIf(is_at_slot.Not())
                reward = p_weight * (self.periods_per_day - p)
                obj_terms.append(is_at_slot * reward)

        for c_id in self.classes_map:
            c_sessions = [s for s in sessions if s["class_id"] == c_id]
            subjs_in_class = set(s["subject_id"] for s in c_sessions)

            for day, d_slots in day_slot_indices.items():
                min_s, max_s = min(d_slots), max(d_slots)
                day_domain = cp_model.Domain.FromIntervals([[min_s, max_s]])

                if self.break_after_period > 0:
                    before_lunch_slots = [self.inverse_slot_map[(day, p)] for p in range(1, self.break_after_period + 1)]
                    after_lunch_slots = [self.inverse_slot_map[(day, p)] for p in range(self.break_after_period + 1, self.periods_per_day + 1)]

                    before_occs = []
                    after_occs = []

                    for sess in c_sessions:
                        sid = sess["id"]
                        start_v = session_vars[sid]["start"]
                        length = sess["length"]

                        if before_lunch_slots:
                            b_min, b_max = min(before_lunch_slots), max(before_lunch_slots)
                            b_dom = cp_model.Domain.FromIntervals([[b_min, b_max]])
                            is_before = model.NewBoolVar(f"c_bef_{sid}_{day}")
                            model.AddLinearExpressionInDomain(start_v, b_dom).OnlyEnforceIf(is_before)
                            model.AddLinearExpressionInDomain(start_v, b_dom.complement()).OnlyEnforceIf(is_before.Not())
                            before_occs.append(is_before * length)

                        if after_lunch_slots:
                            a_min, a_max = min(after_lunch_slots), max(after_lunch_slots)
                            a_dom = cp_model.Domain.FromIntervals([[a_min, a_max]])
                            is_after = model.NewBoolVar(f"c_aft_{sid}_{day}")
                            model.AddLinearExpressionInDomain(start_v, a_dom).OnlyEnforceIf(is_after)
                            model.AddLinearExpressionInDomain(start_v, a_dom.complement()).OnlyEnforceIf(is_after.Not())
                            after_occs.append(is_after * length)

                    if before_occs and after_occs:
                        diff = model.NewIntVar(0, self.periods_per_day, f"lunch_bal_diff_{c_id}_{day}")
                        sum_before = sum(before_occs)
                        sum_after = sum(after_occs)
                        model.Add(diff >= sum_before - sum_after)
                        model.Add(diff >= sum_after - sum_before)
                        obj_terms.append(diff * -5)

                for s_id in subjs_in_class:
                    s_th_sessions = [s for s in c_sessions if s["subject_id"] == s_id and s["type"] == "theory"]
                    s_lab_sessions = [s for s in c_sessions if s["subject_id"] == s_id and s["type"] == "lab"]

                    th_on_day_lits = []
                    for sess in s_th_sessions:
                        sid = sess["id"]
                        start_v = session_vars[sid]["start"]
                        is_on_day = model.NewBoolVar(f"th_{sid}_{day}")
                        model.AddLinearExpressionInDomain(start_v, day_domain).OnlyEnforceIf(is_on_day)
                        model.AddLinearExpressionInDomain(start_v, day_domain.complement()).OnlyEnforceIf(is_on_day.Not())
                        th_on_day_lits.append(is_on_day)

                    lab_on_day_lits = []
                    for sess in s_lab_sessions:
                        sid = sess["id"]
                        start_v = session_vars[sid]["start"]
                        is_on_day = model.NewBoolVar(f"lab_rep_{sid}_{day}")
                        model.AddLinearExpressionInDomain(start_v, day_domain).OnlyEnforceIf(is_on_day)
                        model.AddLinearExpressionInDomain(start_v, day_domain.complement()).OnlyEnforceIf(is_on_day.Not())
                        lab_on_day_lits.append(is_on_day)

                    if len(th_on_day_lits) >= 2:
                        is_th_repeat = model.NewBoolVar(f"th_repeat_{c_id}_{s_id}_{day}")
                        th_sum = sum(th_on_day_lits)
                        model.Add(th_sum >= 2).OnlyEnforceIf(is_th_repeat)
                        model.Add(th_sum <= 1).OnlyEnforceIf(is_th_repeat.Not())
                        obj_terms.append(is_th_repeat * -15)

                    if th_on_day_lits and lab_on_day_lits:
                        has_th = model.NewBoolVar(f"has_th_{c_id}_{s_id}_{day}")
                        has_lab = model.NewBoolVar(f"has_lab_{c_id}_{s_id}_{day}")
                        model.Add(sum(th_on_day_lits) >= 1).OnlyEnforceIf(has_th)
                        model.Add(sum(th_on_day_lits) == 0).OnlyEnforceIf(has_th.Not())
                        model.Add(sum(lab_on_day_lits) >= 1).OnlyEnforceIf(has_lab)
                        model.Add(sum(lab_on_day_lits) == 0).OnlyEnforceIf(has_lab.Not())

                        is_lab_th_repeat = model.NewBoolVar(f"lab_th_repeat_{c_id}_{s_id}_{day}")
                        model.AddBoolAnd([has_th, has_lab]).OnlyEnforceIf(is_lab_th_repeat)
                        model.AddBoolOr([has_th.Not(), has_lab.Not()]).OnlyEnforceIf(is_lab_th_repeat.Not())
                        obj_terms.append(is_lab_th_repeat * -75)

        model.Maximize(sum(obj_terms))

        # Solve
        log_step("🚀 Step 4: Executing CP-SAT Solver", f"Time limit: {time_limit_seconds}s")
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        # Parallel search: use all available cores except one (massively improves
        # the chance of reaching a feasible schedule inside the time limit).
        workers = max(1, (os.cpu_count() or 2) - 1)
        try:
            solver.parameters.num_search_workers = workers
            log_info(f"Solving with {workers} parallel workers.")
        except Exception:
            pass
        status = solver.Solve(model)

        elapsed = time.time() - start_solve_time
        status_name = solver.StatusName(status)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            log_error(f"Solver returned {status_name} after {elapsed:.2f}s.")
            raise RuntimeError("CP-SAT solver failed to find a feasible solution under the given constraints.")

        obj_val = solver.ObjectiveValue()
        log_success(f"CP-SAT Solver Status: {status_name} (Solved in {elapsed:.2f}s, Objective Value: {obj_val:.1f}).")

        # Extract master schedule
        master_schedule = []
        for sess in sessions:
            sid = sess["id"]
            start_val = solver.Value(session_vars[sid]["start"])
            stype = sess["type"]
            length = sess["length"]

            selected_room = None
            if stype == "lab":
                for r_id, r_lit in session_vars[sid]["room_literals"].items():
                    if solver.Value(r_lit) == 1:
                        selected_room = r_id
                        break

            for offset in range(length):
                slot_idx = start_val + offset
                day, period = self.slot_map[slot_idx]
                master_schedule.append({
                    "class_id": sess["class_id"],
                    "subject_id": sess["subject_id"],
                    "teacher_id": sess["teacher_id"],
                    "room_id": selected_room,
                    "day": day,
                    "period": period,
                    "type": stype
                })

        log_info(f"Extracted {len(master_schedule)} master schedule entries.")
        return master_schedule
