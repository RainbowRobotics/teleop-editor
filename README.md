# Teleoperation Recorder & Editor


## Update 할때

### Backend

```bash
cd backend
uv sync
```

### Fronted

```bash
cd frontend
npm install
npm run build
```


## 실행

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

```bash
cd frontend
node .output/server/index.mjs
```