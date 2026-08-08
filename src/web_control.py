#!/usr/bin/env python3
"""
Web-based Tank Control Interface
Provides real-time control and camera streaming for the robot tank
"""

import sys
import io
import time
import signal
import threading
from pathlib import Path
from flask import Flask, render_template, Response, jsonify, request
from flask_cors import CORS

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from motor_control import TankController
    from picamera2 import Picamera2
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running on a Raspberry Pi with required libraries")
    sys.exit(1)

app = Flask(__name__, template_folder='../templates')
CORS(app)

# Global tank controller
tank = None
camera = None
camera_lock = threading.Lock()
tank_lock = threading.Lock()

# Tank state
tank_state = {
    'speed': 50,
    'camera_angle': 0,
    'autonomous_mode': False,
    'last_command': 'stop',
    'status': 'ready'
}


def init_camera():
    """Initialize camera"""
    global camera
    try:
        camera = Picamera2()
        config = camera.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        camera.configure(config)
        camera.start()
        time.sleep(2)
        print("✅ Camera initialized")
        return True
    except Exception as e:
        print(f"⚠️  Camera initialization failed: {e}")
        camera = None
        return False


def init_tank():
    """Initialize tank controller"""
    global tank
    try:
        # Resolve config relative to this file so it works from any CWD
        config_dir = str(Path(__file__).resolve().parent.parent / "config")
        tank = TankController(config_dir=config_dir)
        print("✅ Tank controller initialized")
        return True
    except Exception as e:
        print(f"❌ Tank initialization failed: {e}")
        return False


def generate_camera_feed():
    """Generate camera feed for streaming"""
    global camera
    while True:
        if camera is None:
            # Send placeholder image if camera not available
            yield (b'--frame\r\n'
                   b'Content-Type: text/plain\r\n\r\n'
                   b'Camera not available\r\n')
            time.sleep(1)
            continue

        try:
            with camera_lock:
                stream = io.BytesIO()
                camera.capture_file(stream, format='jpeg')
                stream.seek(0)
                frame = stream.read()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        except Exception as e:
            print(f"Camera error: {e}")
            time.sleep(0.1)


@app.route('/')
def index():
    """Main control interface"""
    return render_template('control.html')


@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(
        generate_camera_feed(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get tank status"""
    return jsonify(tank_state)


@app.route('/api/control', methods=['POST'])
def control():
    """Handle movement commands"""
    global tank_state

    if tank is None:
        return jsonify({'error': 'Tank not initialized'}), 500

    data = request.json
    command = data.get('command')
    speed = data.get('speed', tank_state['speed'])

    try:
        with tank_lock:
            if command == 'forward':
                tank.move_forward(speed=speed)
                tank_state['last_command'] = 'forward'
            elif command == 'backward':
                tank.move_backward(speed=speed)
                tank_state['last_command'] = 'backward'
            elif command == 'left':
                tank.turn_left(speed=speed)
                tank_state['last_command'] = 'left'
            elif command == 'right':
                tank.turn_right(speed=speed)
                tank_state['last_command'] = 'right'
            elif command == 'stop':
                tank.stop_all()
                tank_state['last_command'] = 'stop'
            else:
                return jsonify({'error': 'Unknown command'}), 400

        return jsonify({'status': 'success', 'command': command})
    except Exception as e:
        print(f"Control error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/camera', methods=['POST'])
def camera_control():
    """Handle camera gimbal commands"""
    global tank_state

    if tank is None:
        return jsonify({'error': 'Tank not initialized'}), 500

    data = request.json
    command = data.get('command')

    try:
        with tank_lock:
            if command == 'pan_left':
                tank.pan_camera(-15)
                tank_state['camera_angle'] -= 15
            elif command == 'pan_right':
                tank.pan_camera(15)
                tank_state['camera_angle'] += 15
            elif command == 'center':
                # Return to center
                tank.pan_camera(-tank_state['camera_angle'])
                tank_state['camera_angle'] = 0
            else:
                return jsonify({'error': 'Unknown camera command'}), 400

        return jsonify({
            'status': 'success',
            'angle': tank_state['camera_angle']
        })
    except Exception as e:
        print(f"Camera control error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/speed', methods=['POST'])
def set_speed():
    """Set movement speed"""
    global tank_state

    data = request.json
    speed = data.get('speed', 50)

    # Clamp speed between 0 and 100
    speed = max(0, min(100, speed))
    tank_state['speed'] = speed

    return jsonify({'status': 'success', 'speed': speed})


@app.route('/api/autonomous', methods=['POST'])
def toggle_autonomous():
    """Toggle autonomous mode"""
    global tank_state

    data = request.json
    enabled = data.get('enabled', False)

    tank_state['autonomous_mode'] = enabled

    if enabled:
        print("🤖 Autonomous mode enabled")
        # TODO: Start autonomous navigation agent
    else:
        print("🎮 Manual control mode")
        if tank:
            with tank_lock:
                tank.stop_all()

    return jsonify({
        'status': 'success',
        'autonomous_mode': tank_state['autonomous_mode']
    })


@app.route('/api/emergency_stop', methods=['POST'])
def emergency_stop():
    """Emergency stop all motors"""
    global tank_state

    if tank:
        with tank_lock:
            tank.stop_all()

    tank_state['last_command'] = 'emergency_stop'
    tank_state['autonomous_mode'] = False

    print("🛑 EMERGENCY STOP activated")

    return jsonify({'status': 'stopped'})


def cleanup():
    """Cleanup resources"""
    global tank, camera

    print("\n🧹 Cleaning up...")

    if tank:
        tank.cleanup()

    if camera:
        camera.stop()

    print("👋 Shutdown complete")


def _signal_handler(signum, frame):
    """Handle SIGTERM/SIGINT by routing through graceful shutdown so
    motors are stopped (prevents wheels staying powered on service restart)"""
    raise KeyboardInterrupt()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    print("🤖 Tank Robot Web Control")
    print("=" * 50)

    # Initialize hardware
    init_camera()
    if not init_tank():
        print("⚠️  Warning: Tank controller initialization failed")
        print("   Control interface will start but may not function")

    try:
        print("\n🌐 Starting web server...")
        print("   Access control panel at: http://<pi-ip>:8080")
        print("   Press Ctrl+C to stop\n")

        app.run(
            host='0.0.0.0',
            port=8080,
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    finally:
        cleanup()
