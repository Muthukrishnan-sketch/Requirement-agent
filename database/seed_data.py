"""
Seeds the database with sample candidates and jobs so the end-to-end demo
(`Find the top 5 Python developers with at least 2 years of experience and
shortlist them`) has real data to run against.

Run with:  python -m database.seed_data
"""

from database.db import init_db, session_scope
from database.models import Candidate, Job

SAMPLE_CANDIDATES = [
    dict(full_name="Ananya Rao", email="ananya.rao@example.com", phone="9840000001",
         location="Chennai", skills=["python", "fastapi", "postgresql", "docker"],
         years_experience=3.5, current_title="Backend Developer",
         resume_summary="Backend engineer focused on Python microservices and APIs."),
    dict(full_name="Kevin Mathew", email="kevin.mathew@example.com", phone="9840000002",
         location="Bengaluru", skills=["python", "django", "aws", "redis"],
         years_experience=5.0, current_title="Senior Software Engineer",
         resume_summary="5 years building Django-based SaaS backends on AWS."),
    dict(full_name="Priya Sundaram", email="priya.sundaram@example.com", phone="9840000003",
         location="Chennai", skills=["python", "machine learning", "pandas", "sql"],
         years_experience=2.0, current_title="Data Scientist",
         resume_summary="Data scientist with 2 years applying ML to churn prediction."),
    dict(full_name="Rahul Verma", email="rahul.verma@example.com", phone="9840000004",
         location="Hyderabad", skills=["java", "spring boot", "kafka"],
         years_experience=4.0, current_title="Java Developer",
         resume_summary="Java backend developer, event-driven microservices."),
    dict(full_name="Divya Krishnan", email="divya.krishnan@example.com", phone="9840000005",
         location="Chennai", skills=["python", "flask", "mysql", "celery"],
         years_experience=1.2, current_title="Junior Python Developer",
         resume_summary="Early-career Python developer, Flask APIs and task queues."),
    dict(full_name="Sanjay Iyer", email="sanjay.iyer@example.com", phone="9840000006",
         location="Chennai", skills=["python", "fastapi", "mongodb", "react"],
         years_experience=2.8, current_title="Full Stack Developer",
         resume_summary="Full-stack dev, FastAPI backends with a React frontend."),
    dict(full_name="Meera Nair", email="meera.nair@example.com", phone="9840000007",
         location="Kochi", skills=["javascript", "node.js", "express"],
         years_experience=3.0, current_title="Node.js Developer",
         resume_summary="Node.js backend developer for e-commerce platforms."),
    dict(full_name="Arjun Pillai", email="arjun.pillai@example.com", phone="9840000008",
         location="Chennai", skills=["python", "fastapi", "postgresql", "kubernetes"],
         years_experience=6.0, current_title="Staff Engineer",
         resume_summary="Staff engineer leading Python platform teams for 6 years."),
    dict(full_name="Fathima Beevi", email="fathima.beevi@example.com", phone="9840000009",
         location="Coimbatore", skills=["python", "scrapy", "selenium", "sql"],
         years_experience=2.3, current_title="Automation Engineer",
         resume_summary="Web scraping and automation specialist using Python."),
    dict(full_name="Vikram Shetty", email="vikram.shetty@example.com", phone="9840000010",
         location="Mumbai", skills=["c++", "embedded systems"],
         years_experience=7.0, current_title="Embedded Engineer",
         resume_summary="Embedded systems engineer, no backend web experience."),
]

SAMPLE_JOBS = [
    dict(title="Python Developer", department="Engineering",
         required_skills=["python", "fastapi", "sql"], min_experience=2.0,
         description="Build and maintain backend services in Python/FastAPI.",
         status="open"),
    dict(title="Data Scientist", department="Data",
         required_skills=["python", "machine learning", "pandas"], min_experience=1.5,
         description="Own churn and recommendation models end to end.",
         status="open"),
]


def run():
    init_db()
    with session_scope() as db:
        if db.query(Candidate).count() == 0:
            db.add_all([Candidate(**c) for c in SAMPLE_CANDIDATES])
        if db.query(Job).count() == 0:
            db.add_all([Job(**j) for j in SAMPLE_JOBS])
    print("Database seeded.")


if __name__ == "__main__":
    run()
