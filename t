python -c "import os, platform, sys; print(f'\n--- SUCCESS! ---\nRunning on OS: {platform.system()} {platform.release()}\nComputer Name: {platform.node()}\nPython Version: {sys.version.split()[0]}')"


Step 2: Running Docker Containers & AirflowNow that you are virtually sitting inside your desktop, your terminal commands affect your home environment:Press `Ctrl + `` to open your terminal.If you are starting your lab via a Docker container, type your regular start command (e.g., docker run -d -p 8080:8080 my-airflow-image) or your python start scripts.The container will instantly boot up at home and start utilizing your desktop's specs and GPU.Step 3: How to view the Web Interfaces (Crucial)If you start an Airflow web UI, a Dagster board, or a Jupyter Notebook server at home, you cannot see it on your laptop browser by typing localhost normally. You have to use VS Code's Port Forwarding:Look at the bottom terminal panel area in VS Code and click the Ports tab.Click the Forward a Port button.Type the port your tool is using:8080 for Apache Airflow3000 for Dagster8888 for Jupyter NotebooksPress Enter.VS Code will generate a custom link under the Forwarded Address column. Hover over that link and click the globe icon to securely load your home container’s web panel directly inside your school laptop's browser!If you want, tell me:Are you running Airflow using a basic pip install setup, or are you pulling an official Docker image or Docker Compose file?I can give you the exact terminal commands to spin it up cleanly!


python -c "
import sqlite3, os, sys
sys.path.insert(0, '.')
from ml.batch_jobs import create_batch_scheduler, DISTRICTS
print('Districts:', len(DISTRICTS))
sched = create_batch_scheduler()
jobs = sched.get_jobs()
for j in jobs:
    print(j.id, j.next_run_time)
sched.shutdown()
"


python -c "
import sqlite3
con = sqlite3.connect('data/transport.db')
print(con.execute('SELECT created_at, district, predicted_count FROM predictions ORDER BY created_at DESC LIMIT 5').fetchall())
con.close()
"

# Ctrl+C pipeline
python main.py
streamlit run dashboard/app.py


window.ONEMAP_TOKEN = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxNzE4OCwiZm9yZXZlciI6ZmFsc2UsImlzcyI6Ik9uZU1hcCIsImlhdCI6MTc4MjkxNjM4NCwibmJmIjoxNzgyOTE2Mzg0LCJleHAiOjE3ODMxNzU1ODQsImp0aSI6IjljNGM0ZjcxLTNhMjgtNGVlZi04ZTYzLTQ2MzE1OTIxNDk3MSJ9.28Rqjzttiv2aICz5TmV0G8MoD2MZs0AGilNKNXQNp9VbtG548t71p4rzlu74m2Lspb4LPFFFCj_icFCfTL1KDmijM9wUok19-dg_dE1PWPBo7_MxD41nMn4V34rusbiFom-4YM6uwyZTvf5mhYzgOc3_uP5RvlcpQPnnAK4Na8c57rFkyOH6tqxG5wm3QDhYqJgId8MMcL6ubvOY9wmtalSj4n3aES2QYC6CbZvhbzLvKIv7QPmVKt-WdlapcRv6UvtyIX5BcRhPq6JrP5CbqVH63s_tootFmaiPDZVcb4Bi09pm1JvZmazVFJgAM8YUAdd3Awb34P3y8oo3R-C7nA';
$env:ONEMAP_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxNzE4OCwiZm9yZXZlciI6ZmFsc2UsImlzcyI6Ik9uZU1hcCIsImlhdCI6MTc4MjkxNjM4NCwibmJmIjoxNzgyOTE2Mzg0LCJleHAiOjE3ODMxNzU1ODQsImp0aSI6IjljNGM0ZjcxLTNhMjgtNGVlZi04ZTYzLTQ2MzE1OTIxNDk3MSJ9.28Rqjzttiv2aICz5TmV0G8MoD2MZs0AGilNKNXQNp9VbtG548t71p4rzlu74m2Lspb4LPFFFCj_icFCfTL1KDmijM9wUok19-dg_dE1PWPBo7_MxD41nMn4V34rusbiFom-4YM6uwyZTvf5mhYzgOc3_uP5RvlcpQPnnAK4Na8c57rFkyOH6tqxG5wm3QDhYqJgId8MMcL6ubvOY9wmtalSj4n3aES2QYC6CbZvhbzLvKIv7QPmVKt-WdlapcRv6UvtyIX5BcRhPq6JrP5CbqVH63s_tootFmaiPDZVcb4Bi09pm1JvZmazVFJgAM8YUAdd3Awb34P3y8oo3R-C7nA"


streamlit run dashboard/app_v2.py --server.port 8502