# Tank Robot Makefile
# Installation and deployment for Raspberry Pi

INSTALL_DIR = /opt/tank-agent
SERVICE_DIR = /etc/systemd/system
PYTHON = python3
USER = pi

.PHONY: help install install-deps install-files install-services enable-services uninstall clean test

help:
	@echo "Tank Robot Installation Makefile"
	@echo "================================"
	@echo ""
	@echo "Available targets:"
	@echo "  install          - Full installation (deps + files + services)"
	@echo "  install-deps     - Install Python dependencies"
	@echo "  install-files    - Copy files to $(INSTALL_DIR)"
	@echo "  install-services - Install systemd services"
	@echo "  enable-services  - Enable and start services"
	@echo "  uninstall        - Remove installation"
	@echo "  test             - Run hardware tests"
	@echo "  clean            - Clean temporary files"

install: install-deps install-files install-services
	@echo ""
	@echo "✅ Installation complete!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Enable services: sudo make enable-services"
	@echo "  2. Test hardware: make test"
	@echo "  3. Access web interface: http://<pi-ip>:8080"

install-deps:
	@echo "📦 Installing system dependencies..."
	sudo apt update
	sudo apt install -y python3-pip python3-dev python3-lgpio
	@echo ""
	@echo "📦 Installing Python dependencies..."
	pip3 install -r requirements.txt
	@echo ""
	@echo "🔧 Configuring GPIO permissions..."
	sudo usermod -a -G gpio $(USER)
	@echo "✅ Dependencies installed"

install-files:
	@echo "📂 Creating installation directory..."
	sudo mkdir -p $(INSTALL_DIR)
	sudo mkdir -p $(INSTALL_DIR)/src
	sudo mkdir -p $(INSTALL_DIR)/utils
	sudo mkdir -p $(INSTALL_DIR)/config
	sudo mkdir -p $(INSTALL_DIR)/init
	@echo ""
	@echo "📋 Copying files..."
	sudo cp -r src/* $(INSTALL_DIR)/src/
	sudo cp -r utils/* $(INSTALL_DIR)/utils/
	sudo cp -r config/* $(INSTALL_DIR)/config/
	sudo cp requirements.txt $(INSTALL_DIR)/
	sudo cp README.md $(INSTALL_DIR)/
	sudo cp CLAUDE.md $(INSTALL_DIR)/
	@echo ""
	@echo "🔒 Setting permissions..."
	sudo chown -R $(USER):$(USER) $(INSTALL_DIR)
	sudo chmod +x $(INSTALL_DIR)/utils/*.py
	sudo chmod +x $(INSTALL_DIR)/src/*.py
	@echo "✅ Files installed to $(INSTALL_DIR)"

install-services:
	@echo "⚙️  Installing systemd services..."
	sudo cp init/camera-stream.service $(SERVICE_DIR)/
	sudo cp init/tank-control.service $(SERVICE_DIR)/
	sudo cp init/tank-autonomous.service $(SERVICE_DIR)/
	@echo ""
	@echo "🔄 Reloading systemd daemon..."
	sudo systemctl daemon-reload
	@echo "✅ Services installed"

enable-services:
	@echo "▶️  Enabling and starting services..."
	@echo ""
	@echo "Starting camera stream service..."
	sudo systemctl enable camera-stream.service
	sudo systemctl start camera-stream.service
	@echo ""
	@echo "Starting web control service..."
	sudo systemctl enable tank-control.service
	sudo systemctl start tank-control.service
	@echo ""
	@echo "Autonomous service installed but not started (enable manually if needed)"
	@echo "  To enable: sudo systemctl enable tank-autonomous.service"
	@echo "  To start:  sudo systemctl start tank-autonomous.service"
	@echo ""
	@echo "✅ Services enabled and started"
	@echo ""
	@echo "Check status with:"
	@echo "  sudo systemctl status camera-stream"
	@echo "  sudo systemctl status tank-control"

uninstall:
	@echo "🗑️  Stopping services..."
	-sudo systemctl stop camera-stream.service
	-sudo systemctl stop tank-control.service
	-sudo systemctl stop tank-autonomous.service
	@echo ""
	@echo "🗑️  Disabling services..."
	-sudo systemctl disable camera-stream.service
	-sudo systemctl disable tank-control.service
	-sudo systemctl disable tank-autonomous.service
	@echo ""
	@echo "🗑️  Removing service files..."
	-sudo rm -f $(SERVICE_DIR)/camera-stream.service
	-sudo rm -f $(SERVICE_DIR)/tank-control.service
	-sudo rm -f $(SERVICE_DIR)/tank-autonomous.service
	sudo systemctl daemon-reload
	@echo ""
	@echo "🗑️  Removing installation directory..."
	-sudo rm -rf $(INSTALL_DIR)
	@echo "✅ Uninstallation complete"

test:
	@echo "🧪 Running hardware tests..."
	@echo ""
	$(PYTHON) utils/test_mobility.py

quick-test:
	@echo "⚡ Running quick component test..."
	@echo ""
	$(PYTHON) utils/quick_test.py

status:
	@echo "📊 Service Status"
	@echo "================"
	@echo ""
	@echo "Camera Stream:"
	@sudo systemctl status camera-stream.service --no-pager | head -n 10
	@echo ""
	@echo "Web Control:"
	@sudo systemctl status tank-control.service --no-pager | head -n 10
	@echo ""
	@echo "Autonomous Agent:"
	@sudo systemctl status tank-autonomous.service --no-pager | head -n 10

logs:
	@echo "📜 Recent logs (Ctrl+C to exit)"
	@echo ""
	sudo journalctl -u camera-stream.service -u tank-control.service -u tank-autonomous.service -f

clean:
	@echo "🧹 Cleaning temporary files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Clean complete"

.DEFAULT_GOAL := help
