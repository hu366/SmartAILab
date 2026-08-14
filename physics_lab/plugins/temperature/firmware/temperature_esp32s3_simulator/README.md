# ESP32-S3 Temperature Simulator

Open `temperature_esp32s3_simulator.ino` in Arduino IDE, select the ESP32-S3 Zero board, and upload it manually.

The sketch uses `115200` baud and JSONL protocol version `1`. It supports `hello`, `collect_temperature`, `pause`, `resume`, and `stop`. Temperature samples are simulated, so no external sensor is required.

Before starting the application, configure the temperature serial port and clear the pendulum port if both would point to the same board:

```powershell
Remove-Item Env:PHYSICS_LAB_PENDULUM_PORT -ErrorAction SilentlyContinue
$env:PHYSICS_LAB_TEMPERATURE_PORT = "COM16"
python app.py
```

Replace `COM16` with the port shown by Arduino IDE. If `PHYSICS_LAB_TEMPERATURE_PORT` is absent, the built-in simulated temperature device is used.
