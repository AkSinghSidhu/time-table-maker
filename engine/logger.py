import datetime
import sys

def log_step(step_name, detail=""):
    """Prints formatted step log to terminal."""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    if detail:
        print(f"[{now}] {step_name} -> {detail}", flush=True)
    else:
        print(f"[{now}] {step_name}", flush=True)

def log_info(message):
    """Prints info line to terminal."""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}]    • {message}", flush=True)

def log_success(message):
    """Prints success line to terminal."""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] ✅ {message}", flush=True)

def log_warning(message):
    """Prints warning line to terminal."""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] ⚠️ {message}", flush=True)

def log_error(message):
    """Prints error line to terminal."""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] ❌ {message}", file=sys.stderr, flush=True)
