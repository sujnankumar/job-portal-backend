# Timezone Configuration Changes

This document outlines the changes made to standardize timezone handling across the backend to use Indian Standard Time (IST).

## Changes Made

### 1. Created Timezone Utility (`app/utils/timezone_utils.py`)
- Added IST timezone constant (UTC+5:30)
- Created helper functions:
  - `get_ist_now()`: Get current datetime in IST
  - `utc_to_ist()`: Convert UTC datetime to IST
  - `ist_to_utc()`: Convert IST datetime to UTC
  - `format_ist_datetime()`: Format datetime in IST with custom format
  - `parse_ist_datetime()`: Parse datetime string as IST

### 2. Updated Files to Use IST

#### Authentication & JWT
- `app/utils/jwt_handler.py`: Token expiration now calculated in IST
- `app/functions/auth_functions.py`: User registration and onboarding timestamps in IST

#### Job Management
- `app/functions/job_functions.py`: All job-related timestamps (posted_at, expires_at, etc.) in IST
- Job listing and expiration checks now use IST

#### Interview Management
- `app/functions/interview_functions.py`: Interview scheduling and notifications in IST

#### Company Management
- `app/functions/company_functions.py`: Company creation timestamps in IST

#### Resume Management
- `app/functions/resume_functions.py`: Resume upload timestamps in IST

#### Application Management
- `app/routes/application.py`: Application submission, updates, and notifications in IST

## Benefits

1. **Consistency**: All timestamps across the backend now use the same timezone (IST)
2. **User Experience**: Times displayed to users will be in their local timezone (IST)
3. **Debugging**: Easier to debug time-related issues with consistent timezone
4. **Database**: All datetime fields in MongoDB now consistently use IST

## Important Notes

- JWT tokens still use UTC internally (as per standard practice) but expiration is calculated based on IST
- The timezone utility functions handle conversions between UTC and IST when needed
- All existing data in the database will continue to work, but new entries will use IST
- Frontend applications should expect timestamps in IST format

## Usage Examples

```python
from app.utils.timezone_utils import get_ist_now, format_ist_datetime

# Get current time in IST
current_time = get_ist_now()

# Format datetime for display
formatted_time = format_ist_datetime(current_time, "%Y-%m-%d %H:%M:%S %Z")
```
