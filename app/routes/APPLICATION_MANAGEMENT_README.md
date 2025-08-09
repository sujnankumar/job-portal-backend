# Application Management Routes Documentation

This module provides endpoints for employers to manage job applications (accept/reject) and automatically send notifications to job seekers.

## Endpoints

### 1. Accept Application
**POST** `/api/application-management/accept/{application_id}`

- **Authorization**: Employer only
- **Description**: Accept a job application and notify the applicant
- **Request Body** (optional):
  ```json
  {
    "message": "Congratulations! We'd like to proceed with your application..."
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "message": "Application accepted successfully",
    "application_id": "application_id",
    "status": "accepted",
    "applicant_name": "John Doe",
    "job_title": "Software Engineer"
  }
  ```

### 2. Reject Application
**POST** `/api/application-management/reject/{application_id}`

- **Authorization**: Employer only
- **Description**: Reject a job application and notify the applicant
- **Request Body** (optional):
  ```json
  {
    "message": "Thank you for your interest. Unfortunately...",
    "reason": "Experience requirements not met"
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "message": "Application rejected successfully",
    "application_id": "application_id",
    "status": "rejected",
    "applicant_name": "John Doe",
    "job_title": "Software Engineer"
  }
  ```

### 3. Get Application Status
**GET** `/api/application-management/status/{application_id}`

- **Authorization**: Employer (for their jobs) or Job Seeker (for their applications)
- **Description**: Get detailed status of an application
- **Response**:
  ```json
  {
    "application_id": "application_id",
    "status": "accepted",
    "applied_at": "2025-01-01T10:00:00+05:30",
    "status_updated_at": "2025-01-02T15:30:00+05:30",
    "employer_feedback": "Great profile!",
    "rejection_reason": "",
    "job_title": "Software Engineer",
    "company_name": "Tech Corp",
    "applicant": {
      "name": "John Doe",
      "email": "john@example.com"
    }
  }
  ```

### 4. Get Pending Applications
**GET** `/api/application-management/pending`

- **Authorization**: Employer only
- **Description**: Get all pending applications for employer's jobs
- **Response**:
  ```json
  {
    "success": true,
    "pending_applications": [
      {
        "application_id": "app_id_1",
        "job_id": "job_123",
        "job_title": "Software Engineer",
        "company_name": "Tech Corp",
        "applicant_name": "John Doe",
        "applicant_email": "john@example.com",
        "applied_at": "2025-01-01T10:00:00+05:30",
        "status": "pending"
      }
    ],
    "total_count": 1
  }
  ```

## Features

### Automatic Notifications
When an application is accepted or rejected, the system automatically:
- Updates the application status in the database
- Creates a notification record
- Sends real-time WebSocket notification to the job seeker (if online)

### Authorization
- Only employers can accept/reject applications for their own job postings
- Job seekers can only view their own application statuses
- Proper validation ensures users can only access authorized data

### Status Tracking
- Applications can only be accepted/rejected if they are in "pending" status
- Status changes are timestamped with IST timezone
- Employer feedback and rejection reasons are stored

### Error Handling
- Comprehensive error handling for invalid requests
- Proper HTTP status codes
- Meaningful error messages

## Usage Examples

### Frontend Integration
```javascript
// Accept application
const acceptApplication = async (applicationId, message) => {
  const response = await fetch(`/api/application-management/accept/${applicationId}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ message })
  });
  return response.json();
};

// Get pending applications
const getPendingApplications = async () => {
  const response = await fetch('/api/application-management/pending', {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
};
```
