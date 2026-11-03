class GenerationCancelled(Exception):
    """Generation was cancelled by the caller."""


def check_cancelled(event):
    if event is not None and event.is_set():
        raise GenerationCancelled("Timetable generation cancelled.")
