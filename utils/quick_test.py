#!/usr/bin/env python3
"""Quick Tank Component Tester - Individual component testing utility"""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from motor_control import TankController, L298NMotorController, StepperMotor
    from gpio_compat import GPIO
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

def quick_motor_test():
    """Quick individual motor test"""
    print("Quick Motor Test - Testing each wheel individually")
    tank = TankController()
    
    try:
        motors = [
            ("Front Left", lambda: tank.left_controller.motor_a_forward(40)),
            ("Rear Left", lambda: tank.left_controller.motor_b_forward(40)),
            ("Front Right", lambda: tank.right_controller.motor_a_forward(40)), 
            ("Rear Right", lambda: tank.right_controller.motor_b_forward(40)),
        ]
        
        for name, motor_func in motors:
            input(f"Press Enter to test {name} motor...")
            motor_func()
            input("Press Enter to stop...")
            tank.stop_all()
            
    finally:
        tank.cleanup()

def quick_movement_test():
    """Quick movement pattern test"""
    print("Quick Movement Test")
    tank = TankController()
    
    try:
        movements = [
            ("Forward", lambda: tank.move_forward(50, 1)),
            ("Backward", lambda: tank.move_backward(50, 1)),
            ("Left Turn", lambda: tank.turn_left(50, 0.5)),
            ("Right Turn", lambda: tank.turn_right(50, 0.5)),
        ]
        
        for name, move_func in movements:
            input(f"Press Enter for {name}...")
            move_func()
            
    finally:
        tank.cleanup()

def quick_gimbal_test():
    """Quick gimbal test"""
    print("Quick Gimbal Test")
    tank = TankController()
    
    try:
        input("Press Enter to pan gimbal right 45°...")
        tank.pan_camera(45)
        input("Press Enter to pan gimbal left 90°...")
        tank.pan_camera(-90)
        input("Press Enter to return to center...")
        tank.pan_camera(45)
    finally:
        tank.cleanup()

if __name__ == "__main__":
    tests = {
        "1": ("Individual Motors", quick_motor_test),
        "2": ("Movement Patterns", quick_movement_test),
        "3": ("Camera Gimbal", quick_gimbal_test),
    }
    
    print("Quick Tank Component Tester")
    print("=" * 30)
    for key, (name, _) in tests.items():
        print(f"{key}. {name}")
    
    choice = input("\nSelect test (1-3): ").strip()
    
    if choice in tests:
        _, test_func = tests[choice]
        test_func()
    else:
        print("Invalid choice")