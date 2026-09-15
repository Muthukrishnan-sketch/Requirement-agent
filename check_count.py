from database.db import session_scope
from database.models import Candidate
with session_scope() as db:
    print(db.query(Candidate).count())
