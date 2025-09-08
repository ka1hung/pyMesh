
#!/usr/bin/env python3
"""
Meshtastic HTTP Server Application
A REST API server for sending messages through Meshtastic devices via COM port.
"""

import json
import logging
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import queue
import threading

import meshtastic
import meshtastic.serial_interface
from flask import Flask, request, jsonify
from flask.logging import create_logger
import serial.tools.list_ports


class Config:
    """Configuration management for the application"""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.default_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 5000,
                "debug": False
            },
            "meshtastic": {
                "com_port": "auto",  # "auto" for auto-detection or specific port like "COM3"
                "timeout": 10
            },
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "file": "meshtastic_server.log"
            }
        }
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        try:
            if Path(self.config_file).exists():
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                # Merge with defaults to ensure all keys exist
                return self.merge_configs(self.default_config, config)
            else:
                self.save_config(self.default_config)
                return self.default_config.copy()
        except Exception as e:
            logging.error(f"Error loading config: {e}")
            return self.default_config.copy()
    
    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving config: {e}")
    
    def merge_configs(self, default: Dict, user: Dict) -> Dict:
        """Recursively merge user config with defaults"""
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.merge_configs(result[key], value)
            else:
                result[key] = value
        return result


class MeshtasticManager:
    """Manages Meshtastic device connection and messaging"""
    
    def __init__(self, config: Config):
        self.config = config
        self.interface = None
        self.logger = logging.getLogger(__name__)
        self.connection_lock = threading.Lock()
        self._connected = False
        # 新增佇列與背景執行緒
        self.message_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._message_worker, daemon=True)
        self.worker_thread.start()

    def _message_worker(self):
        while True:
            job = self.message_queue.get()
            if not job:
                continue  # 允許 queue None 跳過
            action, data, ret_queue = job  # data 是 dict，ret_queue 用於回傳執行結果
            try:
                if action == "send":
                    result = self._send_message_core(**data)
                    ret_queue.put(result)
                else:
                    ret_queue.put({"success": False, "error": "Unknown action"})
            except Exception as e:
                ret_queue.put({"success": False, "error": str(e)})
            finally:
                self.message_queue.task_done()    
    # 內部底層發送及查詢
    def _send_message_core(self, message, destination=None, channelIndex=None):
        if not self._connected:
            if not self.connect():
                return {"success": False, "error": "Not connected"}
        with self.connection_lock:
            if destination:
                print(f"Sending to {destination}: {message}")
                pkg=self.interface.sendText(message, destinationId=destination)
                print(f"Send result: {pkg}")
            elif channelIndex:
                print(f"Sending to channel {channelIndex}: {message}")
                pkg=self.interface.sendText(message, channelIndex=channelIndex)
                print(f"Send result: {pkg}")
            else:
                self.interface.sendText(message)
            return {
                "success": True,
                "message": "Message sent successfully",
                "timestamp": datetime.now().isoformat(),
                "destination": destination or "broadcast"
            }

    def find_meshtastic_port(self) -> Optional[str]:
        """Auto-detect Meshtastic device COM port"""
        ports = serial.tools.list_ports.comports()
        meshtastic_ports = []
        
        for port in ports:
            # Check for common Meshtastic device identifiers
            if any(identifier in (port.description or "").lower() for identifier in 
                   ["ch340", "cp210", "ftdi", "usb serial", "arduino"]):
                meshtastic_ports.append(port.device)
                self.logger.info(f"Found potential Meshtastic device: {port.device} - {port.description}")
        
        if meshtastic_ports:
            return meshtastic_ports[0]  # Return first found device
        
        self.logger.warning("No Meshtastic devices found via auto-detection")
        return None
    
    def connect(self) -> bool:
        """Establish connection to Meshtastic device"""
        with self.connection_lock:
            if self._connected and self.interface:
                return True
            
            try:
                com_port = self.config.config["meshtastic"]["com_port"]
                
                if com_port == "auto":
                    com_port = self.find_meshtastic_port()
                    if not com_port:
                        raise Exception("Could not auto-detect Meshtastic device")
                
                self.logger.info(f"Connecting to Meshtastic device on {com_port}")
                
                self.interface = meshtastic.serial_interface.SerialInterface(devPath=com_port)
                
                # Wait for connection to establish
                time.sleep(2)
                
                # Test connection by getting node info
                if self.interface.myInfo:
                    self._connected = True
                    self.logger.info(f"Successfully connected to Meshtastic device: {self.interface.myInfo}")
                    return True
                else:
                    raise Exception("Failed to get device information")
                    
            except Exception as e:
                self.logger.error(f"Failed to connect to Meshtastic device: {e}")
                self._connected = False
                if self.interface:
                    try:
                        self.interface.close()
                    except:
                        pass
                    self.interface = None
                return False
    
    def disconnect(self):
        """Disconnect from Meshtastic device"""
        with self.connection_lock:
            if self.interface:
                try:
                    self.interface.close()
                    self.logger.info("Disconnected from Meshtastic device")
                except Exception as e:
                    self.logger.error(f"Error disconnecting: {e}")
                finally:
                    self.interface = None
                    self._connected = False
    
    # 對外包裝 (讓 API 層呼叫)
    def send_message(self, message: str, destination: Optional[str] = None, channelIndex: Optional[int] = None, timeout=10):
        self.connect()
        ret_q = queue.Queue()
        self.message_queue.put(("send", {"message": message, "destination": destination, "channelIndex": channelIndex}, ret_q))
        try:
            return ret_q.get(timeout=timeout)
        except queue.Empty:
            self.disconnect()
            # self.connect()  # 嘗試重新連線
            return {"success": False, "error": "Message send timed out"}

