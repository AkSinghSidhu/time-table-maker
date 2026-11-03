import pandas as pd
import os
import re
import tempfile
from engine.logger import log_step, log_info, log_success

class TimetableExporter:
    """Generates Class views, Teacher views, and exports formatted Excel workbooks."""

    @staticmethod
    def generate_projections(master_schedule, data):
        days = data.working_days
        periods_per_day = data.periods_per_day
        break_after_period = getattr(data, "break_after_period", 0)

        # Build column list: Period 1..N with separate BREAK column inserted after break_after_period
        periods_cols = []
        for p in range(1, periods_per_day + 1):
            periods_cols.append(f"Period {p}")
            if break_after_period > 0 and p == break_after_period:
                periods_cols.append("BREAK")

        subj_name = {str(row["subject_id"]): str(row["name"]) for _, row in data.subjects.iterrows()}
        teacher_name = {str(row["teacher_id"]): str(row["name"]) for _, row in data.teachers.iterrows()}
        class_name = {str(row["class_id"]): str(row["name"]) for _, row in data.classes.iterrows()}

        class_ids = list(data.classes["class_id"].astype(str).unique())
        teacher_ids = list(data.teachers["teacher_id"].astype(str).unique())

        log_step("📊 Step 6: Generating Schedule Projections", f"Class Views: {len(class_ids)}, Teacher Views: {len(teacher_ids)}")

        class_grids = {}
        teacher_grids = {}

        for c_id in class_ids:
            df = pd.DataFrame(index=days, columns=periods_cols)
            df.fillna("Free", inplace=True)
            if "BREAK" in df.columns:
                df["BREAK"] = "LUNCH BREAK"
            class_grids[c_id] = df

        for t_id in teacher_ids:
            df = pd.DataFrame(index=days, columns=periods_cols)
            df.fillna("Free", inplace=True)
            if "BREAK" in df.columns:
                df["BREAK"] = "LUNCH BREAK"
            teacher_grids[t_id] = df

        for entry in master_schedule:
            c_id = entry["class_id"]
            s_id = entry["subject_id"]
            t_id = entry["teacher_id"]
            r_id = entry.get("room_id")
            day = entry["day"]
            p = entry["period"]
            stype = entry["type"]

            p_col = f"Period {p}"
            s_display = subj_name.get(s_id, s_id)
            t_display = teacher_name.get(t_id, t_id)
            c_display = class_name.get(c_id, c_id)

            lab_tag = " [LAB]" if stype == "lab" else ""
            room_tag = f" ({r_id})" if r_id and str(r_id) != "None" else ""

            cell_class = f"{s_display} ({t_display}){lab_tag}{room_tag}"
            if c_id in class_grids and day in class_grids[c_id].index and p_col in class_grids[c_id].columns:
                class_grids[c_id].at[day, p_col] = cell_class

            cell_teacher = f"{c_display} - {s_display}{lab_tag}"
            if t_id in teacher_grids and day in teacher_grids[t_id].index and p_col in teacher_grids[t_id].columns:
                teacher_grids[t_id].at[day, p_col] = cell_teacher

        log_info(f"Generated grids for Class Sections: {', '.join(class_ids)}")
        log_info(f"Generated grids for Teachers: {', '.join(teacher_ids)}")

        return class_grids, teacher_grids

    @staticmethod
    def named_grids(class_grids, teacher_grids):
        """Return Excel-safe, case-insensitively unique names for every view."""
        used = set()
        named = []
        for prefix, grids in (("Class_", class_grids), ("Tr_", teacher_grids)):
            for key, grid in grids.items():
                base = re.sub(r"[\\/*?:\[\]\x00-\x1f]", "_", prefix + str(key)).strip("'")
                name = base[:31].rstrip("'")
                suffix = 1
                while name.casefold() in used:
                    tag = f"_{suffix}"
                    name = base[:31 - len(tag)] + tag
                    suffix += 1
                used.add(name.casefold())
                named.append((name, grid))
        return named

    @staticmethod
    def export_excel(class_grids, teacher_grids, output_path):
        log_step("💾 Step 7: Exporting Schedule to Excel Workbook", output_path)
        named = TimetableExporter.named_grids(class_grids, teacher_grids)
        if not named:
            raise ValueError("There are no timetable views to export.")
        destination = os.path.abspath(output_path)
        fd, temporary = tempfile.mkstemp(suffix=".xlsx", dir=os.path.dirname(destination))
        os.close(fd)
        try:
            with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
                for sheet_name, df in named:
                    df.to_excel(writer, sheet_name=sheet_name)
                    # Timetable labels are text, even when an imported name starts with '='.
                    for row in writer.sheets[sheet_name].iter_rows():
                        for cell in row:
                            if cell.data_type == "f":
                                cell.data_type = "s"
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)

        log_success(f"Workbook successfully exported to {output_path}")
        return output_path
