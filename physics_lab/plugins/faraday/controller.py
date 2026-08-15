from __future__ import annotations

import copy
from collections import deque
from threading import Condition
from typing import Any

from PySide6.QtCore import QObject, Signal

from physics_lab.core.cancellation import ExperimentCancelled
from physics_lab.core.contracts import DeviceRequirement, ExperimentProject, PlatformServices, WorkflowWorker
from physics_lab.devices.serial_faraday import FaradaySampleTimeout, SerialFaradayDevice
from physics_lab.plugins.faraday.calculations import rotation_angle, summarize_samples, wavelength_result


RAW_FILENAME = "faraday_samples.jsonl"


class FaradayCollectionStopped(Exception):
    """Raised when the operator stops the current magnetic-field point."""


class FaradayController(QObject):
    sample_received = Signal(dict)
    point_changed = Signal(dict)
    wavelength_changed = Signal(dict)
    session_ready = Signal()
    session_message = Signal(str)

    def __init__(self, project: ExperimentProject, services: PlatformServices) -> None:
        super().__init__()
        self.project = project
        self.services = services
        self._condition = Condition()
        self._commands: deque[tuple[str, dict[str, Any]]] = deque()
        self._device: Any = None
        self._worker: WorkflowWorker | None = None
        self._running = False
        self._debug_active = False
        self._collect_active = False
        self._stop_requested = False
        self._selected_wavelength: str | None = None
        self._data: dict[str, dict[str, Any]] = {}

    def _push(self, command: str, **payload: Any) -> None:
        with self._condition:
            self._commands.append((command, payload))
            self._condition.notify_all()

    def select_wavelength(self, wavelength_id: str) -> None:
        self._push("select_wavelength", wavelength_id=wavelength_id)

    def start_debug(self, point_id: str | None = None) -> None:
        self._push("debug_start", point_id=point_id)

    def stop_debug(self) -> None:
        if self._debug_active and self._device is not None:
            self._device.send_command("debug_stop")
        else:
            self._push("debug_stop")

    def collect_point(self, point_id: str) -> None:
        self._push("collect", point_id=point_id)

    def stop_collect(self) -> None:
        if not self._collect_active or self._device is None:
            return
        self._stop_requested = True
        self._device.send_command("stop")

    def _next_command(self, worker: WorkflowWorker) -> tuple[str, dict[str, Any]]:
        with self._condition:
            while not self._commands:
                if getattr(worker, "is_cancelled", lambda: False)():
                    raise ExperimentCancelled()
                self._condition.wait(0.1)
            return self._commands.popleft()

    def _config(self) -> dict[str, Any]:
        return self.project.plugin_config

    def _length_m(self) -> float:
        return float(self._config()["sample"]["length_m"])

    def _build_data(self) -> None:
        points = self._config().get("field_points", [])
        self._data = {}
        for wavelength in self._config().get("wavelengths", []):
            self._data[str(wavelength["id"])] = {
                "id": str(wavelength["id"]),
                "value_nm": float(wavelength["value_nm"]),
                "status": "waiting",
                "anomalies": [],
                "_event_sequence": 0,
                "points": [
                    {
                        "id": str(point["id"]),
                        "index": index,
                        "current_a": float(point["current_a"]),
                        "magnetic_field_t": float(point["magnetic_field_t"]),
                        "status": "waiting",
                        "anomalies": [],
                        "_event_sequence": 0,
                    }
                    for index, point in enumerate(points, start=1)
                ],
            }

    def _all_complete(self) -> bool:
        return bool(self._data) and all(
            point["status"] == "complete"
            for wavelength in self._data.values()
            for point in wavelength["points"]
        )

    def _all_wavelength_points_complete(self, wavelength: dict[str, Any]) -> bool:
        return bool(wavelength["points"]) and all(point["status"] == "complete" for point in wavelength["points"])

    @staticmethod
    def _update_partial_angles(wavelength: dict[str, Any]) -> list[dict[str, Any]]:
        """Calculate theta as soon as a completed zero-field reference exists."""
        complete_points = [point for point in wavelength["points"] if point.get("status") == "complete"]
        zero_points = [
            point
            for point in complete_points
            if float(point.get("magnetic_field_t", 0.0)) == 0.0 and "r" in point
        ]
        if len(zero_points) != 1:
            return []
        r0 = float(zero_points[0]["r"])
        changed: list[dict[str, Any]] = []
        for point in complete_points:
            if "r" not in point:
                continue
            theta = 0.0 if float(point["magnetic_field_t"]) == 0.0 else rotation_angle(float(point["r"]), r0)
            if point.get("theta_rad") != theta:
                point["theta_rad"] = theta
                changed.append(point)
        return changed

    def _raw_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for wavelength in self._data.values():
            for point in wavelength["points"]:
                for sample in point.get("samples", []):
                    rows.append(self._raw_row(wavelength, point, sample, True))
                for sample in point.get("anomalies", []):
                    rows.append(self._raw_row(wavelength, point, sample, False))
        return rows

    @staticmethod
    def _raw_row(
        wavelength: dict[str, Any],
        point: dict[str, Any],
        sample: dict[str, Any],
        valid: bool,
    ) -> dict[str, Any]:
        return {
            "wavelength_id": wavelength["id"],
            "wavelength_nm": wavelength["value_nm"],
            "point_id": point["id"],
            "point_index": point["index"],
            "current_a": point["current_a"],
            "magnetic_field_t": point["magnetic_field_t"],
            "event_index": sample.get("event_index", sample.get("index", -1)),
            "sample_index": sample.get("index", -1),
            "raw_left": sample.get("raw_left"),
            "raw_right": sample.get("raw_right"),
            "r": sample.get("r"),
            "valid": valid,
            "status": "valid" if valid else "abnormal",
            "abnormal_reason": "" if valid else str(sample.get("reason", "未知异常")),
            "mode": str(sample.get("mode", "formal")),
            "debug": bool(sample.get("debug", False)),
        }

    def _anomaly_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for wavelength in self._data.values():
            for point in wavelength["points"]:
                for sample in point.get("anomalies", []):
                    record = self._raw_row(wavelength, point, sample, False)
                    record.pop("valid", None)
                    records.append(record)
        return records

    def _result_snapshot(self) -> dict[str, Any]:
        wavelengths: list[dict[str, Any]] = []
        anomalies = self._anomaly_records()
        for wavelength in self._data.values():
            item = copy.deepcopy(wavelength)
            item.pop("samples", None)
            item.pop("anomalies", None)
            item.pop("_event_sequence", None)
            for point in item["points"]:
                point.pop("samples", None)
                point.pop("anomalies", None)
                point.pop("_event_sequence", None)
            if self._all_wavelength_points_complete(wavelength):
                calculated = wavelength_result(item["points"], self._length_m())
                item.update({key: value for key, value in calculated.items() if key != "points"})
                item["points"] = calculated["points"]
                item["status"] = "complete"
            wavelengths.append(item)
        return {
            "sample": copy.deepcopy(self._config().get("sample", {})),
            "wavelengths": wavelengths,
            "anomalies": anomalies,
            "complete": self._all_complete(),
        }

    def _persist_snapshot(self) -> None:
        rows = self._raw_rows()
        self.services.project_repository.write_raw_rows(
            self.project,
            rows,
            RAW_FILENAME,
            columns=(
                "wavelength_id", "wavelength_nm", "point_id", "point_index", "current_a",
                "magnetic_field_t", "event_index", "sample_index", "raw_left", "raw_right", "r",
                "valid", "status", "abnormal_reason", "mode", "debug",
            ),
        )
        self.project.result = self._result_snapshot()
        self.services.project_repository.save(self.project)

    def clear_run_data(self) -> None:
        self._data.clear()
        self.project.result = {}
        try:
            self.services.project_repository.delete_raw_file(self.project, RAW_FILENAME)
        except (OSError, FileNotFoundError):
            self.services.project_repository.save(self.project)
        self.services.project_repository.save(self.project)

    def _emit_point(self, wavelength: dict[str, Any], point: dict[str, Any]) -> None:
        payload = copy.deepcopy(point)
        payload["wavelength_id"] = wavelength["id"]
        self.point_changed.emit(payload)
        self.wavelength_changed.emit({"id": wavelength["id"], "status": wavelength["status"]})

    def _check_worker(self) -> None:
        if self._worker is not None and getattr(self._worker, "is_cancelled", lambda: False)():
            if self._device is not None:
                self._device.send_command("stop")
            raise ExperimentCancelled()

    def _on_sample(self, sample: dict[str, Any], wavelength_id: str, point_id: str, debug: bool) -> None:
        self._check_worker()
        if self._worker is not None and getattr(self._worker, "is_paused", lambda: False)():
            self._device.send_command("pause")
            self._worker.wait_until_resumed()
            self._check_worker()
            self._device.send_command("resume")
        sample = dict(sample)
        sample["wavelength_id"] = wavelength_id
        sample["point_id"] = point_id
        sample["debug"] = debug
        self.sample_received.emit(sample)

    @staticmethod
    def _tag_sample(point: dict[str, Any], sample: dict[str, Any], debug: bool) -> dict[str, Any]:
        point["_event_sequence"] = int(point.get("_event_sequence", 0)) + 1
        tagged = dict(sample)
        tagged["event_index"] = point["_event_sequence"]
        tagged["valid"] = bool(tagged.get("valid", True))
        tagged["debug"] = debug
        return tagged

    def _handle_sample(
        self,
        wavelength: dict[str, Any],
        point: dict[str, Any],
        sample: dict[str, Any],
        debug: bool,
    ) -> dict[str, Any]:
        tagged = self._tag_sample(point, sample, debug)
        if not tagged["valid"]:
            point.setdefault("anomalies", []).append(copy.deepcopy(tagged))
        self._on_sample(tagged, wavelength["id"], point["id"], debug)
        return tagged

    def _run_debug(self, wavelength: dict[str, Any], point: dict[str, Any]) -> None:
        self._debug_active = True
        point["status"] = "debugging"
        self._emit_point(wavelength, point)
        try:
            self._device.request(
                "debug_start",
                on_sample=lambda sample: self._handle_sample(wavelength, point, sample, True),
            )
        except FaradaySampleTimeout as exc:
            point["last_error"] = str(exc)
            self.session_message.emit(f"调试发现异常值，5秒内未恢复；已记录异常，可修正后重试")
        finally:
            self._debug_active = False
            if point["status"] == "debugging":
                point["status"] = "waiting"
            self._emit_point(wavelength, point)

    def _run_collect(self, wavelength: dict[str, Any], point: dict[str, Any]) -> None:
        for key in ("raw_left", "raw_right", "r", "samples", "theta_rad", "last_error"):
            point.pop(key, None)
        point["anomalies"] = []
        point["_event_sequence"] = 0
        point["status"] = "collecting"
        wavelength["status"] = "collecting"
        self._emit_point(wavelength, point)
        count = int(self._config()["serial"]["samples_per_point"])
        samples: list[dict[str, Any]] = []
        self._collect_active = True
        self._stop_requested = False

        def on_sample(sample: dict[str, Any]) -> None:
            tagged = self._handle_sample(wavelength, point, sample, False)
            if tagged["valid"]:
                samples.append(tagged)

        try:
            self._device.request("collect", {"count": count}, on_sample=on_sample)
            if self._stop_requested:
                raise FaradayCollectionStopped()
            if len(samples) != count:
                raise ValueError(f"磁场点 {point['index']} 只收到 {len(samples)} / {count} 个采样值")
            point.update(summarize_samples(samples))
            point["samples"] = samples
            point.pop("last_error", None)
            point["status"] = "complete"
            wavelength["status"] = "complete" if self._all_wavelength_points_complete(wavelength) else "collecting"
            points_to_emit = self._update_partial_angles(wavelength)
            if not any(item["id"] == point["id"] for item in points_to_emit):
                points_to_emit.append(point)
            for changed_point in points_to_emit:
                self._emit_point(wavelength, changed_point)
            self._persist_snapshot()
        except FaradayCollectionStopped:
            point["status"] = "waiting"
            point.pop("last_error", None)
            self._emit_point(wavelength, point)
            self._persist_snapshot()
            self.session_message.emit("当前磁场点已停止，可以重新采集")
        except FaradaySampleTimeout as exc:
            point["status"] = "waiting"
            point["last_error"] = str(exc)
            self._emit_point(wavelength, point)
            self.session_message.emit("异常值已记录，5秒内未恢复；当前磁场点未完成，请修正后重试")
            return
        except Exception:
            point["status"] = "waiting"
            self._emit_point(wavelength, point)
            raise
        finally:
            self._collect_active = False
            self._stop_requested = False

    def run(self, worker: WorkflowWorker) -> None:
        self._worker = worker
        self._running = True
        leases = []
        device_id = ""
        registered = False
        completed = False
        try:
            self.clear_run_data()
            self._build_data()
            config = self._config()
            port = str(config["serial"]["port"]).strip()
            baudrate = int(config["serial"]["baudrate"])
            device = SerialFaradayDevice(port, baudrate)
            self._device = device
            device_id = device.device_id
            self.services.device_manager.register(device)
            registered = True
            requirement = DeviceRequirement(
                "esp32s3_board",
                frozenset({"faraday_sampling"}),
                firmware="faraday-esp32s3-zero",
                channels=frozenset({"raw_left", "raw_right"}),
            )
            leases = self.services.device_manager.acquire_all((requirement,), owner=self.project.project_id)
            device.connect()
            self.project.device_metadata = device.metadata
            self.session_ready.emit()
            self.session_message.emit("设备已连接，选择波长后开始调试或采集")

            while not self._all_complete():
                self._check_worker()
                command, payload = self._next_command(worker)
                if command == "select_wavelength":
                    wavelength_id = str(payload["wavelength_id"])
                    if wavelength_id not in self._data:
                        raise ValueError(f"未知波长配置：{wavelength_id}")
                    self._selected_wavelength = wavelength_id
                    self.session_message.emit(f"已选择波长 {self._data[wavelength_id]['value_nm']} nm")
                    continue
                if self._selected_wavelength is None:
                    raise ValueError("请先选择并确认实验波长")
                wavelength = self._data[self._selected_wavelength]
                if command == "debug_start":
                    point_id = payload.get("point_id")
                    point = next(
                        (item for item in wavelength["points"] if point_id and item["id"] == point_id),
                        None,
                    )
                    if point is None:
                        point = next((item for item in wavelength["points"] if item["status"] != "complete"), None)
                    if point is None:
                        point = wavelength["points"][0]
                    self._run_debug(wavelength, point)
                elif command == "collect":
                    point_id = str(payload["point_id"])
                    point = next((item for item in wavelength["points"] if item["id"] == point_id), None)
                    if point is None:
                        raise ValueError(f"未知磁场点：{point_id}")
                    self._run_collect(wavelength, point)
                elif command == "debug_stop":
                    continue

            final_result = self._result_snapshot()
            self.project.result = final_result
            self.services.project_repository.save(self.project)
            completed = True
            worker.completed.emit(final_result)
        except ExperimentCancelled:
            self.clear_run_data()
            worker.cancelled.emit()
        except Exception as exc:  # pragma: no cover - worker boundary
            self.clear_run_data()
            worker.failed.emit(str(exc))
        finally:
            self._running = False
            self._debug_active = False
            if self._device is not None:
                self._device.disconnect()
            if leases:
                self.services.device_manager.release_all(leases)
            if registered and device_id:
                self.services.device_manager.unregister(device_id)
            if not completed:
                self.project.device_metadata = {}
            self._device = None
            self._worker = None
