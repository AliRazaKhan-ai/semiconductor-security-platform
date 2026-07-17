"""Purpose: Expose the production WSGI application object.
Directory: project root.
Dependencies: app.factory.
Connection: Gunicorn imports this module as wsgi:app.
"""

from app.factory import create_app

app = create_app()

