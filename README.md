# Physics Lab

基于 PySide6 的物理实验桌面平台原型。平台提供通用实验创建流程，具体实验通过插件目录扩展。

## 启动

```powershell
python -m pip install -r requirements.txt
python app.py
```

如果 Windows 没有把 Python 加入 PATH，请使用本机 Python 解释器的完整路径运行上述命令。

## 当前流程

```text
新实验 -> 选择实验插件 -> 通用配置 -> 实验参数 -> 实验操作 -> 实验结果
```

当前内置“单摆实验”和“温度采集实验”插件，实验执行阶段使用模拟设备生成数据。每个项目会保存到 `projects/<实验编号>/manifest.json`，并创建 `raw`、`processed`、`results` 和 `logs` 目录。实验编号就是项目唯一标识，重复编号会被拒绝，不会覆盖已有项目。原始数据使用插件定义的 JSONL 行结构保存；插件可以选择通用表格导出组件，也可以实现自己的图表、表格或导出格式。

打开历史项目时，平台根据 `manifest.json` 的 `current_step` 恢复到上次保存的工作流页面。

历史列表支持删除项目；删除前会要求确认，并同时删除该项目的 manifest、原始数据和日志。正在运行的实验必须先取消并释放设备。

项目 manifest 带有 `schema_version`。打开旧版项目时平台会自动补齐可迁移字段并回写；如果项目使用的插件版本与当前版本不同，平台会提示检查兼容性。

真实单摆设备通过 `PHYSICS_LAB_PENDULUM_PORT` 在启动时配置串口；未配置时使用模拟设备。

Arduino 固件通过 JSONL `hello` 消息声明 `protocol` 版本。Python 适配器会在采集前校验协议版本，不支持的固件会在握手阶段拒绝连接。

温度实验也提供独立串口适配器和 ESP32-S3 模拟温度固件。烧录温度固件后，通过 `PHYSICS_LAB_TEMPERATURE_PORT` 配置串口；未配置时使用模拟温度设备。

平台通过 `DeviceManager` 管理设备登记和独占占用。插件声明 `device_requirements`，实验工作流通过 `PlatformServices` 获取匹配设备；一个插件可以原子地申请多个不同设备。当前提供 `SimulatedPendulumDevice`；真实 Arduino 设备后续只需实现相同的设备接口，固件烧录仍由 Arduino IDE 手动完成。

## 新增实验插件

完整开发流程见 [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md)，代码骨架见 `physics_lab/plugins/PLUGIN_TEMPLATE.md`。

在 `physics_lab/plugins/<plugin_id>/plugin.py` 中提供 `get_plugin()`，返回包含以下内容的插件对象：

```python
plugin_id
version
display_name
description
create_workflow(project)
```

工作流通过 `page_ids()` 声明页面顺序，通过 `create_page()` 创建页面，通过 `run(worker)` 执行后台实验任务。平台不要求不同实验拥有相同的配置、采集或结果结构。

## 测试

```powershell
python -m pytest -q
```
