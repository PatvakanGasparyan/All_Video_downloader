Markdown# Video Downloader + FastAPI Web Panel + MySQL

A lightweight, efficient system for downloading videos from various web services (via `yt-dlp`), tracking metadata in MySQL, and managing downloads through a clean web dashboard.

---

## 🏗️ Architecture Overview

The system follows a decoupled architecture, separating the web interface, the backend logic, and the persistent storage layer.



```text
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   FastAPI    │     │   Public     │     │    MySQL     │
│  (Python)    │────>│   Web Panel  │────>│   Database   │
│  :8000       │     │  (HTML/JS)   │     │   :3306      │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │
       └────────────────────┴────────────────────┘
               yt-dlp / Local Storage
⚙️ Code Architecture (Logic Flow)To understand how data flows through the application:server.py (Controller): Handles incoming HTTP requests, orchestrates the download process, and manages database communication.downloader.py (Integration Layer): Wraps yt-dlp commands using asyncio subprocesses to prevent blocking the main event loop.db.py (Data Access Object): Manages the connection pool (aiomysql) to ensure high-performance concurrent database operations.public/ (Client Side): A vanilla JavaScript implementation that communicates with the REST API.Execution Flow:PlaintextUser Action (Click Download)
      │
      ▼
HTTP POST /download ──> server.py (Validation)
                            │
                            ├──────────> downloader.py (yt-dlp subprocess)
                            │               │
                            │               ▼ (Return Metadata)
                            ├──────────> db.py (INSERT record)
                            │
      ▲                     ▼
Response (success: true) <── server.py (JSON response)
🚀 Key FeaturesUniversal Downloader: Seamless integration with yt-dlp supporting YouTube, Vimeo, and direct MP4 streams.Modern Web Dashboard: A responsive UI for monitoring active and completed downloads.Persistent Storage: MySQL 8.0 backend to maintain a searchable history of all processed video files.Intelligent Cleanup: Automatic file system synchronization; deleting a record from the DB triggers the deletion of the associated video file.📁 Project StructurePlaintext├── downloads/             # Local storage for downloaded media
├── public/                # Frontend assets
│   ├── app.js             # Client-side logic & API interaction
│   ├── index.html         # Main Dashboard interface
│   └── style.css          # UI styling
├── db.py                  # Database connection & CRUD operations
├── downloader.py          # yt-dlp execution wrapper
├── server.py              # FastAPI application entry point
├── requirements.txt       # Python package dependencies
└── README.md
🛠️ Tech StackLayerTechnologyBackendPython 3.10+, FastAPIDownloaderyt-dlpDatabaseMySQL 8.0, aiomysqlFrontendVanilla JS, HTML5, CSS3📋 API ReferenceRouteMethodDescription/downloadPOSTInitiate video download process/videosGETRetrieve complete download history/videos/{id}DELETERemove video metadata and physical file