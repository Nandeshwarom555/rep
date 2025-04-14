from app import app

# This file is needed for gunicorn to find the app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
