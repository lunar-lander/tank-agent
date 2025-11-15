#!/usr/bin/env python3
"""
Autonomous Navigation Agent for Tank Robot
Implements AI-driven navigation, obstacle avoidance, and path planning
"""

import sys
import time
import threading
import argparse
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from collections import deque

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from motor_control import TankController
    from ai_vision import VisionProcessor, VisionFrame
    from picamera2 import Picamera2
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running on a Raspberry Pi with required libraries")
    sys.exit(1)


class NavigationMode(Enum):
    """Navigation modes"""
    IDLE = 0
    EXPLORE = 1  # Random exploration
    WAYPOINT = 2  # Navigate to specific waypoint
    RETURN_HOME = 3  # Return to starting position
    AVOID_OBSTACLE = 4  # Active obstacle avoidance


class AgentState(Enum):
    """Agent operational states"""
    STOPPED = 0
    MOVING_FORWARD = 1
    TURNING_LEFT = 2
    TURNING_RIGHT = 3
    REVERSING = 4
    SCANNING = 5


@dataclass
class NavigationStats:
    """Statistics for navigation session"""
    start_time: float
    distance_traveled: float
    obstacles_avoided: int
    turns_made: int
    current_mode: NavigationMode
    current_state: AgentState


class AutonomousAgent:
    """AI agent for autonomous tank navigation"""

    def __init__(self, tank: TankController, vision: VisionProcessor,
                 camera: Picamera2, mode: NavigationMode = NavigationMode.EXPLORE):
        """
        Initialize autonomous agent

        Args:
            tank: Tank controller instance
            vision: Vision processor instance
            camera: Camera instance
            mode: Initial navigation mode
        """
        self.tank = tank
        self.vision = vision
        self.camera = camera
        self.mode = mode

        # Agent state
        self.state = AgentState.STOPPED
        self.running = False
        self.paused = False

        # Navigation parameters
        self.default_speed = 40
        self.turn_speed = 35
        self.reverse_speed = 35
        self.scan_speed = 30

        # Timing parameters
        self.forward_duration = 1.0  # Time to move forward before checking
        self.turn_duration = 0.5  # Time to turn (adjust based on testing)
        self.reverse_duration = 1.0  # Time to reverse when stuck
        self.scan_duration = 0.3  # Time for each scan step

        # Decision making
        self.stuck_threshold = 3  # Number of blocked attempts before reversing
        self.stuck_counter = 0
        self.last_successful_direction = None

        # Memory for path planning
        self.visited_positions = deque(maxlen=100)
        self.obstacle_memory = deque(maxlen=50)

        # Statistics
        self.stats = NavigationStats(
            start_time=time.time(),
            distance_traveled=0.0,
            obstacles_avoided=0,
            turns_made=0,
            current_mode=mode,
            current_state=AgentState.STOPPED
        )

        # Threading
        self.lock = threading.Lock()
        self.navigation_thread = None

        print(f"✅ Autonomous agent initialized in {mode.name} mode")

    def start(self):
        """Start autonomous navigation"""
        if self.running:
            print("⚠️  Agent already running")
            return

        self.running = True
        self.paused = False
        self.stats.start_time = time.time()

        # Start navigation thread
        self.navigation_thread = threading.Thread(target=self._navigation_loop, daemon=True)
        self.navigation_thread.start()

        print(f"🚀 Autonomous navigation started in {self.mode.name} mode")

    def stop(self):
        """Stop autonomous navigation"""
        self.running = False
        self.paused = False

        if self.navigation_thread:
            self.navigation_thread.join(timeout=2.0)

        with self.lock:
            self.tank.stop_all()
            self.state = AgentState.STOPPED

        print("🛑 Autonomous navigation stopped")

    def pause(self):
        """Pause autonomous navigation"""
        self.paused = True
        with self.lock:
            self.tank.stop_all()
        print("⏸️  Autonomous navigation paused")

    def resume(self):
        """Resume autonomous navigation"""
        self.paused = False
        print("▶️  Autonomous navigation resumed")

    def set_mode(self, mode: NavigationMode):
        """Change navigation mode"""
        self.mode = mode
        self.stats.current_mode = mode
        print(f"📍 Navigation mode changed to: {mode.name}")

    def _navigation_loop(self):
        """Main navigation loop (runs in separate thread)"""
        print("🔄 Navigation loop started")

        while self.running:
            if self.paused:
                time.sleep(0.1)
                continue

            try:
                # Capture frame
                frame = self.camera.capture_array()

                # Convert from RGB to BGR for OpenCV
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                # Process vision
                vision_result = self.vision.process_frame(frame_bgr, annotate=False)

                # Make decision based on current mode
                if self.mode == NavigationMode.EXPLORE:
                    self._explore_mode(vision_result)
                elif self.mode == NavigationMode.WAYPOINT:
                    self._waypoint_mode(vision_result)
                elif self.mode == NavigationMode.RETURN_HOME:
                    self._return_home_mode(vision_result)
                elif self.mode == NavigationMode.AVOID_OBSTACLE:
                    self._avoid_obstacle_mode(vision_result)

                # Small delay to prevent CPU overload
                time.sleep(0.05)

            except Exception as e:
                print(f"❌ Navigation error: {e}")
                with self.lock:
                    self.tank.stop_all()
                time.sleep(0.5)

        # Cleanup on exit
        with self.lock:
            self.tank.stop_all()
        print("🔄 Navigation loop ended")

    def _explore_mode(self, vision: VisionFrame):
        """
        Exploration mode - randomly explore environment while avoiding obstacles

        Args:
            vision: Current vision frame with obstacle detection
        """
        with self.lock:
            # Check if path is clear
            if vision.safe_to_move_forward and self.state != AgentState.SCANNING:
                # Move forward
                if self.state != AgentState.MOVING_FORWARD:
                    self.tank.move_forward(self.default_speed)
                    self.state = AgentState.MOVING_FORWARD
                    self.stuck_counter = 0
                    self.last_successful_direction = 'forward'

            else:
                # Obstacle detected, need to navigate around it
                self.stats.obstacles_avoided += 1
                self.stuck_counter += 1

                # If stuck too many times, reverse
                if self.stuck_counter >= self.stuck_threshold:
                    if self.state != AgentState.REVERSING:
                        print("🔙 Stuck! Reversing...")
                        self.tank.move_backward(self.reverse_speed, self.reverse_duration)
                        self.state = AgentState.REVERSING
                        self.stuck_counter = 0
                        time.sleep(self.reverse_duration)

                # Decide which way to turn
                if vision.safe_to_turn_left and not vision.safe_to_turn_right:
                    # Turn left
                    if self.state != AgentState.TURNING_LEFT:
                        print("↰ Turning left")
                        self.tank.turn_left(self.turn_speed, self.turn_duration)
                        self.state = AgentState.TURNING_LEFT
                        self.stats.turns_made += 1
                        time.sleep(self.turn_duration)

                elif vision.safe_to_turn_right and not vision.safe_to_turn_left:
                    # Turn right
                    if self.state != AgentState.TURNING_RIGHT:
                        print("↱ Turning right")
                        self.tank.turn_right(self.turn_speed, self.turn_duration)
                        self.state = AgentState.TURNING_RIGHT
                        self.stats.turns_made += 1
                        time.sleep(self.turn_duration)

                elif vision.safe_to_turn_left and vision.safe_to_turn_right:
                    # Both directions safe, choose based on exploration strategy
                    # Prefer direction opposite to last turn to explore more area
                    if self.last_successful_direction == 'left':
                        direction = 'right'
                    else:
                        direction = 'left'

                    if direction == 'left':
                        print("↰ Turning left (exploration)")
                        self.tank.turn_left(self.turn_speed, self.turn_duration)
                        self.state = AgentState.TURNING_LEFT
                    else:
                        print("↱ Turning right (exploration)")
                        self.tank.turn_right(self.turn_speed, self.turn_duration)
                        self.state = AgentState.TURNING_RIGHT

                    self.stats.turns_made += 1
                    self.last_successful_direction = direction
                    time.sleep(self.turn_duration)

                else:
                    # All directions blocked, perform scan
                    print("🔍 All paths blocked, scanning...")
                    self._perform_scan()

    def _avoid_obstacle_mode(self, vision: VisionFrame):
        """
        Active obstacle avoidance mode - similar to explore but more conservative

        Args:
            vision: Current vision frame
        """
        # Similar to explore mode but with more cautious behavior
        self._explore_mode(vision)

    def _waypoint_mode(self, vision: VisionFrame):
        """
        Waypoint navigation mode - navigate to specific coordinates

        Args:
            vision: Current vision frame
        """
        # TODO: Implement waypoint navigation with dead reckoning or visual odometry
        # For now, fall back to exploration
        print("⚠️  Waypoint mode not fully implemented, using exploration")
        self._explore_mode(vision)

    def _return_home_mode(self, vision: VisionFrame):
        """
        Return to home mode - navigate back to starting position

        Args:
            vision: Current vision frame
        """
        # TODO: Implement path reversal or landmark-based navigation
        # For now, fall back to exploration
        print("⚠️  Return home mode not fully implemented, using exploration")
        self._explore_mode(vision)

    def _perform_scan(self):
        """
        Perform 360-degree scan to find clear path

        Returns best direction or None if all blocked
        """
        self.state = AgentState.SCANNING

        # Pan camera to look around
        scan_angles = [-45, -30, 0, 30, 45]
        best_direction = None
        max_clearance = 0

        for angle in scan_angles:
            # Pan camera
            if angle != 0:
                self.tank.pan_camera(angle)
                time.sleep(0.3)

            # Capture and analyze
            frame = self.camera.capture_array()
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            vision = self.vision.process_frame(frame_bgr, annotate=False)

            # Count clearance (fewer obstacles = more clearance)
            clearance = 100 - len(vision.obstacles)

            if clearance > max_clearance:
                max_clearance = clearance
                if angle < 0:
                    best_direction = 'left'
                elif angle > 0:
                    best_direction = 'right'
                else:
                    best_direction = 'forward'

            # Reset camera angle
            if angle != 0:
                self.tank.pan_camera(-angle)

        # Execute best direction
        if best_direction == 'left':
            print("↰ Scan result: Turn left")
            self.tank.turn_left(self.turn_speed, self.turn_duration * 2)
            self.stats.turns_made += 1
        elif best_direction == 'right':
            print("↱ Scan result: Turn right")
            self.tank.turn_right(self.turn_speed, self.turn_duration * 2)
            self.stats.turns_made += 1
        else:
            # Still no clear path, reverse
            print("🔙 No clear path found, reversing")
            self.tank.move_backward(self.reverse_speed, self.reverse_duration)

        self.stuck_counter = 0

    def get_stats(self) -> NavigationStats:
        """Get current navigation statistics"""
        self.stats.current_state = self.state
        self.stats.current_mode = self.mode
        return self.stats

    def print_stats(self):
        """Print navigation statistics"""
        runtime = time.time() - self.stats.start_time
        print("\n" + "=" * 50)
        print("📊 AUTONOMOUS NAVIGATION STATISTICS")
        print("=" * 50)
        print(f"Runtime:           {runtime:.1f} seconds")
        print(f"Mode:              {self.stats.current_mode.name}")
        print(f"State:             {self.stats.current_state.name}")
        print(f"Obstacles Avoided: {self.stats.obstacles_avoided}")
        print(f"Turns Made:        {self.stats.turns_made}")
        print(f"Distance Traveled: {self.stats.distance_traveled:.2f}m (estimated)")
        print("=" * 50 + "\n")


