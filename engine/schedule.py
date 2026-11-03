"""One validated schedule shared by the preview and every export."""

from copy import deepcopy

from engine.exporter import TimetableExporter
from engine.validator import IndependentValidator


class ScheduleDocument:
    def __init__(self, master_schedule, data):
        self.data = deepcopy(data)
        self._schedule = deepcopy(master_schedule)
        self.validate()

    @property
    def master_schedule(self):
        return deepcopy(self._schedule)

    def validate(self):
        violations = IndependentValidator.validate_schedule(self._schedule, self.data)
        if violations:
            raise ValueError("\n".join(violations))

    def projections(self):
        self.validate()
        return TimetableExporter.generate_projections(self._schedule, self.data)

    def export_excel(self, path):
        return TimetableExporter.export_excel(*self.projections(), path)

    def swap(self, view, identifier, first_slot, second_slot):
        """Swap whole sessions, or move a session into a free slot, atomically."""
        if view not in {"class_id", "teacher_id"}:
            raise ValueError("Choose a class or teacher view.")
        for day, period in (first_slot, second_slot):
            if day not in self.data.working_days or not 1 <= period <= self.data.periods_per_day:
                raise ValueError("Select teaching periods within the timetable.")

        def group(slot):
            matches = [i for i, row in enumerate(self._schedule)
                       if row[view] == identifier and (row["day"], row["period"]) == slot]
            if not matches:
                return []
            index = matches[0]
            entry = self._schedule[index]
            if entry["type"] == "theory":
                return [index]
            if "session_id" in entry:
                return [i for i, row in enumerate(self._schedule) if row.get("session_id") == entry["session_id"]]
            # Legacy schedules have no session IDs; valid data permits one subject lab per day.
            keys = ("class_id", "subject_id", "teacher_id", "room_id", "day", "type")
            return [i for i, row in enumerate(self._schedule) if all(row.get(key) == entry.get(key) for key in keys)]

        first, second = group(first_slot), group(second_slot)
        if not first and not second:
            return
        if set(first) & set(second):
            raise ValueError("Select two different sessions, or a session and a free period.")
        if first and second and len(first) != len(second):
            raise ValueError("Swap sessions of the same length. Move a lab into two free consecutive periods.")

        def anchor(indices, fallback):
            if not indices:
                return fallback
            row = min((self._schedule[i] for i in indices), key=lambda row: row["period"])
            return row["day"], row["period"]

        first_anchor, second_anchor = anchor(first, first_slot), anchor(second, second_slot)
        candidate = deepcopy(self._schedule)
        for indices, destination in ((first, second_anchor), (second, first_anchor)):
            for offset, index in enumerate(sorted(indices, key=lambda i: self._schedule[i]["period"])):
                candidate[index]["day"] = destination[0]
                candidate[index]["period"] = destination[1] + offset
        violations = IndependentValidator.validate_schedule(candidate, self.data)
        if violations:
            raise ValueError("Swap rejected:\n" + "\n".join(violations))
        self._schedule = candidate
