import uvicorn
import os
import sys

if __name__ == "__main__":
    # main.py lives in the same folder as run.py
    root_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, root_dir)
    print("Starting Smart Academic Resource Exchange Server...")
    print("Access frontend at: http://127.0.0.1:8000/")
    print("API documentation at: http://127.0.0.1:8000/docs")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, app_dir=root_dir)
