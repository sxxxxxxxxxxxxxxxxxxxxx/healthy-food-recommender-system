from app import app as flask_app
from app import db, _ensure_food_image_column, initialize_data

_initialized = False


def _lazy_init():
    global _initialized
    if _initialized:
        return
    with flask_app.app_context():
        db.create_all()
        _ensure_food_image_column()
    initialize_data()
    _initialized = True


@flask_app.before_request
def _init_once():
    _lazy_init()


# ✅ 这一行必须存在
app = flask_app
