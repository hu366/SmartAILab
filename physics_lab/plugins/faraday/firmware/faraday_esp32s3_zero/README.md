# Faraday ESP32-S3 Zero firmware

This firmware is based on the SmartAILab dual photodiode reference firmware.
It reads the left and right channels from GPIO 7 and GPIO 8, performs the
two-stage average, and emits `physics-lab-jsonl` protocol v1 messages.

Select the Waveshare ESP32-S3 Zero board in the Arduino IDE and flash at
115200 baud. No third-party Arduino library is required.

Commands are JSON lines:

```json
{"command":"hello","protocol":1}
{"command":"debug_start"}
{"command":"debug_stop"}
{"command":"collect","count":10}
{"command":"pause"}
{"command":"resume"}
{"command":"stop"}
```

Debug mode emits one `sample` every 0.1 seconds. Formal mode emits `count`
samples, one approximately every second, then emits `done`. Each sample has
`raw_left`, `raw_right`, `r`, `index`, and `mode` fields.

If either optical channel is zero or invalid for one averaging cycle, that
cycle is discarded and sampling continues. It does not disconnect the
experiment.
