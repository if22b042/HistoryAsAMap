from frontend.app import app
from backend.models.model import db, Tag

with app.app_context():
    tags = Tag.query.order_by(Tag.name).all()
    result = [tag.to_dict() for tag in tags]
    print(f"Total tags: {len(result)}")
    print("First 3 tags:")
    for tag in result[:3]:
        print(f"  {tag}")
