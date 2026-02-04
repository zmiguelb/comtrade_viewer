## Build/Compose
Inside the project folder must have these:
```
├── PROJECT_FOLDER
   ├── app.py
   ├── docker-compose.yml
   ├── Dockerfile
   └── requirements.txt
```
```shell
podman build -t comtrade-viewer:1.0 .
```

## Run the image
```shell
podman run -d --network host --name comtrade-viewer localhost/comtrade-viewer:1.0     streamlit run app.py     --server.port=8501     --server.address=0.0.0.0     --server.headless=true     --browser.gatherUsageStats=false     --server.enableCORS=false     --server.enableXsrfProtection=false
```

## Run (Careful firewall
```shell
podman run -d -p 8501:8501 --name comtrade-viewer localhost/comtrade-viewer:1.0
```