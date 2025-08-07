from app.db import db
from gridfs import GridFS
from bson import ObjectId
from datetime import datetime
import pdfplumber
import docx
import spacy
import re
from io import BytesIO

gfs = GridFS(db)
nlp = spacy.load("en_core_web_sm")

def extract_text_from_pdf(file_bytes):
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        text = "\n".join(page.extract_text() or '' for page in pdf.pages)
    return text

def extract_text_from_docx(file_bytes):
    doc = docx.Document(BytesIO(file_bytes))
    return "\n".join([p.text for p in doc.paragraphs])

def extract_email(text):
    match = re.search(r"[\w\.-]+@[\w\.-]+", text)
    return match.group(0) if match else None

def extract_phone(text):
    match = re.search(r"(\+?\d{1,3}[\s-]?)?(\(?\d{3}\)?[\s-]?)?\d{3}[\s-]?\d{4}", text)
    return match.group(0) if match else None

def extract_name(text):
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            return ent.text
    return None

def extract_skills(text):
    skills = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if 'skill' in line.lower():
            for l in lines[i+1:i+10]:
                if l.strip() == '' or len(l.strip()) < 2:
                    break
                skills.extend([s.strip() for s in re.split(r",|;|\|", l) if s.strip()])
            break
    return list(set(skills))

def extract_education(text):
    education_keywords = ["bachelor", "master", "phd", "b.sc", "m.sc", "btech", "mtech", "university", "college", "school"]
    lines = text.splitlines()
    education = [l for l in lines if any(k in l.lower() for k in education_keywords)]
    return education

def extract_experience(text):
    exp_keywords = ["experience", "worked", "company", "role", "position", "employer"]
    lines = text.splitlines()
    experience = [l for l in lines if any(k in l.lower() for k in exp_keywords)]
    return experience

def parse_resume(file_bytes, content_type):
    if content_type == "application/pdf":
        text = extract_text_from_pdf(file_bytes)
    elif content_type in ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]:
        text = extract_text_from_docx(file_bytes)
    else:
        return {"error": "Unsupported file type"}
    return {
        "name": extract_name(text),
        "email": extract_email(text),
        "phone": extract_phone(text),
        "skills": extract_skills(text),
        "education": extract_education(text),
        "experience": extract_experience(text),
        "raw_text": text
    }

# Upload resume
def upload_resume(user_id: str, file, filename: str, content_type: str):
    # Remove old resume if exists
    old = db.resumes.find_one({"user_id": user_id})
    if old:
        gfs.delete(old["file_id"])
        db.resumes.delete_one({"user_id": user_id})
    file_id = gfs.put(file, filename=filename, content_type=content_type, upload_date=datetime.utcnow())
    parsed_data = parse_resume(file, content_type)
    db.resumes.insert_one({
        "user_id": user_id,
        "file_id": file_id,
        "filename": filename,
        "content_type": content_type,
        "upload_date": datetime.utcnow(),
        "parsed_data": parsed_data
    })
    return {"msg": "Resume uploaded", "file_id": str(file_id)}

# Download resume
def get_resume(user_id: str):
    meta = db.resumes.find_one({"user_id": user_id})
    if not meta:
        return None
    file = gfs.get(meta["file_id"])
    return file, meta

# Delete resume
def delete_resume(user_id: str):
    meta = db.resumes.find_one({"user_id": user_id})
    if not meta:
        return False
    gfs.delete(meta["file_id"])
    db.resumes.delete_one({"user_id": user_id})
    return True

# List all resumes (admin/HR)
def list_resumes():
    return list(db.resumes.find({}, {"_id": 0}))

def get_resume_by_file_id(file_id: str):
    # print(file_id)
    resume = db.resumes.find_one({"file_id": ObjectId(file_id)})
    if not resume:
        return None, None
    file = gfs.get(resume.get("file_id")).read()
    # print(resume)
    return file, resume