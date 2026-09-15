from database.db import session_scope
from database.models import Candidate

with session_scope() as db:
    c = db.query(Candidate).get(11)
    c.current_title = "Java Developer"
    c.resume_summary = "Backend developer with Python and Java experience."
    print("Updated candidate:", c.full_name, "-", c.current_title)
