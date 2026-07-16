from flask import Flask
from controllers.add_new_entry import add_new_entry
from models.model import db

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"  # Use an in-memory DB
app.config["SECRET_KEY"] = "test_secret"
db.init_app(app)

with app.app_context():
    db.create_all()

    # Test adding an entry
    add_new_entry("https://en.wikipedia.org/wiki/Battle_of_Verdun", tablenum=0)
