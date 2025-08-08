from datetime import datetime, timezone, timedelta

# Indian Standard Time (IST) - UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now():
    """Get current datetime in IST timezone"""
    return datetime.now(IST)

def utc_to_ist(utc_dt):
    """Convert UTC datetime to IST"""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(IST)

def ist_to_utc(ist_dt):
    """Convert IST datetime to UTC"""
    if ist_dt.tzinfo is None:
        ist_dt = ist_dt.replace(tzinfo=IST)
    return ist_dt.astimezone(timezone.utc)

def format_ist_datetime(dt, format_str="%Y-%m-%d %H:%M:%S %Z"):
    """Format datetime in IST with custom format"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ist_dt = dt.astimezone(IST)
    return ist_dt.strftime(format_str)

def parse_ist_datetime(dt_str, format_str="%Y-%m-%d %H:%M:%S"):
    """Parse datetime string as IST"""
    dt = datetime.strptime(dt_str, format_str)
    return dt.replace(tzinfo=IST)