class MeshtasticServer:
    """Main application server"""
    
    def __init__(self):
        self.config = Config()
        self.setup_logging()
        self.logger = logging.getLogger(__name__)
        self.meshtastic_manager = MeshtasticManager(self.config)
        
        # Create Flask app
        self.app = Flask(__name__)
        self.app.logger = create_logger(self.app)
        self.setup_routes()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        self.logger.info("Meshtastic HTTP Server initialized")
    
    def setup_logging(self):
        """Configure logging"""
        log_config = self.config.config["logging"]
        
        logging.basicConfig(
            level=getattr(logging, log_config["level"]),
            format=log_config["format"],
            handlers=[
                logging.FileHandler(log_config["file"]),
                logging.StreamHandler(sys.stdout)
            ]
        )
    
    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/send_message', methods=['POST'])
        def send_message():
            """Send message endpoint"""
            try:
                data = request.get_json()
                
                if not data:
                    return jsonify({
                        "success": False,
                        "error": "Invalid JSON data"
                    }), 400
                
                message = data.get('message')
                if not message:
                    return jsonify({
                        "success": False,
                        "error": "Message field is required"
                    }), 400
                
                destination = data.get('destination')  # Optional
                channelIndex = data.get('channelIndex')  # Optional
                
                result = self.meshtastic_manager.send_message(message, destination,channelIndex)
                
                if result["success"]:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 500
                    
            except Exception as e:
                self.logger.error(f"Error in send_message endpoint: {e}")
                return jsonify({
                    "success": False,
                    "error": f"Internal server error: {str(e)}"
                }), 500
        
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({
                "success": False,
                "error": "Endpoint not found"
            }), 404
        
        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({
                "success": False,
                "error": "Internal server error"
            }), 500
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutdown()
        sys.exit(0)
    
    def shutdown(self):
        """Graceful shutdown"""
        self.logger.info("Shutting down Meshtastic HTTP Server...")
        # self.meshtastic_manager.disconnect()
        self.logger.info("Shutdown complete")
    
    def run(self):
        """Start the server"""
        server_config = self.config.config["server"]
        
        self.logger.info(f"Starting Meshtastic HTTP Server on {server_config['host']}:{server_config['port']}")
        
        # Try to connect to Meshtastic device on startup
        self.meshtastic_manager.connect()
        
        try:
            self.app.run(
                host=server_config["host"],
                port=server_config["port"],
                debug=server_config["debug"],
                threaded=True
            )
        except Exception as e:
            self.logger.error(f"Server error: {e}")
        finally:
            self.shutdown()


def main():
    """Main entry point"""
    print("Meshtastic HTTP Server")
    print("=====================")
    print("Starting server...")
    
    try:
        server = MeshtasticServer()
        server.run()
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
