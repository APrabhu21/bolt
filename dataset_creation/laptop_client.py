#!/usr/bin/env python3
"""
Laptop Client Script
Run this on your laptop to view the stream and capture images
"""

import cv2
import socket
import struct
import pickle
import threading
import time
import os
from datetime import datetime

class CameraClient:
    def __init__(self, go2_ip, stream_port=8888, save_port=8889):
        self.go2_ip = go2_ip
        self.stream_port = stream_port
        self.save_port = save_port
        self.stream_socket = None
        self.save_socket = None
        self.running = False
        self.current_frame = None
        self.frame_lock = threading.Lock()
        self.image_counter = 0
        
        # Create local save directory
        self.local_save_dir = "ball_dataset_local"
        if not os.path.exists(self.local_save_dir):
            os.makedirs(self.local_save_dir)
    
    def connect_to_stream(self):
        """Connect to the video stream"""
        try:
            self.stream_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.stream_socket.connect((self.go2_ip, self.stream_port))
            print(f"Connected to stream at {self.go2_ip}:{self.stream_port}")
            return True
        except Exception as e:
            print(f"Failed to connect to stream: {e}")
            return False
    
    def connect_to_save_server(self):
        """Connect to the save command server"""
        try:
            self.save_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.save_socket.connect((self.go2_ip, self.save_port))
            print(f"Connected to save server at {self.go2_ip}:{self.save_port}")
            return True
        except Exception as e:
            print(f"Failed to connect to save server: {e}")
            return False
    
    def receive_frames(self):
        """Receive and decode video frames"""
        try:
            while self.running:
                # Receive frame size (4 bytes)
                size_data = b""
                while len(size_data) < 4:
                    chunk = self.stream_socket.recv(4 - len(size_data))
                    if not chunk:
                        raise ConnectionError("Connection lost")
                    size_data += chunk
                
                frame_size = struct.unpack("!L", size_data)[0]
                
                # Receive frame data
                frame_data = b""
                while len(frame_data) < frame_size:
                    chunk = self.stream_socket.recv(min(4096, frame_size - len(frame_data)))
                    if not chunk:
                        raise ConnectionError("Connection lost")
                    frame_data += chunk
                
                # Deserialize and decode frame
                frame_encoded = pickle.loads(frame_data)
                frame = cv2.imdecode(frame_encoded, cv2.IMREAD_COLOR)
                
                # Update current frame thread-safely
                with self.frame_lock:
                    self.current_frame = frame
                
        except Exception as e:
            if self.running:
                print(f"Frame receiving error: {e}")
    
    def save_image_remote(self, filename=None):
        """Send command to save image on GO2"""
        try:
            if filename:
                command = f"SAVE:{filename}"
            else:
                command = "SAVE"
            
            self.save_socket.send(command.encode('utf-8'))
            response = self.save_socket.recv(1024).decode('utf-8')
            
            if response.startswith("SAVED:"):
                filepath = response.split(":", 1)[1]
                print(f"✓ Image saved on GO2: {filepath}")
                return True
            else:
                print(f"✗ Failed to save on GO2: {response}")
                return False
                
        except Exception as e:
            print(f"Error saving remote image: {e}")
            return False
    
    def save_image_local(self, filename=None):
        """Save current frame locally on laptop"""
        try:
            with self.frame_lock:
                if self.current_frame is None:
                    print("✗ No frame available to save")
                    return False
                
                frame = self.current_frame.copy()
            
            if filename is None:
                self.image_counter += 1
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = f"ball_dataset_{self.image_counter:04d}_{timestamp}.jpg"
            
            filepath = os.path.join(self.local_save_dir, filename)
            success = cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            if success:
                print(f"✓ Image saved locally: {filepath}")
                return True
            else:
                print(f"✗ Failed to save image: {filepath}")
                return False
            
        except Exception as e:
            print(f"Error saving local image: {e}")
            return False
    
    def display_instructions(self):
        """Display control instructions"""
        instructions = """
=== BALL DETECTION DATASET CAPTURE ===
Controls:
- 's' or SPACE: Save image on GO2 (remote)
- 'l': Save image locally on laptop
- 'b': Save image both remote and local
- 'q' or ESC: Quit
- 'h': Show this help again

Tip: Position the ball in different locations, lighting conditions,
and angles to create a diverse dataset!
        """
        print(instructions)
    
    def start(self):
        """Start the camera client"""
        try:
            # Connect to servers
            if not self.connect_to_stream():
                return
            
            if not self.connect_to_save_server():
                return
            
            self.running = True
            
            # Start frame receiving thread
            receive_thread = threading.Thread(target=self.receive_frames)
            receive_thread.daemon = True
            receive_thread.start()
            
            # Wait for first frame
            print("Waiting for video stream...")
            while self.current_frame is None and self.running:
                time.sleep(0.1)
            
            self.display_instructions()
            
            # Main display loop
            while self.running:
                with self.frame_lock:
                    if self.current_frame is not None:
                        # Add overlay information
                        display_frame = self.current_frame.copy()
                        
                        # Add text overlay
                        cv2.putText(display_frame, f"Images saved: {self.image_counter}", 
                                  (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        cv2.putText(display_frame, "Press 's' to save, 'q' to quit", 
                                  (10, display_frame.shape[0] - 10), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                        
                        cv2.imshow('GO2 Camera Stream - Ball Detection Dataset', display_frame)
                
                # Handle keyboard input
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q') or key == 27:  # 'q' or ESC
                    break
                elif key == ord('s') or key == ord(' '):  # 's' or SPACE - save remote
                    if self.save_image_remote():
                        self.image_counter += 1
                elif key == ord('l'):  # 'l' - save local
                    if self.save_image_local():
                        print(f"📁 Total images in dataset: {self.image_counter}")
                elif key == ord('b'):  # 'b' - save both
                    self.image_counter += 1
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                    filename = f"ball_dataset_{self.image_counter:04d}_{timestamp}.jpg"
                    
                    remote_success = self.save_image_remote(filename)
                    local_success = self.save_image_local(filename)
                    
                    if remote_success or local_success:
                        self.image_counter += 1
                elif key == ord('h'):  # 'h' - help
                    self.display_instructions()
        
        except KeyboardInterrupt:
            print("\nShutting down...")
        except Exception as e:
            print(f"Client error: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the camera client"""
        self.running = False
        
        cv2.destroyAllWindows()
        
        if self.stream_socket:
            self.stream_socket.close()
        
        if self.save_socket:
            self.save_socket.close()
        
        print(f"Camera client stopped. Total images captured: {self.image_counter}")
        print(f"Local images saved to: {os.path.abspath(self.local_save_dir)}")

if __name__ == "__main__":
    # Replace with your GO2's IP address
    GO2_IP = "192.168.123.18"  # Your GO2's actual IP
    
    print(f"Connecting to GO2 at {GO2_IP}")
    print("Make sure the camera server is running on the GO2!")
    
    client = CameraClient(GO2_IP)
    client.start()
