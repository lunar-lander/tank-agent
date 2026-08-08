#!/usr/bin/env python3
"""
GPIO Compatibility Layer for Raspberry Pi 5
Provides RPi.GPIO-like interface using lgpio for Pi 5 compatibility
"""

import time
try:
    import lgpio
    PI5_AVAILABLE = True
except ImportError:
    PI5_AVAILABLE = False

try:
    import RPi.GPIO as RPI_GPIO_MODULE
    RPI_GPIO_AVAILABLE = True
except ImportError:
    RPI_GPIO_AVAILABLE = False

class GPIO:
    # Constants
    BCM = "BCM"
    OUT = "OUT" 
    IN = "IN"
    HIGH = 1
    LOW = 0
    
    _handle = None
    _pwm_instances = {}
    
    @classmethod
    def setmode(cls, mode):
        """Set GPIO numbering mode (BCM/BOARD)"""
        if PI5_AVAILABLE:
            # lgpio always uses BCM numbering; open the chip once so all
            # pins are claimed on the same handle (reopening would make
            # later writes fail with "GPIO busy")
            if cls._handle is None:
                cls._handle = lgpio.gpiochip_open(0)
        elif RPI_GPIO_AVAILABLE:
            RPI_GPIO_MODULE.setmode(RPI_GPIO_MODULE.BCM if mode == "BCM" else RPI_GPIO_MODULE.BOARD)
        else:
            print("Warning: No GPIO library available - running in simulation mode")
    
    @classmethod
    def setwarnings(cls, flag):
        """Set GPIO warnings"""
        if RPI_GPIO_AVAILABLE and not PI5_AVAILABLE:
            RPI_GPIO_MODULE.setwarnings(flag)
    
    @classmethod
    def setup(cls, pin, direction):
        """Setup GPIO pin"""
        if PI5_AVAILABLE and cls._handle is not None:
            if direction == "OUT":
                lgpio.gpio_claim_output(cls._handle, pin)
            else:
                lgpio.gpio_claim_input(cls._handle, pin)
        elif RPI_GPIO_AVAILABLE:
            RPI_GPIO_MODULE.setup(pin, RPI_GPIO_MODULE.OUT if direction == "OUT" else RPI_GPIO_MODULE.IN)
    
    @classmethod
    def output(cls, pin, value):
        """Set GPIO pin output"""
        if PI5_AVAILABLE:
            # On Pi 5 use lgpio; if the chip has been cleaned up this is a no-op
            if cls._handle is not None:
                lgpio.gpio_write(cls._handle, pin, value)
        elif RPI_GPIO_AVAILABLE:
            RPI_GPIO_MODULE.output(pin, value)
        else:
            print(f"GPIO: Setting pin {pin} to {value}")
    
    @classmethod
    def cleanup(cls):
        """Cleanup GPIO"""
        if PI5_AVAILABLE and cls._handle is not None:
            # Stop all PWM instances
            for pwm in cls._pwm_instances.values():
                pwm.stop()
            cls._pwm_instances.clear()
            lgpio.gpiochip_close(cls._handle)
            cls._handle = None
        elif RPI_GPIO_AVAILABLE:
            RPI_GPIO_MODULE.cleanup()
    
    @classmethod
    def PWM(cls, pin, frequency):
        """Create PWM instance"""
        if PI5_AVAILABLE:
            return LgpioPWM(cls._handle, pin, frequency)
        elif RPI_GPIO_AVAILABLE:
            return RPI_GPIO_MODULE.PWM(pin, frequency)
        else:
            return SimulatedPWM(pin, frequency)

class LgpioPWM:
    """PWM implementation using lgpio for Pi 5"""
    def __init__(self, handle, pin, frequency):
        self.pin = pin
        self.frequency = frequency
        self.duty_cycle = 0
        self.running = False
        
    def start(self, duty_cycle):
        """Start PWM with given duty cycle"""
        self.duty_cycle = duty_cycle
        if GPIO._handle is not None:
            lgpio.tx_pwm(GPIO._handle, self.pin, self.frequency, duty_cycle)
        self.running = True
    
    def ChangeDutyCycle(self, duty_cycle):
        """Change PWM duty cycle"""
        self.duty_cycle = duty_cycle
        if self.running and GPIO._handle is not None:
            lgpio.tx_pwm(GPIO._handle, self.pin, self.frequency, duty_cycle)
    
    def stop(self):
        """Stop PWM"""
        if GPIO._handle is not None:
            lgpio.tx_pwm(GPIO._handle, self.pin, 0, 0)  # Stop PWM
        self.running = False

class SimulatedPWM:
    """Simulated PWM for testing without hardware"""
    def __init__(self, pin, frequency):
        self.pin = pin
        self.frequency = frequency
        self.duty_cycle = 0
        
    def start(self, duty_cycle):
        self.duty_cycle = duty_cycle
        print(f"PWM: Starting pin {self.pin} at {self.frequency}Hz, {duty_cycle}% duty cycle")
    
    def ChangeDutyCycle(self, duty_cycle):
        self.duty_cycle = duty_cycle
        print(f"PWM: Pin {self.pin} duty cycle changed to {duty_cycle}%")
    
    def stop(self):
        print(f"PWM: Stopping pin {self.pin}")