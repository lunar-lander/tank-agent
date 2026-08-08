# Robot Tank Project - Claude Documentation

## Project Overview
**Agentic AI controlled robotic tank project** - 4-wheel drive robot tank with camera gimbal, built on Raspberry Pi with L298N motor drivers. Designed for autonomous operation with AI decision-making capabilities.

## Current State (2026-08-08)

**Hardware blocker:** The L298N modules are NOT powered — no 12V supply is connected to the L298N motor-power terminals yet. All drive logic is verified (see below), but the wheels will NOT spin until 7-12V is connected to both L298N VM/12V terminals and GND is shared with the Pi.

**Software is verified working end-to-end:**
- All motor control signals confirmed at the physical GPIO pins (ENA/ENB PWM ~80% duty + IN1-4 direction correct on all 4 motors, both L298Ns).
- Web control live at `http://192.168.0.76:8080` (movement, gimbal, speed, emergency stop, live video).
- Camera streaming confirmed (real JPEG frames over `/video_feed`).
- systemd: `tank-control.service` ACTIVE; `camera-stream.service` DISABLED (web_control serves the video instead); `tank-autonomous.service` installed but NOT enabled (needs the camera, conflicts with tank-control).

**Deployment environment (Raspberry Pi 5, kernel 6.12+rpt-rpi-2712, user `ixaxaar`):**
- Code lives at `/home/ixaxaar/tank-agent` (NOT `/opt/tank-agent` as the old Makefile assumed).
- Services run on **system** python3 (`/usr/bin/python3`). System deps installed: `python3-lgpio`, `python3-yaml`, `python3-opencv`, `picamera2`, `flask`, `flask-cors`.
- The repo `venv/` is **NOT usable** for picamera2 (missing `libcamera`, a system package) — don't use it for web_control/autonomous. It works for pure GPIO/motor scripts.
- The installed `lgpio` (v0.2.2.0, joan's) takes PWM duty in **% (0-100)**.

**Root-cause bugs fixed (2026-08-08) in `src/gpio_compat.py`:**
1. **PWM duty scale** — lgpio `tx_pwm` duty is **% (0-100)**, not 0-1,000,000. Old code multiplied by 10,000, so every non-zero speed was rejected (`bad PWM dutycycle`) and motors never received a drive signal.
2. **Chip reopened per controller** — `GPIO.setmode()` opened a new gpiochip on every call (left controller, right controller, gimbal), claiming pins on different handles; writes via the stale class handle failed with `GPIO busy`. Fix: open the chip once.
3. **Cleanup fallthrough** — after `GPIO.cleanup()` closed the chip, `GPIO.output()` fell through to an uninitialized RPi.GPIO and raised. Fix: no-op when the lgpio handle is gone.

**Other fixes (same day):**
- `src/web_control.py`: handles **SIGTERM → graceful cleanup** (verified: service restart releases all drive pins, motors can't stay powered); config dir resolved relative to the file (CWD-independent); `init_tank()` so it works from anywhere.
- `src/ai_vision.py`: added missing `import sys`.
- `init/*.service`: updated for real paths (`/home/ixaxaar/tank-agent`, `User=ixaxaar`).
- `Makefile`: `INSTALL_DIR=/home/ixaxaar/tank-agent`, `USER=ixaxaar`.

**Next step:** Connect 7-12V to both L298N power terminals + share GND with the Pi, then re-test movement via the web UI.

## Hardware Configuration

### Motors & Drivers
- **Left Wheels**: L298N driver controlling 2 DC motors (front + rear)
  - Front Left: GPIO 12 (PWM), 10 (forward), 22 (reverse)  
  - Rear Left: GPIO 2 (speed), 27 (forward), 17 (reverse)

- **Right Wheels**: L298N driver controlling 2 DC motors (front + rear)  
  - Front Right: GPIO 13 (PWM), 26 (forward), 21 (reverse)
  - Rear Right: GPIO 6 (speed), 20 (forward), 16 (reverse)

- **Camera Gimbal**: Stepper motor (4-phase)
  - GPIO pins: 14, 15, 18, 23
  - 200 steps/revolution, 360� pan range

### Camera
- Pi Camera v2/v3 compatible
- 1920x1080 @ 10fps default
- Stream server on port 5000 (Flask-based)

## Software Architecture

### Core Modules
- **`src/motor_control.py`**: Main motor control library
  - `L298NMotorController`: Controls L298N drivers (single/dual motor)
  - `StepperMotor`: 4-phase stepper motor control  
  - `TankController`: High-level tank movement & integration

### Configuration Files  
- **`config/motors.yml`**: Motor pin assignments & parameters
- **`config/application.yml`**: Movement patterns & camera config
- **`config/util.yml`**: Wheel position enums

### Testing Utilities
- **`utils/test_mobility.py`**: Comprehensive hardware test suite
- **`utils/quick_test.py`**: Quick individual component testing
- **`utils/camera_stream.py`**: Camera streaming server

## Key Commands

### Testing Hardware
```bash
# Full hardware test suite
python3 utils/test_mobility.py

# Quick individual tests
python3 utils/quick_test.py

# Camera stream test
python3 utils/camera_stream.py
```

### Installation (deployed manually on the Pi)
```bash
# Files live at /home/ixaxaar/tank-agent; services installed via:
sudo cp init/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tank-control.service
```

## Development Notes

### Motor Control Design
- L298N controllers support dual motors per IC  
- PWM speed control (0-100%)
- Tank steering: opposite wheel directions for turns
- Emergency stop functionality in all test scripts

### GPIO Safety
- Always call `cleanup()` in try/finally blocks
- GPIO.setwarnings(False) to avoid conflicts
- Use BCM pin numbering consistently

### Configuration Structure
- YAML-based modular config system
- Separate concerns: hardware pins, movement patterns, utilities
- Easy to modify without code changes

## Known Issues & Fixes
- Fixed typo: `moror_a` → `motor_a` in motors.yml:30
- Path fix: moved motor_control.py from lib/ to src/
- Import paths use relative src/ directory
- Fixed lgpio PWM duty scale (%), GPIO chip reopen (`GPIO busy`), and cleanup fallthrough — see Current State above

## Future Enhancements
- [x] Remote control via web interface (live on :8080)
- [x] Autonomous navigation code (not enabled — needs camera)
- [ ] Sensor integration (ultrasonic, IMU)
- [ ] Video recording capabilities
- [ ] Battery monitoring
- [ ] LED status indicators

## Dependencies
```bash
pip install -r requirements.txt
```

## Test Results Tracking
The test suite provides detailed pass/fail reporting for:
- Individual motor functionality (4 motors)
- Movement patterns (forward, backward, left turn, right turn)
- Gimbal functionality (pan left/right/center)
- System integration (complex movement sequences)

## Troubleshooting

### Motor Not Moving
1. **Check L298N power** — the VM/12V terminals MUST have 7-12V connected and GND shared with the Pi; no motor supply = no movement (motors will be silent while GPIO signals look correct).
2. Check wiring connections to L298N
3. Verify power supply to motors
4. Test individual GPIO pins with multimeter
5. Check motor driver enable pins (ENA/ENB)

### GPIO Permission Issues  
```bash
sudo usermod -a -G gpio $USER
# Logout/login or reboot
```

### Camera Issues
```bash
# Enable camera interface
sudo raspi-config
# Interface Options > Camera > Enable
```