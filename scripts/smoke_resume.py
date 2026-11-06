"""One-off smoke test for the complete Resume Intelligence pipeline."""

from jobpulse.ai.resume import extract_resume_profile
from jobpulse.ai.resume_embeddings import generate_and_save_resume_embedding
from jobpulse.database.repository import save_resume_profile


SAMPLE_RESUME = """
Alex Morgan
Senior Software and Data Engineer

Summary
Software and data engineer with 6 years of experience building reliable backend
services and data platforms. Experienced in distributed systems, APIs, and
production data pipelines.

Skills
Python, SQL, system design, data modeling, REST APIs, distributed systems

Technologies
PostgreSQL, FastAPI, Redis, Docker, Airflow, PySpark, Git

Experience
Senior Software Engineer, DataWorks, 2022-2026
- Built FastAPI services backed by PostgreSQL for customer analytics.
- Designed Redis event pipelines and operated Docker-based deployments.
- Developed Airflow workflows and PySpark jobs processing daily event data.

Software Engineer, Insight Labs, 2020-2022
- Implemented Python data services and SQL reporting pipelines.
- Improved pipeline reliability through monitoring and automated testing.

Projects
- JobPulse: Built a job intelligence platform with Python, FastAPI, Redis,
  PostgreSQL, embeddings, and resume analysis.
- Data Quality Toolkit: Created PySpark checks and Airflow workflows for
  validating large batch datasets.

Education
Bachelor of Technology in Computer Science, University of Bangalore, 2020
""".strip()


def main():
    profile = extract_resume_profile(SAMPLE_RESUME)
    resume_id = save_resume_profile(profile)
    embedding = generate_and_save_resume_embedding(resume_id)

    print(f"resume id: {resume_id}")
    print(f"extracted name: {profile.name}")
    print(f"number of skills: {len(profile.skills)}")
    print(f"extracted technologies: {profile.technologies}")
    print(f"embedding model: {embedding['embedding_model']}")
    print(f"embedding dimensions: {embedding['dimensions']}")
    print("persistence succeeded")


if __name__ == "__main__":
    main()
