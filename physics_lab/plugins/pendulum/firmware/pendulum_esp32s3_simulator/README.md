# ESP32-S3 Pendulum Simulator

Open `pendulum_esp32s3_simulator.ino` in Arduino IDE, select the ESP32-S3 Zero board, and upload it manually.

The sketch uses `115200` baud and newline-delimited JSON. The Python application sends `hello`, validates the experiment and protocol, then sends `collect_periods`. The board returns 101 `sample` messages followed by `done`. During collection, `pause`, `resume`, and `stop` control the stream.

To use the board from the application, set the serial port before starting:

```powershell
$env:PHYSICS_LAB_PENDULUM_PORT = "COM7"
python app.py
```

Replace `COM7` with the port shown by Arduino IDE. If the variable is absent, the built-in simulated device is used.
