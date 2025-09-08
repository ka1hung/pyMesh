# Meshtastic HTTP Server

This project provides a simple HTTP REST API server to send messages through a Meshtastic device connected via a serial (COM) port.

## Features

- **REST API**: Send messages via a simple `POST` request.
- **Auto-Detection**: Automatically finds the Meshtastic device's COM port.
- **Configurable**: Easily configure the server and device settings via `config.json`.
- **Queue-based Messaging**: Handles message sending in the background to prevent blocking API requests.

## Prerequisites

- Python 3.x
- A Meshtastic device

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd <repository-folder>
    ```

2.  **Create a virtual environment and activate it:**
    ```bash
    # For Windows
    python -m venv venv
    .\venv\Scripts\activate

    # For macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the required packages:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

Before running the server, you can modify the `config.json` file:

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false
  },
  "meshtastic": {
    "com_port": "auto",
    "timeout": 10
  },
  "logging": {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": "meshtastic_server.log"
  }
}
```

- `server.host`: The IP address the server will listen on (`0.0.0.0` for all network interfaces).
- `server.port`: The port the server will run on.
- `meshtastic.com_port`: Set to `"auto"` to automatically find the device, or specify the port directly (e.g., `"COM3"` on Windows, `"/dev/ttyUSB0"` on Linux).

## Usage

Run the following command to start the server:

```bash
python main.py
```

The server will start and attempt to connect to the Meshtastic device.

## API Endpoint

### Send Message

- **URL**: `/send_message`
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`
- **Body**:

  To send a broadcast message:
  ```json
  {
    "message": "Hello everyone!"
  }
  ```

  To send a direct message:
  ```json
  {
    "message": "Hello node!",
    "destination": "!b4xx8a9c"
  }
  ```

  To send a channel message:
  ```json
  {
    "message": "Hello node!",
    "channelIndex": 1
  }
  ```

- **Success Response (200)**:
  ```json
  {
    "success": true,
    "message": "Message sent successfully",
    "timestamp": "2023-10-27T10:00:00.123456",
    "destination": "!b4xx8a9c"
  }
  ```

- **Error Response (500)**:
  ```json
  {
    "success": false,
    "error": "Not connected"
  }
  ```

## Build binnary file
  ```
  pip install PyInstaller
  pyinstaller --onefile --name "pyMesh" main.py
  ```