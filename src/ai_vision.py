#!/usr/bin/env python3
"""
AI Vision Module for Tank Robot
Provides obstacle detection, object recognition, and visual navigation
"""

import cv2
import numpy as np
import time
import sys
from dataclasses import dataclass
from typing import List, Tuple, Optional
from enum import Enum


class ObstacleType(Enum):
    """Types of obstacles detected"""
    UNKNOWN = 0
    WALL = 1
    OBJECT = 2
    EDGE = 3
    PERSON = 4


@dataclass
class Obstacle:
    """Represents a detected obstacle"""
    type: ObstacleType
    distance: float  # Estimated distance (0-1, where 0 is close, 1 is far)
    position: Tuple[int, int]  # (x, y) position in frame
    size: Tuple[int, int]  # (width, height) in pixels
    confidence: float  # 0-1 confidence score


@dataclass
class VisionFrame:
    """Processed vision frame with detection results"""
    timestamp: float
    obstacles: List[Obstacle]
    safe_to_move_forward: bool
    safe_to_turn_left: bool
    safe_to_turn_right: bool
    recommended_direction: Optional[str]  # 'forward', 'left', 'right', 'backward', 'stop'
    frame_annotated: Optional[np.ndarray]  # Annotated frame for display


class VisionProcessor:
    """Computer vision processor for obstacle detection and navigation"""

    def __init__(self, frame_width=640, frame_height=480):
        """
        Initialize vision processor

        Args:
            frame_width: Width of input frames
            frame_height: Height of input frames
        """
        self.frame_width = frame_width
        self.frame_height = frame_height

        # Detection parameters
        self.min_obstacle_area = 1000  # Minimum area in pixels
        self.edge_threshold_low = 50
        self.edge_threshold_high = 150
        self.distance_zones = 3  # Divide frame into near/medium/far zones

        # Safety margins
        self.safe_zone_width = frame_width // 3  # Center third
        self.safe_zone_height = frame_height // 2  # Bottom half

        # Motion detection for dynamic obstacles
        self.prev_frame_gray = None
        self.motion_threshold = 25

        # Initialize object detector (using basic contour detection)
        # For advanced detection, could use YOLO, MobileNet, etc.
        self.use_advanced_detection = False

        print("✅ Vision processor initialized")

    def process_frame(self, frame: np.ndarray, annotate=True) -> VisionFrame:
        """
        Process a camera frame and detect obstacles

        Args:
            frame: Input frame (BGR format from OpenCV/picamera2)
            annotate: Whether to create annotated frame for display

        Returns:
            VisionFrame with detection results
        """
        timestamp = time.time()

        # Convert to different color spaces
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Detect obstacles using multiple methods
        obstacles = []

        # 1. Edge detection for walls and objects
        edges_obstacles = self._detect_edges(gray)
        obstacles.extend(edges_obstacles)

        # 2. Contour detection for distinct objects
        contour_obstacles = self._detect_contours(gray)
        obstacles.extend(contour_obstacles)

        # 3. Motion detection for dynamic obstacles
        if self.prev_frame_gray is not None:
            motion_obstacles = self._detect_motion(gray, self.prev_frame_gray)
            obstacles.extend(motion_obstacles)

        self.prev_frame_gray = gray.copy()

        # 4. Floor/ground plane detection (simple version)
        # More advanced: use depth estimation or stereo vision

        # Analyze safety zones
        safety_analysis = self._analyze_safety(obstacles, frame.shape)

        # Determine recommended direction
        recommended_direction = self._recommend_direction(safety_analysis, obstacles)

        # Create annotated frame if requested
        annotated_frame = None
        if annotate:
            annotated_frame = self._annotate_frame(frame, obstacles, safety_analysis)

        return VisionFrame(
            timestamp=timestamp,
            obstacles=obstacles,
            safe_to_move_forward=safety_analysis['forward'],
            safe_to_turn_left=safety_analysis['left'],
            safe_to_turn_right=safety_analysis['right'],
            recommended_direction=recommended_direction,
            frame_annotated=annotated_frame
        )

    def _detect_edges(self, gray: np.ndarray) -> List[Obstacle]:
        """Detect obstacles using edge detection"""
        obstacles = []

        # Apply Canny edge detection
        edges = cv2.Canny(gray, self.edge_threshold_low, self.edge_threshold_high)

        # Dilate to connect nearby edges
        kernel = np.ones((5, 5), np.uint8)
        edges_dilated = cv2.dilate(edges, kernel, iterations=2)

        # Find contours in edge map
        contours, _ = cv2.findContours(edges_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_obstacle_area:
                continue

            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)

            # Estimate distance based on position and size
            # Objects lower in frame are closer
            distance = self._estimate_distance(y, h)

            obstacles.append(Obstacle(
                type=ObstacleType.WALL,
                distance=distance,
                position=(x + w // 2, y + h // 2),
                size=(w, h),
                confidence=0.7
            ))

        return obstacles

    def _detect_contours(self, gray: np.ndarray) -> List[Obstacle]:
        """Detect obstacles using contour detection"""
        obstacles = []

        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )

        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_obstacle_area:
                continue

            x, y, w, h = cv2.boundingRect(contour)

            # Filter out very large contours (likely background)
            if area > (self.frame_width * self.frame_height * 0.7):
                continue

            distance = self._estimate_distance(y, h)

            obstacles.append(Obstacle(
                type=ObstacleType.OBJECT,
                distance=distance,
                position=(x + w // 2, y + h // 2),
                size=(w, h),
                confidence=0.6
            ))

        return obstacles

    def _detect_motion(self, current_gray: np.ndarray, prev_gray: np.ndarray) -> List[Obstacle]:
        """Detect moving obstacles"""
        obstacles = []

        # Calculate frame difference
        frame_diff = cv2.absdiff(current_gray, prev_gray)

        # Threshold the difference
        _, thresh = cv2.threshold(frame_diff, self.motion_threshold, 255, cv2.THRESH_BINARY)

        # Dilate to connect regions
        kernel = np.ones((5, 5), np.uint8)
        thresh = cv2.dilate(thresh, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_obstacle_area:
                continue

            x, y, w, h = cv2.boundingRect(contour)
            distance = self._estimate_distance(y, h)

            # Moving objects get higher priority
            obstacles.append(Obstacle(
                type=ObstacleType.PERSON,  # Assume moving = person
                distance=distance,
                position=(x + w // 2, y + h // 2),
                size=(w, h),
                confidence=0.8
            ))

        return obstacles

    def _estimate_distance(self, y_position: int, height: int) -> float:
        """
        Estimate distance based on position and size in frame

        Args:
            y_position: Y position in frame (top = 0)
            height: Height of object in pixels

        Returns:
            Distance estimate (0 = very close, 1 = far)
        """
        # Objects lower in frame are closer
        position_factor = y_position / self.frame_height

        # Larger objects are closer
        size_factor = 1.0 - (height / self.frame_height)

        # Combine factors (weighted average)
        distance = (position_factor * 0.3 + size_factor * 0.7)

        return max(0.0, min(1.0, distance))

    def _analyze_safety(self, obstacles: List[Obstacle], frame_shape: Tuple) -> dict:
        """
        Analyze safety of different movement directions

        Returns:
            Dictionary with safety status for each direction
        """
        height, width = frame_shape[:2]

        # Define zones
        left_zone = width // 3
        right_zone = 2 * width // 3
        near_zone = 2 * height // 3  # Bottom third

        # Check obstacles in each zone
        forward_safe = True
        left_safe = True
        right_safe = True

        for obs in obstacles:
            x, y = obs.position

            # Check if obstacle is close
            if y > near_zone or obs.distance < 0.3:
                # Obstacle is close, check which zone
                if left_zone < x < right_zone:
                    # Center zone - blocks forward movement
                    forward_safe = False
                if x < right_zone:
                    # Left side
                    left_safe = False
                if x > left_zone:
                    # Right side
                    right_safe = False

        return {
            'forward': forward_safe,
            'left': left_safe,
            'right': right_safe
        }

    def _recommend_direction(self, safety: dict, obstacles: List[Obstacle]) -> str:
        """
        Recommend best movement direction based on safety analysis

        Args:
            safety: Safety analysis dictionary
            obstacles: List of detected obstacles

        Returns:
            Recommended direction: 'forward', 'left', 'right', 'backward', or 'stop'
        """
        # If forward is safe, go forward
        if safety['forward']:
            return 'forward'

        # If forward blocked, try turning
        if safety['left'] and not safety['right']:
            return 'left'
        elif safety['right'] and not safety['left']:
            return 'right'
        elif safety['left'] and safety['right']:
            # Both sides safe, choose randomly or based on goal
            # For now, prefer right
            return 'right'
        else:
            # All directions blocked
            return 'backward'

    def _annotate_frame(self, frame: np.ndarray, obstacles: List[Obstacle],
                       safety: dict) -> np.ndarray:
        """
        Create annotated frame with visual overlay

        Args:
            frame: Original frame
            obstacles: Detected obstacles
            safety: Safety analysis

        Returns:
            Annotated frame
        """
        annotated = frame.copy()
        height, width = frame.shape[:2]

        # Draw safety zones
        left_zone = width // 3
        right_zone = 2 * width // 3

        # Draw zone dividers
        cv2.line(annotated, (left_zone, 0), (left_zone, height), (100, 100, 100), 1)
        cv2.line(annotated, (right_zone, 0), (right_zone, height), (100, 100, 100), 1)

        # Draw obstacles
        for obs in obstacles:
            x, y = obs.position
            w, h = obs.size

            # Color based on distance (red = close, yellow = far)
            if obs.distance < 0.3:
                color = (0, 0, 255)  # Red
            elif obs.distance < 0.6:
                color = (0, 165, 255)  # Orange
            else:
                color = (0, 255, 255)  # Yellow

            # Draw bounding box
            x1, y1 = x - w // 2, y - h // 2
            cv2.rectangle(annotated, (x1, y1), (x1 + w, y1 + h), color, 2)

            # Draw label
            label = f"{obs.type.name} {obs.distance:.2f}"
            cv2.putText(annotated, label, (x1, y1 - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Draw safety indicators
        indicator_y = 30
        cv2.putText(annotated, f"FWD: {'OK' if safety['forward'] else 'BLOCKED'}",
                   (10, indicator_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                   (0, 255, 0) if safety['forward'] else (0, 0, 255), 2)
        cv2.putText(annotated, f"LEFT: {'OK' if safety['left'] else 'BLOCKED'}",
                   (10, indicator_y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                   (0, 255, 0) if safety['left'] else (0, 0, 255), 2)
        cv2.putText(annotated, f"RIGHT: {'OK' if safety['right'] else 'BLOCKED'}",
                   (10, indicator_y + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                   (0, 255, 0) if safety['right'] else (0, 0, 255), 2)

        return annotated


# Standalone testing
if __name__ == "__main__":
    print("🔍 Testing AI Vision Module...")

    # Test with webcam or video file
    processor = VisionProcessor()

    # Try to open camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Could not open camera")
        sys.exit(1)

    print("📹 Camera opened. Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Process frame
        result = processor.process_frame(frame, annotate=True)

        # Display results
        if result.frame_annotated is not None:
            cv2.imshow('Tank Vision - Obstacle Detection', result.frame_annotated)

        # Print recommendations
        print(f"Obstacles: {len(result.obstacles)} | "
              f"Safe: F={result.safe_to_move_forward} L={result.safe_to_turn_left} R={result.safe_to_turn_right} | "
              f"Recommended: {result.recommended_direction}")

        # Exit on 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