def main():
    """Main entry point for autonomous agent"""
    parser = argparse.ArgumentParser(description='Tank Robot Autonomous Navigation')
    parser.add_argument('--mode', type=str, default='explore',
                       choices=['explore', 'waypoint', 'return_home', 'avoid'],
                       help='Navigation mode')
    parser.add_argument('--speed', type=int, default=40,
                       help='Default movement speed (20-100)')
    parser.add_argument('--duration', type=int, default=0,
                       help='Run duration in seconds (0 = infinite)')

    args = parser.parse_args()

    # Map mode string to enum
    mode_map = {
        'explore': NavigationMode.EXPLORE,
        'waypoint': NavigationMode.WAYPOINT,
        'return_home': NavigationMode.RETURN_HOME,
        'avoid': NavigationMode.AVOID_OBSTACLE
    }

    print("🤖 Tank Robot Autonomous Navigation Agent")
    print("=" * 50)

    # Initialize hardware
    print("🔧 Initializing hardware...")

    try:
        # Initialize tank
        tank = TankController()
        print("✅ Tank controller initialized")

        # Initialize camera
        camera = Picamera2()
        config = camera.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        camera.configure(config)
        camera.start()
        time.sleep(2)
        print("✅ Camera initialized")

        # Initialize vision processor
        vision = VisionProcessor(frame_width=640, frame_height=480)

        # Create autonomous agent
        agent = AutonomousAgent(
            tank=tank,
            vision=vision,
            camera=camera,
            mode=mode_map[args.mode]
        )

        # Set custom speed if specified
        if args.speed != 40:
            agent.default_speed = args.speed
            agent.turn_speed = args.speed - 5
            agent.reverse_speed = args.speed - 5

        # Start navigation
        agent.start()

        # Run for specified duration or until interrupted
        try:
            if args.duration > 0:
                print(f"⏱️  Running for {args.duration} seconds...")
                time.sleep(args.duration)
                agent.stop()
            else:
                print("⏱️  Running indefinitely. Press Ctrl+C to stop.\n")
                while True:
                    time.sleep(5)
                    agent.print_stats()

        except KeyboardInterrupt:
            print("\n⚠️  Interrupted by user")

        finally:
            agent.stop()
            agent.print_stats()
            tank.cleanup()
            camera.stop()
            print("👋 Autonomous agent shutdown complete")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
