from backend.models.model import db, Tag
from frontend.app import app

with app.app_context():
    tags = Tag.query.all()
    print(f'Tags in database: {len(tags)}')
    for tag in tags:
        print(f'  - {tag.id}: {tag.name}')
