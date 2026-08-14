# 新实验插件开发指南

本文说明如何为 Physics Lab 增加一个实验插件。插件负责实验特有的配置、采集流程、计算、结果展示和固件；平台负责导航、项目保存、设备租约、线程、日志和通用 CSV 导出。

## 1. 创建目录

使用小写、稳定、只包含字母数字和下划线的 `plugin_id`：

```text
physics_lab/plugins/<plugin_id>/
  __init__.py
  plugin.py
  config_page.py       # 可选，也可以全部放在 plugin.py
  operation_page.py    # 可选
  result_page.py       # 可选
  controller.py        # 采集和计算逻辑，可选
  protocol.py          # 插件协议，可选
  firmware/            # Arduino 源码和说明，可选
```

可以复制 `physics_lab/plugins/PLUGIN_TEMPLATE.md` 作为起点。不要修改主窗口来增加实验分支。

## 2. 实现插件入口

`plugin.py` 必须提供无参数的 `get_plugin()`，返回包含以下字段和方法的对象：

```python
class MyPlugin:
    plugin_id = "my_experiment"
    api_version = 1
    version = "1.0.0"
    display_name = "我的实验"
    description = "实验卡片上的简短说明"
    icon = "*"
    device_requirements = (
        DeviceRequirement(
            "esp32s3_board",
            frozenset({"my_sampling"}),
            firmware="my-esp32s3-sim",
            channels=frozenset({"my_sensor"}),
        ),
    )

    def create_workflow(self, project, services):
        return MyWorkflow(project, services, self.device_requirements)


def get_plugin():
    return MyPlugin()
```

插件 ID 必须唯一，版本使用三段式 `主版本.次版本.修订版本`。插件管理器会检查入口、元数据、API 版本和设备需求；加载失败会显示在新实验页面。

## 3. 实现工作流页面

工作流实现以下接口：

- `page_ids() -> list[str]`：返回页面顺序，例如 `config`、`run`、`result`。
- `page_title(page_id)`：返回页面标题。
- `create_page(page_id, parent)`：创建对应的 PySide6 页面，并保存到 `self.pages`，结果页需要支持 `refresh()`。
- `run(worker)`：在后台线程中获取设备、采集数据、计算结果并发送信号。

有输入的页面实现 `validate() -> tuple[bool, str]` 和 `save_to_project(project)`。配置写入 `project.plugin_config`，结果写入 `project.result`。不要直接调用 `MainWindow`；页面切换由平台统一管理。

运行逻辑必须释放设备：

```python
leases = services.device_manager.acquire_all(requirements, owner=project.project_id)
try:
    # device.connect(), device.request(...), worker.progress.emit(...)
    # worker.completed.emit(result)
finally:
    services.device_manager.release_all(leases)
```

采集回调中检查 `worker.is_cancelled()` 和 `worker.is_paused()`。取消时不要发送 `completed`；异常发送 `failed`，取消发送 `cancelled`。设备连接和断开应位于插件控制器或设备适配器中，不要放进 Qt 页面事件处理器。

## 4. 设计设备和固件

平台中的一个设备是一个 ESP32/Arduino 控制板，板上可以有多个传感器通道。`DeviceRequirement` 的四个匹配条件分别是：

- `device_type`：例如 `esp32s3_board`。
- `capabilities`：实验需要的能力，例如 `temperature_sampling`。
- `firmware`：期望的固件标识；串口设备在握手前可以为空，连接后必须校验。
- `channels`：需要的传感器通道集合。

共享 JSONL 串口传输放在 `physics_lab/devices/`。新增真实适配器时参考 `serial_pendulum.py` 和 `serial_temperature.py`，实现 `Device` 接口，并使用 `physics_lab/devices/protocol.py` 的协议版本校验。实验固件放在自己的 `firmware/` 目录，由 Arduino IDE 手动烧录。

当前握手格式为：

```json
{"command":"hello","protocol":1}
{"type":"hello","device_id":"...","experiment":"my_experiment","firmware":"my-firmware","version":"1.0.0","protocol":1}
```

采集消息应使用明确的字段，例如 `sample`、`index`、`temperature`，结束发送 `done`，失败发送 `error`。暂停、继续和取消命令应在固件 README 中写清楚。若使用真实串口，需要在 `app.py` 增加一个环境变量到适配器的注册；例如 `PHYSICS_LAB_TEMPERATURE_PORT`。同一块板切换不同实验固件时，只配置当前实验的端口变量。

## 5. 保存数据和结果

平台项目目录是 `projects/<实验编号>/`。使用 `ProjectRepository` 保存，不要自行拼接项目路径：

- `manifest.json`：通用配置、插件配置、结果、设备元数据和当前步骤。
- `raw/*.jsonl`：插件定义的原始数据行，使用 `write_raw_rows()` 或 `write_raw_samples()`。
- `processed/`、`results/`：插件需要的派生文件。
- `logs/`：平台写入实验日志和错误日志。

每种实验可以拥有不同的原始列、结果结构和结果页。简单表格使用 `RawDataPanel`；需要图表、多个文件或特殊格式时，在插件结果页中实现自己的展示和导出。采集完成后结果页的 `refresh()` 必须同时刷新摘要和原始数据面板。

## 6. 测试和验收

至少增加以下测试：

- 插件能被 `PluginManager` 发现，元数据和设备需求正确。
- 配置校验、配置保存和项目恢复正确。
- 模拟设备能完成完整采集、取消、暂停和继续。
- 串口适配器用 fake transport 覆盖握手、错误协议、错误实验类型和采样解析。
- 原始 JSONL、结果计算、重新计算和 CSV 导出正确。

运行检查：

```powershell
python -m compileall -q physics_lab tests app.py
python -m pytest -q
python app.py
```

真实硬件验收需要 Arduino IDE 烧录、配置对应串口环境变量，完成一次采集后检查 `manifest.json`、`raw/*.jsonl`、日志和导出的 CSV。提交前还要确认拔板、取消、关闭窗口和重复打开历史项目不会留下运行中的线程或设备租约。
